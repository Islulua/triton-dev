"""Offline board-profiler adapter and reports; never execute a kernel in mock mode."""
import copy
import hashlib
import html
import json
import math
import random
import re
import statistics
import time
import uuid
from pathlib import Path
from typing import Protocol

from triton_dev.common.contracts import ToolError, atomic_json, file_lock

CASES = [
    {'id': 'matmul-1024', 'nodeid': 'tests/test_matmul.py::test_matmul[fp16-1024]',
     'name': 'Matmul · 1024³', 'shape': [1024, 1024, 1024], 'dtype': 'fp16',
     'flops': 2 * 1024**3, 'bytes': 6 * 1024**2, 'kernel': 'matmul_fp16_tile128', 'base_us': 68},
    {'id': 'matmul-4096', 'nodeid': 'tests/test_matmul.py::test_matmul[fp16-4096]',
     'name': 'Matmul · 4096³', 'shape': [4096, 4096, 4096], 'dtype': 'fp16',
     'flops': 2 * 4096**3, 'bytes': 6 * 4096**2, 'kernel': 'matmul_fp16_tile128', 'base_us': 1640},
    {'id': 'softmax-4096', 'nodeid': 'tests/test_softmax.py::test_softmax[fp32-1024x4096]',
     'name': 'Softmax · 1024 × 4096', 'shape': [1024, 4096], 'dtype': 'fp32',
     'flops': 5 * 1024 * 4096, 'bytes': 8 * 1024 * 4096, 'kernel': 'softmax_reduce_f32', 'base_us': 84},
]
ENVIRONMENTS = [
    {'id': 'mock-baseline', 'name': 'baseline · 模拟稳定环境', 'revision': 'mock-sdk-20261022-r1',
     'packages': {'triton': 'mock-3.2-baseline', 'llvm': 'mock-18', 'torch': 'mock-2.6'}, 'factor': 1.0},
    {'id': 'mock-candidate', 'name': 'candidate · 模拟候选环境', 'revision': 'mock-sdk-20261023-r2',
     'packages': {'triton': 'mock-3.2-candidate', 'llvm': 'mock-19', 'torch': 'mock-2.6'}, 'factor': 1.23},
]
DEVICE = {'name': 'Mock Accelerator A1', 'id': 'mock-board-0', 'memory_gib': 32,
          'peak_tflops': 120, 'peak_bandwidth_gbs': 900, 'source': 'assumed_demo_spec'}


def catalog():
    return copy.deepcopy({'schema_version': 1, 'source': 'mock_board', 'cases': CASES,
                          'environments': ENVIRONMENTS, 'devices': [DEVICE],
                          'limits': {'warmup': [0, 20], 'repeats': [1, 100], 'seed': [0, 65535]}})


def validate_request(data):
    required = {'case_id', 'environment_id', 'warmup', 'repeats', 'seed', 'adapter', 'idempotency_key'}
    if not isinstance(data, dict) or set(data) != required:
        raise ToolError('INVALID_PROFILE', 'Exact profiling request fields required')
    if data['adapter'] != 'mock':
        raise ToolError('UNSUPPORTED', 'Only the mock board adapter is available; no board test executed')
    if data['case_id'] not in [c['id'] for c in CASES] or data['environment_id'] not in [e['id'] for e in ENVIRONMENTS]:
        raise ToolError('INVALID_PROFILE', 'Select a registered demo case and environment')
    for key, low, high in [('warmup', 0, 20), ('repeats', 1, 100), ('seed', 0, 65535)]:
        if type(data[key]) is not int or not low <= data[key] <= high:
            raise ToolError('INVALID_PROFILE', f'{key} must be an integer in {low}..{high}')
    if not isinstance(data['idempotency_key'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', data['idempotency_key']):
        raise ToolError('INVALID_PROFILE', 'A bounded idempotency key is required')
    return copy.deepcopy(data)


class BoardProfiler(Protocol):
    """Trusted adapter boundary. A real adapter must supply a validated versioned capture."""
    def capture(self, request: dict) -> dict: ...


class MockBoardProfiler:
    def capture(self, request):
        case = copy.deepcopy(next(c for c in CASES if c['id'] == request['case_id']))
        env = copy.deepcopy(next(e for e in ENVIRONMENTS if e['id'] == request['environment_id']))
        rng = random.Random(request['seed'])
        # Warmup samples are generated separately and never included in measured statistics.
        for _ in range(request['warmup']):
            rng.uniform(.97, 1.03)
        events, samples = [], []
        cursor = 0.0
        tiles = 8
        for iteration in range(request['repeats']):
            main = case['base_us'] * env['factor'] * rng.uniform(.97, 1.03)
            available, lookup, slots = {}, {}, {}
            def emit(name, category, track, duration, dependencies=(), tile=None, earliest=None):
                start = max([cursor if earliest is None else earliest, available.get(track, cursor),
                             *[lookup[d]['start_us'] + lookup[d]['duration_us'] for d in dependencies]])
                event = {'id': f'e{len(events)}', 'name': name, 'category': category,
                         'track': track, 'start_us': round(start, 3),
                         'duration_us': round(duration, 3), 'iteration': iteration,
                         'source': 'mock_board', 'depends_on': list(dependencies),
                         'tile': tile, 'buffer_slot': tile % 2 if tile is not None else None}
                events.append(event)
                lookup[event['id']] = event
                available[track] = event['start_us'] + event['duration_us']
                return event['id']
            submit = emit('submit_command_buffer', 'host', 'CPU / dispatch', 9)
            for tile in range(tiles):
                slot = tile % 2
                deps = [submit] + ([slots[slot]] if slot in slots else [])
                h2d = emit('prefetch_input', 'transfer', 'DMA / H2D',
                           case['bytes'] * 2 / 3 / 120000 / tiles + 2, deps, tile)
                load = emit('L2_to_SRAM', 'transfer', 'SDMA / load',
                            case['bytes'] * 2 / 3 / 900000 / tiles + 1.5, [h2d], tile)
                is_matmul = case['id'].startswith('matmul')
                track = f'Matrix / cluster {slot}' if is_matmul else f'Vector / core {slot}'
                compute = emit(case['kernel'], 'kernel', track, main / tiles, [load], tile)
                vector = emit('epilogue_store' if is_matmul else 'normalize_exp', 'kernel',
                              f'Vector / core {slot}', main * .12 / tiles, [compute], tile)
                store = emit('SRAM_to_L2', 'transfer', 'SDMA / store',
                             case['bytes'] / 3 / 900000 / tiles + 1, [vector], tile)
                out = emit('writeback_output', 'transfer', 'DMA / D2H',
                           case['bytes'] / 3 / 120000 / tiles + 1.5, [store], tile)
                slots[slot] = emit('signal_buffer_reuse', 'sync', 'Sync / fence', 1.2, [out], tile)
            finish = max(available.values())
            emit('host_wait_completion', 'wait', 'CPU / wait', finish - (cursor + 9),
                 earliest=cursor + 9)
            device_events = [e for e in lookup.values() if e['category'] in {'kernel', 'transfer', 'sync'}]
            device_start = min(e['start_us'] for e in device_events)
            samples.append({'iteration': iteration, 'device_us': round(finish - device_start, 3),
                            'wall_us': round(finish - cursor + 3, 3),
                            'kernel_work_us': round(sum(e['duration_us'] for e in device_events
                                                       if e['category'] == 'kernel'), 3)})
            cursor = round(finish + 3, 3)
        return {'schema_version': 1, 'model_version': 2, 'source': 'mock_board', 'case': case,
                'environment': env, 'device': copy.deepcopy(DEVICE), 'events': events,
                'samples': samples, 'pipeline': {'tiles': tiles, 'buffer_slots': 2,
                    'strategy': 'double_buffered_tiles', 'clock_domain': 'mock_shared_us'},
                'counters': {'occupancy_pct': 63 if env['factor'] == 1 else 48,
                             'memory_peak_mib': round(case['bytes'] / 1024**2 * 1.4, 2),
                             'source': 'simulated_counters'},
                'warmup_excluded': request['warmup']}


def interval_metrics(events):
    """Union and overlap time; simultaneous engines must not be summed as elapsed time."""
    boundaries = sorted([(e['start_us'], 1) for e in events]
                        + [(e['start_us'] + e['duration_us'], -1) for e in events])
    active = peak = 0
    union = overlap = 0.0
    previous = boundaries[0][0] if boundaries else 0
    for timestamp, change in boundaries:
        if active:
            union += timestamp - previous
        if active >= 2:
            overlap += timestamp - previous
        active += change
        peak = max(peak, active)
        previous = timestamp
    return {'busy_us': union, 'overlap_us': overlap, 'max_active_engines': peak}


def summarize(capture):
    """Derive metrics from capture, keeping simulated counters and ratios distinguishable."""
    if capture.get('schema_version') != 1 or capture.get('source') != 'mock_board':
        raise ToolError('UNSUPPORTED', 'Real board capture validation is not implemented')
    samples = capture['samples']
    values = [s['device_us'] for s in samples]
    if not values or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ToolError('INVALID_PROFILE', 'Positive finite device timings required')
    mean = statistics.mean(values)
    ordered = sorted(values)
    kernels = {}
    totals = {'kernel': 0, 'transfer': 0, 'host': 0}
    for event in capture['events']:
        duration = event['duration_us']
        totals[event['category']] = totals.get(event['category'], 0) + duration
        if event['category'] == 'kernel':
            item = kernels.setdefault(event['name'], {'name': event['name'], 'calls': 0, 'total_us': 0})
            item['calls'] += 1
            item['total_us'] += duration
    for item in kernels.values():
        item['mean_us'] = item['total_us'] / item['calls']
        item['share_pct'] = item['total_us'] / totals['kernel'] * 100
    case, device = capture['case'], capture['device']
    tflops = case['flops'] / (mean * 1e6)
    bandwidth = case['bytes'] / (mean * 1000)
    intensity = case['flops'] / case['bytes']
    roof = min(device['peak_tflops'], intensity * device['peak_bandwidth_gbs'] / 1000)
    engines = []
    wall = sum(s['wall_us'] for s in samples)
    for track in dict.fromkeys(e['track'] for e in capture['events']):
        items = [e for e in capture['events'] if e['track'] == track]
        busy = interval_metrics(items)['busy_us']
        engines.append({'track': track, 'category': items[0]['category'], 'events': len(items),
                        'busy_us': busy, 'window_pct': busy / wall * 100})
    concurrent = interval_metrics([e for e in capture['events'] if e['category'] in {'kernel', 'transfer'}])
    concurrent['overlap_pct'] = concurrent['overlap_us'] / sum(values) * 100
    return {'engines': engines, 'concurrency': concurrent,
            'kernel_work_mean_us': totals['kernel'] / len(samples),
            'timing_basis': 'device_pipeline_span' if capture.get('model_version') == 2 else 'kernel_sum',
            'sample_count': len(values), 'mean_us': mean, 'p50_us': statistics.median(values),
            'p95_us': ordered[max(0, math.ceil(.95 * len(values)) - 1)],
            'min_us': min(values), 'max_us': max(values),
            'wall_mean_us': statistics.mean(s['wall_us'] for s in samples),
            'tflops': tflops, 'effective_bandwidth_gbs': bandwidth, 'arithmetic_intensity': intensity,
            'roof_tflops': roof, 'roof_efficiency_pct': tflops / roof * 100,
            'bound_hint': 'memory' if roof < device['peak_tflops'] else 'compute',
            'category_us': totals, 'kernels': sorted(kernels.values(), key=lambda k: -k['total_us'])}


def chrome_trace(report):
    capture = report['capture']
    tracks = {name: i for i, name in enumerate(dict.fromkeys(e['track'] for e in capture['events']))}
    events = [{'ph': 'M', 'name': 'thread_name', 'pid': 1, 'tid': tid, 'args': {'name': name}}
              for name, tid in tracks.items()]
    events += [{'ph': 'X', 'name': e['name'], 'cat': e['category'], 'ts': e['start_us'],
                'dur': e['duration_us'], 'pid': 1, 'tid': tracks[e['track']],
                'args': {'iteration': e['iteration'], 'tile': e.get('tile'),
                         'buffer_slot': e.get('buffer_slot'), 'depends_on': e.get('depends_on', []),
                         'source': 'mock_board'}} for e in capture['events']]
    lookup = {e['id']: e for e in capture['events']}
    for event in capture['events']:
        for parent_id in event.get('depends_on', []):
            parent = lookup[parent_id]
            flow = f"{parent_id}-{event['id']}"
            events.extend([
                {'ph': 's', 'name': 'dependency', 'cat': 'flow', 'id': flow, 'pid': 1,
                 'tid': tracks[parent['track']], 'ts': parent['start_us'] + parent['duration_us']},
                {'ph': 'f', 'name': 'dependency', 'cat': 'flow', 'id': flow, 'pid': 1,
                 'tid': tracks[event['track']], 'ts': event['start_us'], 'bp': 'e'}])
    return {'traceEvents': events, 'displayTimeUnit': 'ms',
            'metadata': {'source': 'mock_board', 'report_id': report['id'],
                         'environment': capture['environment'], 'case': capture['case'],
                         'warning': 'Synthetic profiling demo; no physical board was tested'}}


def html_report(report):
    """Portable, script-free report with no external resources or network dependency."""
    def esc(value):
        return html.escape(str(value))
    capture, summary = report['capture'], report['summary']
    rows = ''.join(f"<tr><td>{esc(k['name'])}</td><td>{k['calls']}</td>"
                   f"<td>{k['mean_us']:.2f}</td><td>{k['share_pct']:.1f}%</td></tr>"
                   for k in summary['kernels'])
    values = [s['device_us'] for s in capture['samples']]
    low, high = min(values) * .96, max(values) * 1.04
    points = ' '.join(f'{40 + i / max(1, len(values) - 1) * 820:.2f},'
                      f'{170 - (v - low) / (high - low) * 140:.2f}' for i, v in enumerate(values))
    cards = ''.join(f'<article><span>{title}</span><h2>{value:.2f} <small>{unit}</small></h2></article>'
                    for title, value, unit in [('平均 Device', summary['mean_us'], 'μs'),
                        ('P95 Device', summary['p95_us'], 'μs'),
                        ('有效算力', summary['tflops'], 'TFLOP/s'),
                        ('估算带宽', summary['effective_bandwidth_gbs'], 'GB/s')])
    events = [e for e in capture['events'] if e['iteration'] == 0]
    end = max(e['start_us'] + e['duration_us'] for e in events)
    colors = {'host': '#a590c0', 'transfer': '#6092c3', 'kernel': '#40998a',
              'sync': '#d7a35c', 'wait': '#c1cbd1'}
    tracks = list(dict.fromkeys(e['track'] for e in events))
    labels = ''.join(f'<text x="0" y="{32 + i * 48}">{esc(track)}</text>'
                     for i, track in enumerate(tracks))
    bars = labels + ''.join(
        f'<rect x="{210 + e["start_us"] / end * 660:.2f}" '
        f'y="{15 + tracks.index(e["track"]) * 48}" '
        f'width="{max(1, e["duration_us"] / end * 660):.2f}" height="28" '
        f'fill="{colors[e["category"]]}"><title>{esc(e["name"])} '
        f'T{esc(e.get("tile"))} · {esc(e["duration_us"])} μs</title></rect>'
        for e in events)
    metadata = esc(json.dumps({'id': report['id'], 'request': report['request'],
        'environment': capture['environment'], 'device': capture['device'],
        'counters': capture['counters'], 'correctness': report['correctness']}, ensure_ascii=False, indent=2))
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profiling · {esc(capture['case']['name'])} · 模拟数据</title><style>
body{{font:14px/1.7 system-ui,sans-serif;color:#28444e;background:#f4f8f7;margin:0;padding:32px}}main{{max-width:1050px;margin:auto}}section,article{{background:white;border:1px solid #dde7e4;border-radius:8px;padding:22px;margin:18px 0}}.notice{{background:#fff6de;padding:15px;border-radius:6px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}}.cards article{{padding:18px}}h1{{margin-bottom:8px}}h2{{font-size:21px}}small{{font-size:11px}}svg{{width:100%;height:auto}}svg text{{font:11px system-ui;fill:#71868f}}table{{width:100%;text-align:left;border-collapse:collapse}}td,th{{padding:13px;border-bottom:1px solid #e6edeb}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}@media(max-width:650px){{body{{padding:15px}}.cards{{grid-template-columns:1fr 1fr}}}}@media print{{body{{background:white}}section{{break-inside:avoid}}}}
</style><main><p>TRITON-DEV / PROFILING REPORT</p><h1>{esc(capture['case']['name'])}</h1><p>{esc(capture['case']['nodeid'])}<br>{esc(capture['environment']['revision'])} · {len(values)} 次采样</p>
<p class="notice">模拟板卡 mock_board：没有执行真实 case 或设备测试。计数器、时间与板卡峰值均为假设，正确性未验证。</p>
<div class="cards">{cards}</div><section><h2>重复采样 Device 耗时</h2><p>最小 {min(values):.2f} μs / 最大 {max(values):.2f} μs；预热不计入统计。</p><svg viewBox="0 0 900 205" role="img" aria-label="模拟采样耗时曲线"><text x="40" y="15">{high:.2f} μs</text><text x="40" y="200">{low:.2f} μs</text><polyline points="{points}" fill="none" stroke="#16877e" stroke-width="3"/></svg></section>
<section><h2>Kernel 耗时排行</h2><table><tr><th>Kernel</th><th>调用</th><th>平均 μs</th><th>Device占比</th></tr>{rows}</table></section>
<section><h2>采样 1 · 事件时间线</h2><p>横轴 0–{end:.2f} μs；按执行引擎分轨，各引擎间可重叠。</p><svg viewBox="0 0 900 {len(tracks) * 48 + 20}" role="img" aria-label="模拟事件时间线">{bars}</svg></section>
<section><h2>口径与原始元数据</h2><p>Device时间按报告timing_basis：新版为流水线窗口，历史版为kernel工时。重叠事件时长相加不等于流水线耗时。算力与带宽按假设FLOPs/流量计算，并非硬件计数器实测；不作为根因判定。</p><pre>{metadata}</pre></section></main></html>'''


class ProfileStore:
    def __init__(self, root):
        self.root = Path(root)

    def read(self, report_id):
        if not isinstance(report_id, str) or not re.fullmatch(r'profile_[a-f0-9]{32}', report_id):
            raise ToolError('INVALID_PROFILE', 'Invalid report ID')
        try:
            return json.loads((self.root / f'{report_id}.json').read_text())
        except FileNotFoundError as exc:
            raise ToolError('PROFILE_NOT_FOUND', report_id) from exc

    def list(self):
        rows = []
        for file in self.root.glob('profile_*.json'):
            report = self.read(file.stem)
            rows.append({k: report[k] for k in ('id', 'created_at', 'request', 'summary', 'source')})
        return sorted(rows, key=lambda r: r['created_at'], reverse=True)

    def create(self, data):
        request = validate_request(data)
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with file_lock(self.root / '.lock'):
            for old in self.list():
                if old['request']['idempotency_key'] == request['idempotency_key']:
                    report = self.read(old['id'])
                    if report['request_hash'] != fingerprint:
                        raise ToolError('IDEMPOTENCY_CONFLICT', 'Profiling key already used with different options')
                    return report
            if len(list(self.root.glob('profile_*.json'))) >= 200:
                raise ToolError('PROFILE_LIMIT', 'Demo report storage limit is 200; archive reports before continuing')
            capture = MockBoardProfiler().capture(request)
            report = {'schema_version': 1, 'id': 'profile_' + uuid.uuid4().hex,
                      'state': 'generated', 'source': 'mock_board', 'created_at': time.time(),
                      'request': request, 'request_hash': fingerprint, 'capture': capture,
                      'summary': summarize(capture), 'correctness': 'not_checked',
                      'notes': ['No physical board or pytest case was executed.',
                                'All timings/counters and device peaks are simulated assumptions.',
                                'Device time is pipeline span; kernel work sums overlapping engines separately.',
                                'Roofline/bound hint uses an assumed traffic model; it is not a root cause.']}
            atomic_json(self.root / f"{report['id']}.json", report)
            return report

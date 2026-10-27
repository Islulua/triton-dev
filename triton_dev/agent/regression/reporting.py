"""Deterministic facts and reproducible issue reports; no model-authored commands."""
import hashlib
import html
import json
import shlex
from pathlib import Path

from triton_dev.common.contracts import atomic_json


def markdown(task, root):
    boundary = task.get('boundary') or {}
    bad = boundary.get('bad', {}).get('id', '未定位')
    good = boundary.get('good', {}).get('id', '未定位')
    failing = next((e for e in task['experiments'] if e['classification'] == 'target_failure'), None)
    command = shlex.join(['triton-dev', 'agent', 'regression', 'replay', task['id'],
                          '--cache-root', str(Path(root).parent.parent), '--experiment', failing['id']]) if failing else '暂无失败实验可重放'
    lines = ['# SDK regression 调研报告（mock）', '',
             f"任务：{task['id']} · 状态：{task['state']} · 结果：{task['result']}", '',
             '> SDK/组件/模型为模拟；真实CPU pytest子进程，不是板卡测试或真实依赖包归因。', '',
             f"基线：{task['spec']['baseline']}；固定latest：{task.get('target', {}).get('id', '尚未update')}",
             f'边界：{good} → {bad}',
             f"已证明所选历史序列最早失败：{task['earliest_proven']}",
             f"双向支持组件：{', '.join(task.get('supported_components', [])) or '未确认'}", '',
             '## 实验条件', '固定case：`test_regression.py::test_regression[fp16]`',
             f"场景：{task['spec']['scenario']}；源码SHA256：{task['scenario_sha256']}",
             f"阶段：{task['phase']}；耗时：{task['elapsed_seconds']:.2f}s；实验次数：{len(task['experiments'])}；模型调用：{task['model_calls']}", '',
             '## 版本与组件实验', '|实验|环境/组合|重复|结果|退出码|', '|---|---|---|---|---|']
    for e in task['experiments']:
        lines.append(f"|{e['id']}|{e['label']}|{e['repeat'] + 1}|{e['classification']}|{e.get('returncode', '—')}|")
    lines += ['', '## 组件双向干预', '|组件|向前引入|反向回退|支持|', '|---|---|---|---|']
    for row in task['attribution']:
        lines.append(f"|{','.join(row['components'])}|{row['forward']}|{row['rollback']}|{row['supported']}|")
    lines += ['', '## 最简复现（不调用模型）', '需保留本地任务缓存及相同版本triton-dev，并在有pytest的Python环境运行。',
              '```bash', command, '```', '',
              '另附reproduce.py与environment.json，可在独立目录执行：',
              '```bash', 'python -m pytest -q reproduce.py', '```',
              '此命令仅重放合成场景；真实SDK需后续适配器与制品映射。', '',
              '## 提单摘要', f'期望：baseline与latest相同case均通过。实际：{task["result"]}。',
              f'已验证边界：{good} → {bad}；归因范围：mock组件干预。',
              '原始证据位于runs/<experiment-id>/{request,result,environment,stages}.json及test_regression.py。', '',
              '## 限制', *['- ' + x for x in task['limitations']],
              '- 版本缺失/UNKNOWN不会被算作通过；边界模式依赖单调假设，不能证明全局首次。',
              '- 首个得到支持的组件组不表示唯一或全局最小根因；无真实so加载证据。']
    if task.get('error'):
        lines += ['', '错误：' + json.dumps(task['error'], ensure_ascii=False)]
    return '\n'.join(lines) + '\n'


def materialize(root, task):
    atomic_json(root / 'report.json', task)
    content = markdown(task, root)
    (root / 'report.md').write_text(content)
    (root / 'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<title>Regression report</title><body><h1>Regression · mock evidence</h1><pre>'
        + html.escape(content) + '</pre></body></html>')
    failed = next((e for e in task['experiments'] if e['classification'] == 'target_failure'), None)
    if failed:
        run = root / 'runs' / failed['id']
        (root / 'reproduce.py').write_bytes((run / 'test_regression.py').read_bytes())
        (root / 'environment.json').write_bytes((run / 'environment.json').read_bytes())
    files = [p for p in root.rglob('*') if p.is_file() and p.name not in {'SHA256SUMS', '.run.lock'} and '.tmp' not in p.name]
    (root / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n' for p in sorted(files)))


def bundle(root, task):
    """Portable frozen mock reproducer and bounded evidence; omit home/cache/locks."""
    import io
    import tarfile
    if task['state'] in {'queued', 'running'}:
        from triton_dev.common.contracts import ToolError
        raise ToolError('NOT_READY', 'Stop the investigation before exporting a consistent bundle')
    names = ['task.json', 'report.json', 'report.md', 'report.html', 'inventory.json',
             'reproduce.py', 'environment.json']
    for experiment in task['experiments']:
        names.extend(f"runs/{experiment['id']}/{name}" for name in [
            'request.json', 'result.json', 'environment.json', 'stages.json', 'test_regression.py', 'conftest.py'])
    files = {name: (root / name).read_bytes() for name in names if (root / name).is_file()}
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())).encode()
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    return result.getvalue()

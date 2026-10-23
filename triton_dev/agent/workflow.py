"""Resumable offline agent. Models choose registered recipe IDs, never argv or shell."""
import hashlib
import json
import math
import time

from triton_dev.common.contracts import ToolError, atomic_json, file_lock
from triton_dev.execution.records import execute_record


def conclusion(observations, minimum=2):
    good = [x['classification'] for x in observations.values() if x['role'] == 'good']
    bad = [x['classification'] for x in observations.values() if x['role'] == 'bad']
    if good and any(x != 'passed' for x in good):
        return 'baseline_invalid'
    if len(good) >= minimum and len(bad) >= minimum and all(x == 'passed' for x in good) and all(x == 'target_failure' for x in bad):
        return 'change_associated'
    return 'insufficient_evidence'


def run_workflow(model, store, checkpoint, recipes, predicate, *, max_turns=12,
                 max_experiments=6, max_seconds=600):
    if (not 1 <= max_turns <= 100 or not 1 <= max_experiments <= 100
            or not math.isfinite(max_seconds) or not 0 < max_seconds <= 3600):
        raise ToolError('INVALID_ARGUMENT', 'Invalid workflow budget')
    if not isinstance(recipes, dict) or not recipes:
        raise ToolError("INVALID_RECIPE", "A nonempty recipe registry is required")
    for name, recipe in recipes.items():
        if (not isinstance(name, str) or not isinstance(recipe, dict) or recipe.get('role') not in {'good', 'bad'}
                or not isinstance(recipe.get('request'), dict)
                or not 0 < recipe['request'].get('timeout', 300) <= 300):
            raise ToolError('INVALID_RECIPE', 'Named good/bad recipes with timeout <=300 required')
    fingerprint = hashlib.sha256(json.dumps({'recipes': recipes, 'predicate': predicate.__dict__}, sort_keys=True).encode()).hexdigest()
    with file_lock(checkpoint.with_suffix('.lock')):
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
            'schema_version': 1, 'fingerprint': fingerprint, 'turns': 0, 'experiments': 0,
            'observations': {}, 'state': 'ready', 'elapsed': 0, 'pending': None}
        if state.get('schema_version') != 1 or state['fingerprint'] != fingerprint:
            raise ToolError('WORKFLOW_CHANGED', 'Recipe or predicate differs from checkpoint')
        if state['state'] == 'finished':
            return state
        started = time.monotonic()
        elapsed_before = state['elapsed']
        def persist():
            state['elapsed'] = elapsed_before + time.monotonic() - started
            atomic_json(checkpoint, state)
        if state['pending']:
            pending = state['pending']
            record = store.read(pending['run_id'])
            if record['state'] in {'queued', 'running'}:
                # Never automatically re-execute an interrupted side effect.
                store.update(record['id'], state='interrupted')
                record = store.read(record['id'])
            state['observations'][pending['id']] = {
                'run_id': record['id'], 'role': recipes[pending['id']]['role'],
                'classification': predicate.classify(record)}
            state['pending'] = None
            persist()
        while state['turns'] < max_turns and state['elapsed'] < max_seconds:
            state['turns'] += 1
            persist()  # Charge the turn before calling a provider.
            message = model.respond({'schema_version': 1, 'observations': state['observations'],
                                     'remaining_experiments': max_experiments - state['experiments'],
                                     'allowed_recipe_ids': [k for k in recipes if k not in state['observations']]})
            if not isinstance(message, dict) or set(message) - {'action', 'recipe_id', 'evidence_ids', 'conclusion', 'question'}:
                raise ToolError('MODEL_PROTOCOL_ERROR', 'Unexpected workflow message')
            refs = message.get('evidence_ids', [])
            if not isinstance(refs, list) or any(not isinstance(r, str) or r not in state['observations'] for r in refs):
                raise ToolError('UNKNOWN_EVIDENCE', 'Unknown workflow evidence')
            action = message.get('action')
            fields = {'experiment': {'action', 'recipe_id', 'evidence_ids'},
                      'finish': {'action', 'conclusion', 'evidence_ids'},
                      'ask_user': {'action', 'question', 'evidence_ids'}}
            if not isinstance(action, str) or action not in fields or set(message) - fields[action]:
                raise ToolError('MODEL_PROTOCOL_ERROR', 'Invalid action fields')
            if action == 'finish':
                determined = conclusion(state['observations'])
                if message.get('conclusion') != determined or set(refs) != set(state['observations']):
                    raise ToolError('FINISH_REJECTED', 'Conclusion and references must match executed evidence')
                state.update(state='finished', conclusion=determined, scope='registered_experiments')
                persist()
                return state
            if action == 'ask_user':
                if not isinstance(message.get('question'), str) or not message['question'].strip():
                    raise ToolError('MODEL_PROTOCOL_ERROR', 'Question required')
                state.update(state='needs_input', question=message['question'])
                persist()
                return state
            if (action != 'experiment' or not isinstance(message.get('recipe_id'), str)
                    or message['recipe_id'] not in recipes):
                raise ToolError('ACTION_NOT_ALLOWED', 'Choose a pre-registered recipe ID')
            recipe_id = message['recipe_id']
            if recipe_id in state['observations']:
                raise ToolError('NO_PROGRESS', 'Recipe already executed; register repetitions explicitly')
            if state['experiments'] >= max_experiments:
                break
            recipe = recipes[recipe_id]
            request = dict(recipe['request'])
            remaining = max_seconds - (elapsed_before + time.monotonic() - started)
            if remaining <= 0:
                break
            request['timeout'] = min(request.get('timeout', 300), remaining)
            run_id = store.create(request)
            state['experiments'] += 1
            state['pending'] = {'id': recipe_id, 'run_id': run_id}
            persist()
            record = execute_record(store, run_id)
            state['observations'][recipe_id] = {'run_id': run_id, 'role': recipe['role'],
                                               'classification': predicate.classify(record)}
            state['pending'] = None
            persist()
        state.update(state='stopped', reason='budget_exhausted', conclusion=conclusion(state['observations']))
        persist()
        return state

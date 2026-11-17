"""Opt-in wall-clock instrumentation of the unchanged v15.4 engine.

The AST transform adds context managers only; no detector/training expressions
or RNG calls are replaced. Exclusive nested timers avoid double counting trap
generation inside scheduling. Canonical engine files remain byte-for-byte intact.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import csv
import hashlib
import io
from pathlib import Path
import time

from atomic_io import atomic_write_text

SEGMENTS = (
    'honest_training_seconds', 'fabrication_seconds', 'client_evaluation_seconds',
    'trap_generation_seconds', 'scheduling_seconds', 'model_preparation_seconds',
    'feature_seconds', 'decision_seconds', 'aggregation_seconds',
    'evaluation_seconds', 'response_bookkeeping_seconds', 'reporting_seconds',
    'checkpoint_seconds',
)
COMPUTE = SEGMENTS[:10]


def read_rows(path):
    if not path.is_file():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows):
    if not rows:
        return
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, stream.getvalue())


class RoundTimer:
    def __init__(self, path, completed=0, clock=time.perf_counter):
        self.path, self.clock = Path(path), clock
        self.rows = [r for r in read_rows(self.path) if int(r['round']) <= completed]
        self.stack = []
        self.publication_seconds = 0.
        self.started = clock()
        self.setup_seconds = None

    def begin(self, index):
        if self.setup_seconds is None:
            self.setup_seconds = self.clock() - self.started
        self.index, self.start = index, self.clock()
        self.values = dict.fromkeys(SEGMENTS, 0.)
        self.stack = []

    @contextmanager
    def segment(self, name):
        start = self.clock()
        frame = [name, 0.]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = self.clock() - start
            self.stack.pop()
            self.values[name] += elapsed - frame[1]
            if self.stack:
                self.stack[-1][1] += elapsed

    def finish(self, local):
        elapsed = self.clock() - self.start
        accounted = sum(self.values.values())
        if accounted > elapsed + 1e-6:
            raise RuntimeError('Timing segments overlap')
        row = dict(round=self.index, phase=local['mode'], active_clients=len(local['active_start']),
                   decision_boundary=int(bool(local.get('cycle_completed')) or local['mode']=='single_audit'),
                   honest_training_clients=sum(c not in local['truth'] for c in local['active_start']),
                   num_trapped=len(local['trapped']), num_aggregated=len(local['aggregated']),
                   global_accuracy=local['metrics']['accuracy'], **self.values,
                   unassigned_seconds=max(0., elapsed-accounted),
                   round_compute_seconds=sum(self.values[k] for k in COMPUTE),
                   observed_round_wall_seconds=elapsed)
        self.rows.append(row)
        # Timing-file publication itself is excluded and recorded separately.
        start = self.clock()
        write_rows(self.path, self.rows)
        self.publication_seconds += self.clock()-start


def _with(name, statements):
    return ast.With(items=[ast.withitem(context_expr=ast.Call(
        func=ast.Attribute(value=ast.Name(id='_segment_timer', ctx=ast.Load()),
                           attr='segment', ctx=ast.Load()),
        args=[ast.Constant(name)], keywords=[]))], body=statements)


def _target(node):
    if not isinstance(node, ast.Assign):
        return ''
    target = node.targets[0]
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Tuple):
        return ','.join(n.id for n in target.elts if isinstance(n, ast.Name))
    return ''


def _client_loop(loop):
    result = []
    for node in loop.body:
        target = _target(node)
        text = ast.unparse(node)
        if isinstance(node, ast.If) and ast.unparse(node.test) == 'c in truth':
            node.body = [_with('fabrication_seconds' if _target(n) == 'returned'
                               else 'client_evaluation_seconds', [n]) for n in node.body]
            node.orelse = [_with('honest_training_seconds', node.orelse)]
            result.append(node)
            continue
        if target in {'sent', 'identity'} or (isinstance(node, ast.If) and 'identity not in fingerprints' in text):
            category = 'model_preparation_seconds'
        elif (target in {'delta', 'norm', 'profile', 'sendback'} or text.startswith('previous_sent[')
              or (isinstance(node, ast.If) and 'Nonfinite client response' in text)):
            category = 'feature_seconds'
        else:
            category = 'response_bookkeeping_seconds'
        result.append(_with(category, [node]))
    loop.body = result
    return loop


def instrumented_engine(timer):
    """Return an instrumented callable plus reproducible transform provenance."""
    import train_v15_4 as engine
    path = Path(engine.__file__)
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_experiment')
    loop = next(n for n in function.body if isinstance(n, ast.For)
                and isinstance(n.target, ast.Name) and n.target.id == 'round_index')
    assert sum(isinstance(n, ast.For) and ast.unparse(n.target) == 'c' for n in loop.body) == 1
    original_body = list(loop.body)
    body = []
    for node in original_body:
        target, text = _target(node), ast.unparse(node)
        if target == 'round_start':
            body.extend([node, ast.parse('_segment_timer.begin(round_index)').body[0]])
            continue
        if isinstance(node, ast.For) and ast.unparse(node.target) == 'c':
            body.append(_client_loop(node))
            continue
        if target in {'active_start', 'monitored_start', 'quarantined_start', 'mode', 'trapped', 'trap', 'group_lookup'} or (
                isinstance(node, ast.If) and text.startswith('if round_index > config.warmup_rounds')):
            category = 'scheduling_seconds'
        elif target in {'base_state', 'returned_for_aggregation', 'aggregated', 'fingerprints'}:
            category = 'model_preparation_seconds'
        elif target in {'new_removals', 'new_removals,new_rehabilitations', 'cycle_completed'} or (
                isinstance(node, ast.If) and text.startswith('if cycle_completed:')):
            category = 'decision_seconds'
        elif target == 'global_state' or text.startswith('model.load_state_dict('):
            category = 'aggregation_seconds'
        elif target == 'metrics':
            category = 'evaluation_seconds'
        elif isinstance(node, ast.If) and ast.unparse(node.test) == 'config.save_checkpoints':
            node.body = [_with('checkpoint_seconds', node.body)]
            body.append(node)
            continue
        elif isinstance(node, ast.For):
            category = 'response_bookkeeping_seconds'
        else:
            category = 'reporting_seconds'
        body.append(_with(category, [node]))
    body.extend(ast.parse('_segment_timer.finish(locals())').body)
    loop.body = body
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    transformed = ast.unparse(module)
    namespace = dict(engine.__dict__)
    namespace['_segment_timer'] = timer
    original_trap = engine.make_trap_state

    def timed_trap(*args, **kwargs):
        with timer.segment('trap_generation_seconds'):
            return original_trap(*args, **kwargs)

    namespace['make_trap_state'] = timed_trap
    exec(compile(module, str(path), 'exec'), namespace)
    provenance = dict(engine_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        transformed_function_sha256=hashlib.sha256(transformed.encode()).hexdigest(),
        instrumentation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        description='AST context managers only; canonical source files untouched; exclusive nested wall timers',
        segments=list(SEGMENTS), compute_segments=list(COMPUTE),
        communication='Not measured: local simulation, no network transport',
        publication='Instrumentation CSV writes excluded from round timers and separately accumulated')
    return namespace['run_experiment'], provenance

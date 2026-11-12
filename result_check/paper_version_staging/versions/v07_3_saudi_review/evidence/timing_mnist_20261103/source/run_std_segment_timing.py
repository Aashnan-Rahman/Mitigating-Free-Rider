"""Instrument the unchanged full-vector STD-DAGMM workflow, including I/O.

Lin et al. specify the features/joint objective, not fitting epochs or reset
frequency. Five fresh epochs, Adam .001, batch20 and the FRIDA-described
128/64/32 K3 architecture remain explicit reproduction choices, not author code.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

import torch
import segment_timing
from atomic_io import atomic_write_json
import run_std_dagmm_long as core
from segment_timing import RoundTimer, read_rows, write_rows, _with


class StdTimer(RoundTimer):
    def finish_std(self, local):
        elapsed = self.clock()-self.start
        row = dict(local['row'])
        compute = float(row['round_compute_seconds'])
        io = self.values['checkpoint_seconds'] + self.values['reporting_seconds']
        if compute + io > elapsed + 1e-5:
            raise RuntimeError('STD timing segments overlap')
        # The canonical loop deliberately frees `details` before this boundary.
        fitting = json.loads((local['out']/f'detector_round_{self.index:02d}.json').read_text())['fit_details']
        row.update(checkpoint_seconds=self.values['checkpoint_seconds'],
            reporting_seconds=self.values['reporting_seconds'],
            unassigned_seconds=max(0., elapsed-compute-io),
            observed_round_wall_seconds=elapsed,
            joint_training_seconds=sum(fitting['epoch_seconds']),
            mixture_finalization_seconds=fitting['mixture_finalization_seconds'],
            detector_epochs=len(fitting['epoch_seconds']),
            first_training_objective=fitting['training_loss'][0],
            last_training_objective=fitting['training_loss'][-1])
        self.rows.append(row)
        start = self.clock()
        write_rows(self.path, self.rows)
        self.publication_seconds += self.clock()-start


def instrumented_std(timer):
    source = Path(core.__file__).read_text()
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    loop = next(n for n in function.body if isinstance(n, ast.For) and ast.unparse(n.target) == 'round_index')
    body = ast.parse('_segment_timer.begin(round_index)').body
    for node in loop.body:
        text = ast.unparse(node)
        body.append(_with('checkpoint_seconds', [node]) if text.startswith('checkpoint(')
                    else _with('reporting_seconds', [node]) if text.startswith(('dump_csv(', 'publish_status(', 'print('))
                    else node)
    body.extend(ast.parse('_segment_timer.finish_std(locals())').body)
    loop.body = body
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(core.__dict__, _segment_timer=timer)
    original_load = core.load_checkpoint

    def measured_checkpoint(path, protocol):
        saved = original_load(path, protocol)
        limit = int(timer.rows[-1]['round']) if timer.rows else 0
        if saved is None or saved['round'] <= limit:
            return saved
        backup = Path(path).with_name('previous_checkpoint.pt')
        prior = torch.load(backup, map_location='cpu', weights_only=False)
        if prior['protocol'] != protocol or prior['round'] > limit:
            raise RuntimeError('No checkpoint matches the published segment timings')
        temporary = Path(path).with_name('.timing_recovered.pt.tmp')
        shutil.copyfile(backup, temporary)
        temporary.replace(path)
        return prior

    namespace['load_checkpoint'] = measured_checkpoint
    exec(compile(module, core.__file__, 'exec'), namespace)
    return namespace['run'], dict(
        canonical_source_sha256=hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
        instrumentation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_instrumentation_sha256=hashlib.sha256(Path(segment_timing.__file__).read_bytes()).hexdigest(),
        transformed_function_sha256=hashlib.sha256(ast.unparse(module).encode()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    args.dataset, args.distribution, args.attack = 'mnist', 'noniid', 'FR3'
    args.free_rider_pct, args.clients, args.local_epochs = .4, 100, 3
    args.threads, args.detector_epochs, args.detector_batch = 6, 5, 20
    args.resume = (args.output/'protocol.json').is_file()
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    rows = read_rows(args.output/'segment_timings.csv')
    timer = StdTimer(args.output/'segment_timings.csv', len(rows))
    run, protocol = instrumented_std(timer)
    protocol.update(seed=args.seed, rounds=args.rounds, detector_epochs=args.detector_epochs,
        note='Core STD-DAGMM features/objective match Lin et al.; fitting budget/reset schedule and architecture are declared reproduction choices')
    # The canonical runner refuses pre-existing JSON in a fresh output. Keep
    # instrumentation provenance beside it without weakening that safety guard.
    path = args.output.parent/'std_segment_protocol.json'
    if path.is_file() and json.loads(path.read_text()) != protocol:
        raise RuntimeError('STD instrumentation/config changed; use a fresh output')
    atomic_write_json(path, protocol)
    if not (len(rows) == args.rounds and (args.output/'summary.json').is_file()):
        run(args)
    rows = read_rows(args.output/'segment_timings.csv')
    if [int(r['round']) for r in rows] != list(range(1, args.rounds+1)):
        raise RuntimeError('STD segment timing rounds incomplete')
    atomic_write_json(args.output/'timing_summary.json', dict(state='completed', completed_rounds=len(rows),
        measured=True, setup_seconds=timer.setup_seconds,
        instrumentation_publication_seconds_this_invocation=timer.publication_seconds, protocol=protocol))

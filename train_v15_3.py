"""Isolated v15.3 engine, preserving active v15.1/v15.2 checkpoint source hashes.

Training, RNG streams, trap scheduling and aggregation are mechanically copied
from train_v15.py. Only backend selection and provenance differ.
"""
import json
import hashlib
import math
import random
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from torch import nn

import train as shared
from atomic_io import atomic_write_json
from clients.attacks import FreeRiderAttacker, flatten_delta
from logging_utils import RunLogger
from server.aggregation import clone_state, fedavg_delta, make_trap_state
from server.model_fingerprint import model_fingerprint
from server.paired_challenges import derive_seed, stream_seeds
from server.v15_protocol import CycleState, REVISION, policy, build_schedule, measurements, screen, audit_anomalies


def _resume_config(config):
    return {k: v for k, v in config.to_dict().items()
            if k not in ("run_name", "output_dir", "resume_checkpoint", "num_rounds")}


def run_experiment(config, progress_callback=None):
    config.validate()
    if config.methodology_version != "swtcp_v15_3":
        raise ValueError("This isolated engine requires swtcp_v15_3")
    import server.v15_strict_norm as backend
    CycleState, REVISION, policy = backend.CycleState, backend.REVISION, backend.policy
    build_schedule, measurements = backend.build_schedule, backend.measurements
    screen, audit_anomalies = backend.screen, backend.audit_anomalies
    wall_start = time.perf_counter()
    run_name = config.resolved_run_name()
    logger = RunLogger(config, run_name)
    device = shared.resolve_device(config.device)
    seeds = stream_seeds(config)
    source_root = Path(__file__).resolve().parent
    source_names = ["server/v15_protocol.py", "server/diagonal_decision.py",
                    "server/v15_evidence.py", "server/v15_strict_norm.py", "train_v15_3.py"]
    source_hashes = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest() for name in source_names}
    protocol = {"policy": policy(), "settings": _resume_config(config), "seeds": seeds,
                "implementation_sha256": source_hashes}
    shared.set_global_seed(seeds["model"])
    train_set, test_set = shared.get_datasets(config)
    partitions = shared.partition_dataset(train_set, replace(config, seed=seeds["partition"]))
    loaders = [shared.make_client_loader(train_set, indices, config,
               derive_seed(seeds["training"], f"loader:{c}")) for c, indices in enumerate(partitions)]
    eval_loader = shared.make_eval_loader(config, test_set)
    model = shared.get_model(config.dataset).to(device)
    global_state = clone_state(model.state_dict())
    loss_fn = nn.CrossEntropyLoss()
    attack_rng = torch.Generator(device=device).manual_seed(seeds["attack"])
    schedule_rng = random.Random(seeds["schedule"])
    attacker = FreeRiderAttacker(config, device)
    # Simulator-only identities. Never passed to schedule/screen/CycleState.
    truth = set(random.Random(seeds["attacker_selection"]).sample(
        range(config.num_clients), math.ceil(config.free_rider_pct * config.num_clients)))
    extra_settings = dict(review_cycles=config.v15_candidate_review_cycles,
                          cooldown_cycles=config.v15_candidate_cooldown_audits) if config.methodology_version == "swtcp_v15_3" else {}
    state = CycleState(range(config.num_clients), config.cycle_strong_cycles_for_removal,
                       max(config.cycle_suspect_clean_cycles, config.cycle_candidate_clean_cycles),
                       config.cycle_reference_probation_cycles, **extra_settings)
    cycle = 0
    schedule = None
    cycle_start = None
    trap_states = {}
    selected = {}
    previous_sent = {}
    quiet_since = None
    start_round = 1
    prior_elapsed = 0.
    peak_rss = 0.
    started_at = datetime.now().isoformat()
    if config.resume_checkpoint:
        checkpoint = torch.load(config.resume_checkpoint, map_location=device, weights_only=False)
        if checkpoint["protocol"] != protocol:
            raise ValueError("v15 resume settings or decision policy changed")
        completed = int(checkpoint["round"])
        if completed >= config.num_rounds:
            raise ValueError("Checkpoint already reached the configured horizon")
        start_round = completed + 1
        state.load_state_dict(checkpoint["state"])
        global_state = clone_state(checkpoint["global_state"])
        cycle, schedule, cycle_start = checkpoint["cycle"], checkpoint["schedule"], checkpoint["cycle_start"]
        trap_states, selected = checkpoint["trap_states"], checkpoint["selected"]
        previous_sent, quiet_since = checkpoint["previous_sent"], checkpoint["quiet_since"]
        truth = set(checkpoint["ground_truth"])
        attacker.load_state_dict(checkpoint["attacker"])
        attack_rng.set_state(checkpoint["attack_rng"].cpu())
        schedule_rng.setstate(checkpoint["schedule_rng"])
        for loader, generator_state in zip(loaders, checkpoint["loaders"]):
            loader.generator.set_state(generator_state.cpu())
        random.setstate(checkpoint["random_rng"])
        np.random.set_state(checkpoint["numpy_rng"])
        torch.set_rng_state(checkpoint["torch_rng"].cpu())
        if device.type == "cuda":
            torch.cuda.set_rng_state_all([s.cpu() for s in checkpoint["cuda_rng"]])
        prior_elapsed, peak_rss = checkpoint["elapsed"], checkpoint["peak_rss"]
        started_at = checkpoint["started_at"]
        logger.load_existing(completed, checkpoint["global_metrics"])
    atomic_write_json(logger.run_dir / "protocol.json", protocol)

    for round_index in range(start_round, config.num_rounds + 1):
        round_start = time.perf_counter()
        active_start = state.active
        monitored_start = state.monitored.copy()
        quarantined_start = getattr(state, "quarantined", state.monitored).copy()
        mode = "warmup" if round_index <= config.warmup_rounds else "idle"
        trapped = set()
        trap = None
        group_lookup = {}
        if round_index > config.warmup_rounds and active_start:
            if schedule is None:
                if cycle == 0 or state.monitored or state.pending_probation:
                    schedule = build_schedule(active_start, state.monitored, schedule_rng,
                                              config.surveillance_groups, config.v15_cycle_rounds,
                                              initial=(cycle == 0))
                    cycle_start = round_index
                    selected = {}
                    trap_rng = torch.Generator(device=device).manual_seed(
                        derive_seed(seeds["trap"], f"cycle:{cycle}"))
                    trap_states = {t: make_trap_state(global_state, config.trap_noise_scale,
                                   config.trap_noise_floor, trap_rng) for t in (0, 1)}
                    for gid, (role, clients) in enumerate(schedule["groups"]):
                        for c in clients:
                            logger.cycle_group_rows.append(dict(round=round_index, cycle=cycle,
                                client_id=c, group_id=gid, role=role, pool_size=len(clients)))
            if schedule is not None:
                mode = "double_probe" if cycle == 0 else "confirmation"
                offset = round_index - cycle_start
                trap, members = schedule["assignments"][offset]
                trapped = set(members)
                group_lookup = {c: gid for gid, (_, members) in enumerate(schedule["groups"]) for c in members}
            elif quiet_since is not None and round_index - quiet_since >= config.v15_audit_interval_rounds:
                mode = "single_audit"
                trap = 0
                trapped = set(active_start)
                selected = {}
                trap_rng = torch.Generator(device=device).manual_seed(
                    derive_seed(seeds["trap"], f"audit:{round_index}"))
                trap_states = {0: make_trap_state(global_state, config.trap_noise_scale,
                               config.trap_noise_floor, trap_rng)}

        base_state = clone_state(global_state)
        returned_for_aggregation = []
        aggregated = set()
        fingerprints = {}
        for c in active_start:
            sent = trap_states[trap] if c in trapped else base_state
            identity = id(sent)
            if identity not in fingerprints:
                fingerprints[identity] = model_fingerprint(sent)
            if c in truth:
                returned = attacker.fabricate(c, sent, round_index, attack_rng)
                local = shared.evaluate_state_on_loader(model, returned, loaders[c], loss_fn, device, config)
            else:
                shared.set_global_seed(derive_seed(seeds["training"], f"client:{c}:round:{round_index}"))
                returned, local = shared.train_local_model(model, sent, loaders[c], loss_fn, device, config)
            delta = flatten_delta(returned, sent)
            norm = float(delta.norm())
            profile = shared.build_layer_profile(returned, sent, config.zero_update_epsilon)
            if not math.isfinite(norm) or not torch.isfinite(profile).all():
                raise ValueError("Nonfinite client response; cycle not certified")
            sendback = norm == 0 or model_fingerprint(returned) == previous_sent.get(c)
            previous_sent[c] = fingerprints[identity]
            selected_probe = c in trapped and (mode == "single_audit" or
                schedule["selected"][c][trap] == round_index - cycle_start)
            if selected_probe:
                selected.setdefault(c, {})[trap] = dict(norm=norm, profile=profile.detach().cpu().tolist(),
                                                       round=round_index, sendback=bool(sendback))
            if c in trapped:
                logger.cycle_probe_rows.append(dict(round=round_index, cycle=cycle, client_id=c,
                    trap_id=trap, group_id=group_lookup.get(c, "audit"), selected_for_decision=int(selected_probe),
                    delta_norm=norm, layer_profile=json.dumps(profile.detach().cpu().tolist()),
                    exact_sendback=int(sendback), is_free_rider=int(c in truth)))
                logger.trap_assignment_rows.append(dict(round=round_index, client_id=c, phase=mode,
                    role="monitored" if c in monitored_start else "R", group_id=group_lookup.get(c, "audit")))
            allowed = c not in trapped and c not in quarantined_start
            if allowed:
                returned_for_aggregation.append((c, returned))
                aggregated.add(c)
            logger.client_rows.append(dict(round=round_index, client_id=c, is_free_rider=int(c in truth),
                was_active=1, was_trapped=int(c in trapped), was_quarantined=int(c in quarantined_start),
                was_aggregated=int(allowed), delta_norm=norm, exact_sendback=int(sendback),
                local_accuracy=local["accuracy"], local_loss=local["loss"], detection_observation_round=round_index,
                norm_z_score="", profile_z_score="", flagged=0, joint_flag_count=0))
        new_removals = new_rehabilitations = 0
        cycle_completed = schedule is not None and round_index - cycle_start == config.v15_cycle_rounds - 1
        if cycle_completed:
            if any(set(selected.get(c, {})) != {0, 1} for c in active_start):
                raise ValueError("Incomplete A/B coverage: no cycle can authorize removal")
            signals = measurements(selected, active_start, round_index)
            decisions, metadata = screen(signals, round_index)
            events = state.apply(decisions, cycle, round_index)
            logger.cycle_signal_rows.extend({**r, "is_free_rider": int(r["client_id"] in truth)} for r in signals)
            logger.cycle_decision_rows.extend({**d, "cycle": cycle, "is_free_rider": int(d["client_id"] in truth)} for d in decisions)
            logger.cycle_policy_rows.append(dict(round=round_index, cycle=cycle, policy=json.dumps(metadata)))
            for event in events:
                c = event["client_id"]
                if event["event"] == "remove":
                    new_removals += 1
                    logger.removal_rows.append(dict(round=round_index, client_id=c, is_free_rider=int(c in truth),
                        final_penalty=0, removal_basis=event["reason"], zero_update_count=0,
                        suspicion_probes=state.records[c]["strong"]))
                    aggregated.discard(c)
                elif event["event"] == "rehabilitate":
                    new_rehabilitations += 1
                    logger.rehabilitation_rows.append(dict(round=round_index, client_id=c,
                        is_free_rider=int(c in truth), cleared_magnitude_penalty=0,
                        remaining_penalty=0, probes=2, flags=0, dodge_index=0))
                else:
                    logger.candidate_event_rows.append(dict(round=round_index, client_id=c,
                        is_free_rider=int(c in truth), event=event["event"], reason=event["reason"], cumulative_penalty=0))
            # Newly flagged responses are excluded even on their decision round.
            excluded_at_decision = getattr(state, "quarantined", state.monitored) | (set(active_start) - set(state.active))
            aggregated -= excluded_at_decision
            cycle += 1
            schedule, cycle_start, selected, trap_states = None, None, {}, {}
            quiet_since = round_index if not state.monitored and not state.pending_probation else None
        elif mode == "single_audit":
            signals = measurements(selected, active_start, round_index, traps=(0,))
            anomalies, reason = audit_anomalies(signals)
            state.escalate_audit(anomalies)
            logger.cycle_signal_rows.extend({**r, "is_free_rider": int(r["client_id"] in truth)} for r in signals)
            logger.cycle_policy_rows.append(dict(round=round_index, cycle=cycle,
                policy=json.dumps({"mode": "single_audit", "reason": reason, "escalations": len(anomalies)})))
            quiet_since = round_index if not anomalies else None
            selected, trap_states = {}, {}
        for row in logger.client_rows[-len(active_start):] if active_start else []:
            row["was_aggregated"] = int(row["client_id"] in aggregated)
        logger.log_trap_matrix_row(round_index, mode, trapped, config.num_clients)
        global_state = fedavg_delta(base_state, [response for c, response in returned_for_aggregation if c in aggregated])
        model.load_state_dict(global_state)
        metrics = shared.evaluate_model(model, eval_loader, loss_fn, device)
        resources = shared.resource_snapshot(device)
        peak_rss = max(peak_rss, float(resources.get("process_rss_mb") or 0))
        suspected = sum(r["category"] == "S" for r in state.records.values())
        candidates = sum(r["category"] == "C" for r in state.records.values())
        logger.global_rows.append(dict(round=round_index, global_accuracy=metrics["accuracy"], global_loss=metrics["loss"],
            num_active_clients=len(state.active), num_suspected_clients=suspected, num_candidate_clients=candidates,
            num_trapped=len(trapped), num_aggregated=len(aggregated), new_removals=new_removals,
            new_rehabilitations=new_rehabilitations, phase=mode, cycle=cycle,
            round_time_seconds=time.perf_counter() - round_start, **resources))
        detection = shared.build_detection_summary(config, truth, state.active)
        logger.summary_rows = [detection]
        elapsed = prior_elapsed + time.perf_counter() - wall_start
        run_config = {**config.to_dict(), **detection, "run_name": run_name, "started_at": started_at,
            "device_resolved": str(device), "detector_revision": REVISION, "protocol": protocol,
            "completed_rounds": round_index, "total_wall_clock_seconds": elapsed,
            "final_global_accuracy": metrics["accuracy"], "final_global_loss": metrics["loss"],
            "final_suspected_clients": suspected, "final_candidate_clients": candidates,
            "best_global_accuracy": max(r["global_accuracy"] for r in logger.global_rows),
            "average_round_time_seconds": sum(r["round_time_seconds"] for r in logger.global_rows) / len(logger.global_rows),
            "peak_process_rss_mb": peak_rss, "detector_uses_attack_history": False,
            "statistical_decisions_enabled": True,
            "quarantined_clients": len(getattr(state, "quarantined", state.monitored)),
            "intensively_monitored_clients": len(state.monitored),
            "final_honest_candidate_clients": sum(c not in truth and r["category"] == "C" for c, r in state.records.items())}
        new_flags = sum(d["state"] == "S" for d in decisions) if cycle_completed else 0
        logger.detection_round_rows.append(dict(round=round_index, evaluated_clients=config.num_clients,
            true_positives=detection["removed_free_riders"], false_positives=detection["removed_honest_clients"],
            true_negatives=config.num_clients - len(truth) - detection["removed_honest_clients"],
            false_negatives=detection["missed_free_riders"], detection_accuracy=detection["detection_accuracy"],
            precision=detection["precision"], recall=detection["recall"], f1=detection["f1"],
            false_positive_rate=detection["false_positive_removal_rate"], new_removals=new_removals,
            new_rehabilitations=new_rehabilitations, num_suspected=suspected, num_candidates=candidates))
        if config.save_checkpoints:
            checkpoint = dict(protocol=protocol, config=config.to_dict(), round=round_index, global_state=global_state,
                state=state.state_dict(), cycle=cycle, schedule=schedule, cycle_start=cycle_start,
                selected=selected, trap_states=trap_states, previous_sent=previous_sent, quiet_since=quiet_since,
                ground_truth=sorted(truth), attacker=attacker.state_dict(), attack_rng=attack_rng.get_state(),
                schedule_rng=schedule_rng.getstate(), loaders=[l.generator.get_state() for l in loaders],
                random_rng=random.getstate(), numpy_rng=np.random.get_state(), torch_rng=torch.get_rng_state(),
                cuda_rng=torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
                elapsed=elapsed, peak_rss=peak_rss, started_at=started_at, global_metrics=logger.global_rows[-1])
            shared.save_rolling_checkpoint(checkpoint, logger.run_dir, round_index, config.checkpoint_keep_last)
        logger.write_progress(round_index, run_config)
        if progress_callback:
            progress_callback(dict(round=round_index, total_rounds=config.num_rounds, phase=mode,
                methodology_version=config.methodology_version, device=str(device),
                active_clients=len(state.active), suspected_clients=suspected, candidate_clients=candidates,
                quarantined_clients=len(getattr(state, "quarantined", state.monitored)),
                global_accuracy=metrics["accuracy"], global_loss=metrics["loss"], new_flags=new_flags,
                new_removals=new_removals, new_rehabilitations=new_rehabilitations,
                round_time_seconds=logger.global_rows[-1]["round_time_seconds"], **resources))
    run_config["finished_at"] = datetime.now().isoformat()
    honest_rows = [r for r in logger.client_rows if r["is_free_rider"] == 0]
    run_config.update(honest_quarantine_client_rounds=sum(r["was_quarantined"] for r in honest_rows),
        honest_trap_client_rounds=sum(r["was_trapped"] for r in honest_rows),
        honest_excluded_active_client_rounds=sum(not r["was_aggregated"] for r in honest_rows),
        honest_clients_ever_quarantined=len({r["client_id"] for r in honest_rows if r["was_quarantined"]}))
    logger.write_completion(run_config, config.num_rounds)
    if config.save_checkpoints:
        shared.delete_successful_checkpoints(logger.run_dir)
    return str(logger.run_dir)


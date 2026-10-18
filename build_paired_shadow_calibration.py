"""Offline clean-control calibration; never select controls by detector flags."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from atomic_io import atomic_write_json
from server.paired_shadow import CONTEXT_FIELDS, feature_vector, window_vector, fit_artifact


def read_control(run: Path):
    config = json.loads((run / "run_config.json").read_text())
    latest = json.loads((run / "latest_results.json").read_text())
    if not latest.get("completed"):
        raise ValueError("Calibration control must be complete")
    if config["free_rider_pct"] != 0 or not config.get("paired_measurement_only"):
        raise ValueError("Calibration sources must be explicit honest-only paired controls")
    groups = {}
    raw = (run / "paired_responses.csv").read_bytes()
    with (run / "paired_responses.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["is_free_rider"]) != 0:
                raise ValueError("Attacker-containing data cannot calibrate this rule")
            groups.setdefault(int(row["client_id"]), []).append(row)
    vectors = []
    for rows in groups.values():
        rows.sort(key=lambda row: int(row["cycle"]))
        if [int(row["cycle"]) for row in rows] != [0, 1, 2]:
            raise ValueError("Every control client must have one complete three-cycle window")
        vectors.append(window_vector([feature_vector(row) for row in rows]))
    if len(vectors) != config["num_clients"]:
        raise ValueError("Incomplete control population")
    context = {key: config[key] for key in CONTEXT_FIELDS}
    return vectors, context, {"run": str(run.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}


def build(fit_run: Path, calibration_run: Path, output: Path, alpha: float):
    if fit_run.resolve() == calibration_run.resolve():
        raise ValueError("Fitting and calibration must be separate runs")
    fit, context, fit_source = read_control(fit_run)
    calibration, other_context, cal_source = read_control(calibration_run)
    if context != other_context or fit_source["sha256"] == cal_source["sha256"]:
        raise ValueError("Calibration must match the protocol and not duplicate fitting data")
    artifact = fit_artifact(fit, calibration, context=context, alpha=alpha,
                            provenance={"fit": fit_source, "calibration": cal_source})
    atomic_write_json(output, artifact)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alpha", type=float, default=.01)
    args = parser.parse_args()
    artifact = build(args.fit, args.calibration, args.output, args.alpha)
    print(json.dumps({key: artifact[key] for key in ("revision", "alpha", "fit_windows", "calibration_windows", "cutoff")}))

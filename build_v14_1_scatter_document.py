"""32 unsorted, per-trap norm-z/profile-z plots from v14.1 preliminary logs."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "analysis/v14_1_z_scatter"


def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    tex = [r"\documentclass[landscape,a4paper]{article}",
           r"\usepackage[margin=10mm]{geometry}", r"\usepackage{pgfplots}",
           r"\usepgfplotslibrary{groupplots}", r"\pgfplotsset{compat=1.18}",
           r"\pagestyle{empty}", r"\setlength{\parindent}{0pt}",
           r"\definecolor{honestblue}{RGB}{0,114,178}",
           r"\definecolor{riderorange}{RGB}{213,94,0}", r"\begin{document}"]
    provenance = []
    plot_count = 0
    for seed in (42, 43):
        for distribution in ("iid", "noniid"):
            if plot_count:
                tex.append(r"\newpage")
            partition = "IID" if distribution == "iid" else "Non-IID"
            tex += [f"{{\\Large\\bfseries V14.1 preliminary: seed {seed}, {partition}}}\\par",
                    r"\small MNIST, 100 clients, 40\% free riders; comparison at round 20.",
                    r"Each point is one client response. Blue circles: honest; orange triangles: free riders.",
                    r"\par\small No score sorting, jitter, fitted boundaries, or removals. Axes scale independently per panel.",
                    r"\par\vspace{2mm}\centering\begin{tikzpicture}",
                    r"\begin{groupplot}[group style={group size=4 by 2,horizontal sep=12mm,vertical sep=20mm},",
                    r"width=60mm,height=60mm,scale only axis=false,",
                    r"xlabel={Norm-z},ylabel={Profile-z},",
                    r"tick label style={font=\scriptsize},label style={font=\small},title style={font=\small},",
                    r"grid=major,major grid style={draw=gray!20},scaled ticks=false,",
                    r"ticklabel style={/pgf/number format/fixed,/pgf/number format/precision=2},",
                    r"unbounded coords=discard]"]
            sources = {}
            for attack in ("FR1", "FR2", "FR3", "FR4"):
                path = ROOT / f"results/v14_1_preli_mnist_seed{seed}_fr40/v14_1_preli_mnist_{distribution}_{attack}_seed{seed}/preliminary_signals.csv"
                with path.open(newline="", encoding="utf-8") as handle:
                    observations = list(csv.DictReader(handle))
                if len(observations) != 200:
                    raise ValueError(f"Expected 200 probe observations: {path}")
                sources[attack] = observations
                provenance.append({"seed": seed, "distribution": distribution, "attack": attack,
                    "source": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            for trap in (0, 1):
                for attack in ("FR1", "FR2", "FR3", "FR4"):
                    selected = [row for row in sources[attack] if int(row["trap_id"]) == trap]
                    if len(selected) != 100 or len({row["client_id"] for row in selected}) != 100:
                        raise ValueError("Incomplete/duplicate trap coverage")
                    name = f"seed{seed}_{distribution}_{attack}_trap{trap}"
                    valid = []
                    for row in selected:  # Preserve source order; never rank clients.
                        if row["norm_z"] == "" or row["profile_z"] == "":
                            continue
                        x, y = float(row["norm_z"]), float(row["profile_z"])
                        if not math.isfinite(x) or not math.isfinite(y):
                            raise ValueError("Nonfinite plotted score")
                        valid.append({"client_id": row["client_id"], "norm_z": x,
                                      "profile_z": y, "is_free_rider": int(row["is_free_rider"])})
                    if len(valid) != 100 or sum(row["is_free_rider"] for row in valid) != 40:
                        raise ValueError("Plot must contain all 60 honest and 40 free-rider responses")
                    for label, suffix in ((0, "honest"), (1, "riders")):
                        with (OUT / "data" / f"{name}_{suffix}.csv").open("w", newline="", encoding="utf-8") as handle:
                            writer = csv.DictWriter(handle, fieldnames=["client_id", "norm_z", "profile_z", "is_free_rider"])
                            writer.writeheader()
                            writer.writerows(row for row in valid if row["is_free_rider"] == label)
                    lo_x, hi_x = min(row["norm_z"] for row in valid), max(row["norm_z"] for row in valid)
                    lo_y, hi_y = min(row["profile_z"] for row in valid), max(row["profile_z"] for row in valid)
                    dx, dy = (hi_x - lo_x) * .12, (hi_y - lo_y) * .12
                    title = f"{attack} -- Trap {'A' if trap == 0 else 'B'}"
                    tex.append(f"\\nextgroupplot[title={{{title}}},xmin={lo_x-dx},xmax={hi_x+dx},ymin={lo_y-dy},ymax={hi_y+dy}]")
                    tex.append(r"\addplot[only marks,mark=*,mark size=1.5pt,honestblue,opacity=.8] table[x=norm_z,y=profile_z,col sep=comma]{data/" + name + r"_honest.csv};")
                    tex.append(r"\addplot[only marks,mark=triangle*,mark size=2pt,riderorange,opacity=.8] table[x=norm_z,y=profile_z,col sep=comma]{data/" + name + r"_riders.csv};")
                    plot_count += 1
            tex += [r"\end{groupplot}\end{tikzpicture}\par\vspace{2mm}",
                    r"\raggedright\footnotesize Top row: Trap A. Bottom row: Trap B. FR1's 40 exact-zero responses coincide at one location; no jitter is added.",
                    r"\par Labels are evaluation ground truth, not inputs to the reference statistics. Coincident markers may hide multiple clients."]
    tex.append(r"\end{document}")
    assert plot_count == 32 and len(provenance) == 16
    (OUT / "norm_profile_scatter.tex").write_text("\n".join(tex) + "\n", encoding="utf-8")
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (OUT / "README.md").write_text(
        "# V14.1 preliminary z-score scatter plots\n\n"
        "32 plots: two traps × four attacks × two partitions × two seeds.\n\n"
        "X: signed norm-z. Y: profile-z. Blue circles: 60 honest clients; orange triangles: 40 free riders.\n"
        "No averaging across traps, score sorting, jitter, or fitted decision thresholds.\n"
        "Four landscape pages: seed 42 IID, seed 42 non-IID, seed 43 IID, seed 43 non-IID.\n"
        "Rows distinguish traps A/B; columns distinguish FR1–FR4. Axes autoscale per panel.\n"
        "FR1 markers coincide because all 40 updates are exactly zero.\n\n"
        "Reproduce: run `python build_v14_1_scatter_document.py`, then compile `norm_profile_scatter.tex` with pdflatex in this folder.\n"
        "The data CSVs preserve original client order. Provenance includes source hashes.\n", encoding="utf-8")
    print(json.dumps({"plots": plot_count, "sources": len(provenance), "output": str(OUT)}))


if __name__ == "__main__":
    main()

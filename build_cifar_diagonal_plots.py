"""CIFAR seed-42 diagnostic plots, preserving client order and frozen rules."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BATCH = ROOT / "results/v14_1_preli_cifar10_diagonal_seed42_fr40"
OUT = ROOT / "analysis/v14_1_cifar_diagonal_scatter"


def load(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    tex = [r"\documentclass[landscape,a4paper]{article}",
           r"\usepackage[margin=10mm]{geometry}\usepackage{pgfplots}",
           r"\usepgfplotslibrary{groupplots}\pgfplotsset{compat=1.18}",
           r"\pagestyle{empty}\setlength{\parindent}{0pt}",
           r"\definecolor{honestblue}{RGB}{0,114,178}",
           r"\definecolor{riderorange}{RGB}{213,94,0}\begin{document}"]
    provenance = []
    for distribution in ("iid", "noniid"):
        if distribution == "noniid":
            tex.append(r"\newpage")
        partition = "IID" if distribution == "iid" else "Non-IID"
        tex += [f"{{\\Large\\bfseries CIFAR-10: {partition}, seed 42 -- per-trap signals}}\\par",
                r"\small Round 20; 100 clients; 40\% free riders. Blue circles: honest. Orange triangles: free riders.",
                r"\par Top: Trap A. Bottom: Trap B. No sorting or jitter; coincident points may hide clients.",
                r"\par\vspace{3mm}\centering\begin{tikzpicture}",
                r"\begin{groupplot}[group style={group size=4 by 2,horizontal sep=12mm,vertical sep=20mm},",
                r"width=60mm,height=62mm,xlabel={Norm-z},ylabel={Profile-z},grid=major,",
                r"major grid style={draw=gray!20},tick label style={font=\scriptsize},",
                r"label style={font=\small},title style={font=\small},scaled ticks=false]"]
        sources = {}
        for attack in ("FR1", "FR2", "FR3", "FR4"):
            path = BATCH / f"v14_1_preli_cifar10_diagonal_{distribution}_{attack}_seed42/preliminary_signals.csv"
            sources[attack] = load(path)
            assert len(sources[attack]) == 200
            provenance.append(dict(source=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for trap in (0, 1):
            for attack, rows in sources.items():
                selected = [r for r in rows if int(r["trap_id"]) == trap]
                assert len(selected) == 100 and len({r["client_id"] for r in selected}) == 100
                name = f"{distribution}_{attack}_trap{trap}"
                for flag, suffix in (("0", "honest"), ("1", "riders")):
                    subset = [r for r in selected if r["is_free_rider"] == flag]
                    assert len(subset) == (60 if flag == "0" else 40)
                    with (OUT / "data" / f"{name}_{suffix}.csv").open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=["client_id", "norm_z", "profile_z"])
                        writer.writeheader()
                        writer.writerows({k: r[k] for k in writer.fieldnames} for r in subset)
                tex.append(f"\\nextgroupplot[title={{{attack} -- Trap {'A' if trap == 0 else 'B'}}}]")
                for suffix, mark, color in (("honest", "*", "honestblue"), ("riders", "triangle*", "riderorange")):
                    tex.append(f"\\addplot[only marks,mark={mark},mark size=1.5pt,{color},opacity=.75] table[x=norm_z,y=profile_z,col sep=comma]{{data/{name}_{suffix}.csv}};")
        tex += [r"\end{groupplot}\end{tikzpicture}\par\raggedright\footnotesize",
                r"Axes scale independently. FR1's 40 identical exact-zero responses coincide. Labels are evaluation-only."]
    tex += [r"\newpage{\Large\bfseries CIFAR-10: combined decision score at round 20}\par",
            r"\small $D=(D_A+D_B)/2$, with $D_t=\mathrm{profile\mbox{-}z}_t-\mathrm{norm\mbox{-}z}_t$.",
            r"\par Blue: honest. Orange: free riders. Dashed lines: frozen rule's bootstrap lower/upper average-view boundaries.",
            r"\par Client IDs are unsorted. Decisions also require agreement on both trap views and the majority gate.",
            r"\par\vspace{3mm}\centering\begin{tikzpicture}",
            r"\begin{groupplot}[group style={group size=4 by 2,horizontal sep=12mm,vertical sep=20mm},",
            r"width=60mm,height=62mm,xlabel={Client ID},ylabel={Average D},grid=major,",
            r"major grid style={draw=gray!20},tick label style={font=\scriptsize},",
            r"label style={font=\small},title style={font=\small},scaled ticks=false]"]
    for distribution in ("iid", "noniid"):
        for attack in ("FR1", "FR2", "FR3", "FR4"):
            folder = BATCH / f"v14_1_preli_cifar10_diagonal_{distribution}_{attack}_seed42"
            rows = load(folder / "preliminary_decisions.csv")
            policy = json.loads((folder / "preliminary_decision_policy.json").read_text())
            title = f"{'IID' if distribution == 'iid' else 'Non-IID'} {attack}"
            if not policy["majority_gate"]:
                title += " (gate failed)"
            tex.append(f"\\nextgroupplot[title={{{title}}},xmin=-2,xmax=101]")
            for flag, suffix, mark, color in (("0", "honest", "*", "honestblue"), ("1", "riders", "triangle*", "riderorange")):
                name = f"{distribution}_{attack}_average_{suffix}.csv"
                with (OUT / "data" / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["client_id", "D_average"])
                    writer.writeheader()
                    writer.writerows({k: r[k] for k in writer.fieldnames} for r in rows if r["is_free_rider"] == flag)
                tex.append(f"\\addplot[only marks,mark={mark},mark size=1.5pt,{color},opacity=.75] table[x=client_id,y=D_average,col sep=comma]{{data/{name}}};")
            for key in ("lower", "upper"):
                value = policy["boundaries"][0][key]
                tex.append(f"\\addplot[gray,dashed,no marks] coordinates {{(0,{value}) (99,{value})}};")
    tex += [r"\end{groupplot}\end{tikzpicture}\par\raggedright\footnotesize",
            r"Non-IID FR3: everyone remains candidate because the lower-score cohort fails the majority check.",
            r"\par These plots do not tune thresholds and no clients were removed.\end{document}"]
    (OUT / "cifar_diagonal_scatter.tex").write_text("\n".join(tex), encoding="utf-8")
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"24 plots on 3 pages: {OUT}")


if __name__ == "__main__":
    main()

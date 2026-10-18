# V14.1 preliminary z-score scatter plots

32 plots: two traps × four attacks × two partitions × two seeds.

X: signed norm-z. Y: profile-z. Blue circles: 60 honest clients; orange triangles: 40 free riders.
No averaging across traps, score sorting, jitter, or fitted decision thresholds.
Four landscape pages: seed 42 IID, seed 42 non-IID, seed 43 IID, seed 43 non-IID.
Rows distinguish traps A/B; columns distinguish FR1–FR4. Axes autoscale per panel.
FR1 markers coincide because all 40 updates are exactly zero.

Reproduce: run `python build_v14_1_scatter_document.py`, then compile `norm_profile_scatter.tex` with pdflatex in this folder.
The data CSVs preserve original client order. Provenance includes source hashes.

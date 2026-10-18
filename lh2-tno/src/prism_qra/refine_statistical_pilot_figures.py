"""Refine presentation-only pilot figures without changing calculations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def refine(output: Path) -> None:
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    colors = ("#196b83", "#cc6b27", "#5b4794")
    measures = ("log_diameter", "linear_diameter")
    layouts = ("linear", "compact", "offset")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), sharey=True)
    fig.subplots_adjust(top=.78, bottom=.20, left=.07, right=.98, wspace=.03)
    x = np.arange(6)
    for ax, measure in zip(axes, measures):
        for i, layout in enumerate(layouts):
            values = summary["information"][measure][layout]["mean_possible_priority_sets"]
            ax.bar(x + (i - 1) * .24, values, width=.22, label=layout, color=colors[i])
        ax.set_xticks(x, ("None", "A", "B", "C", "D", "All"))
        ax.set(xlabel="Cd assumed known exactly", title=measure.replace("_", " "), ylim=(0, 2.7))
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Mean number of feasible top-set patterns")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.5, .04), ncols=3, frameon=False)
    fig.suptitle("Information sensitivity — A–D are one-at-a-time; All reveals four\n"
                 "Exact reach-pattern sets; NOT formal value of information", y=.96)
    path = output / "04_information_sensitivity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file() and p.name != "artifact_hashes.json"}
    (output / "artifact_hashes.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    refine(args.directory)

"""Visual-only refinement for the locked synthetic-transfer artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "논문" / "통계전이평가_20260901"
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    layouts = {
        **protocol["analysis_layouts"],
        **protocol["post_pilot_pre_evaluation_layouts"],
    }
    analysis_names = set(protocol["analysis_layouts"])
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 7.2), constrained_layout=True)
    for ax, (name, points) in zip(axes.ravel(), layouts.items()):
        xy = np.asarray(points, dtype=float)
        ax.scatter(xy[:, 0], xy[:, 1], s=45, color="#145a70")
        for i, (x, y) in enumerate(xy):
            ax.annotate("ABCD"[i], (x, y), xytext=(5, 5), textcoords="offset points")
        x_pad = max(np.ptp(xy[:, 0]) * .08, .12)
        y_pad = max(np.ptp(xy[:, 1]) * .12, .12)
        ax.set_xlim(xy[:, 0].min() - x_pad, xy[:, 0].max() + x_pad)
        if np.ptp(xy[:, 1]) < 1e-12:
            ax.set_ylim(-.35, .35)
            ax.set_yticks([0.])
        else:
            ax.set_ylim(xy[:, 1].min() - y_pad, xy[:, 1].max() + y_pad)
        ax.set(title=f"{name} ({'analysis' if name in analysis_names else 'transfer'})",
               xlabel="normalized x", ylabel="normalized y", aspect="equal")
    fig.suptitle("Synthetic layouts — geometry transfer cases, not facility drawings")
    fig.savefig(output / "01_layout_partition.png", dpi=190)
    plt.close(fig)

    hashes = {p.name: sha256(p) for p in sorted(output.iterdir())
              if p.is_file() and p.name != "artifact_hashes.json"}
    (output / "artifact_hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

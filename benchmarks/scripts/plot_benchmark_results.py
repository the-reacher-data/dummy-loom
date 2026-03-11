"""Generate per-scenario benchmark charts and markdown summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "benchmarks" / "raw"
IMG_DIR = ROOT / "docs" / "images"
REPORT_DIR = ROOT / "docs"

_TARGET_COLOURS: dict[str, str] = {
    "loompy": "#2563EB",
    "loompy-cache-memory": "#059669",
    "fastapi-native": "#DC2626",
}
_TARGET_LABELS: dict[str, str] = {
    "loompy": "Loom",
    "loompy-cache-memory": "Loom + cache",
    "fastapi-native": "FastAPI native",
}
_FALLBACK_COLOURS = ("#7C3AED", "#D97706", "#374151")


def _colour(target: str, index: int) -> str:
    return _TARGET_COLOURS.get(target, _FALLBACK_COLOURS[index % len(_FALLBACK_COLOURS)])


def _label(target: str) -> str:
    return _TARGET_LABELS.get(target, target)


def _latest_json() -> Path:
    files = sorted(RAW_DIR.glob("benchmark_external_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No benchmark json files found in {RAW_DIR}")
    return files[-1]


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Invalid benchmark json root")
    return data


def _scenario_rows(
    data: dict[str, Any], scenario_name: str
) -> dict[str, dict[int, dict[str, float]]]:
    out: dict[str, dict[int, dict[str, float]]] = {}
    for result in data["results"]:
        target = str(result["target"])
        per_concurrency: dict[int, dict[str, float]] = {}
        for row in result["aggregate"]["by_scenario"]:
            if str(row["scenario"]) != scenario_name:
                continue
            concurrency = int(row["concurrency"])
            per_concurrency[concurrency] = {
                "rps": float(row["median_rps"]),
                "p95": float(row["median_p95_ms"]),
            }
        out[target] = per_concurrency
    return out


def _plot_scenario(data: dict[str, Any], scenario_name: str, out_path: Path) -> None:
    scenario_rows = _scenario_rows(data, scenario_name)
    targets = list(scenario_rows.keys())
    concurrencies = sorted(
        {c for target_rows in scenario_rows.values() for c in target_rows}
    )
    if not concurrencies:
        raise RuntimeError(f"No data found for scenario: {scenario_name}")

    n_targets = len(targets)
    n_conc = len(concurrencies)
    bar_h = 0.22
    group_gap = 0.15
    group_height = n_targets * bar_h + group_gap

    fig, (ax_rps, ax_p95) = plt.subplots(
        1, 2,
        figsize=(13, max(3.5, n_conc * group_height + 1.4)),
        constrained_layout=True,
    )
    fig.patch.set_facecolor("#FAFAFA")

    y_positions: list[float] = []
    y_labels: list[str] = []
    for c_i, c in enumerate(reversed(concurrencies)):
        group_center = c_i * group_height
        y_labels.append(f"c={c}")
        y_positions.append(group_center + (n_targets - 1) * bar_h / 2)

        for t_i, target in enumerate(targets):
            colour = _colour(target, t_i)
            y = group_center + t_i * bar_h
            rps = scenario_rows[target].get(c, {}).get("rps", 0.0)
            p95 = scenario_rows[target].get(c, {}).get("p95", 0.0)

            legend_label = _label(target) if c_i == 0 else "_nolegend_"
            ax_rps.barh(y, rps, height=bar_h * 0.85, color=colour,
                        alpha=0.88, label=legend_label)
            ax_p95.barh(y, p95, height=bar_h * 0.85, color=colour,
                        alpha=0.88, label="_nolegend_")

            if rps > 0:
                ax_rps.text(rps + 4, y, f"{rps:.0f}", va="center",
                            fontsize=7.5, color="#374151")
            if p95 > 0:
                ax_p95.text(p95 + 0.3, y, f"{p95:.1f}", va="center",
                            fontsize=7.5, color="#374151")

    for ax in (ax_rps, ax_p95):
        ax.set_facecolor("#FAFAFA")
        ax.set_yticks(y_positions)
        ax.set_yticklabels(y_labels, fontsize=9)
        ax.grid(axis="x", linestyle="--", alpha=0.4, color="#CBD5E1")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))

    ax_rps.set_xlabel("Median RPS  (higher is better)", fontsize=9)
    ax_p95.set_xlabel("Median p95 ms  (lower is better)", fontsize=9)
    ax_rps.set_title("Throughput", fontsize=10, fontweight="bold", pad=6)
    ax_p95.set_title("Tail latency", fontsize=10, fontweight="bold", pad=6)

    handles, labels = ax_rps.get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="lower center",
        ncol=n_targets,
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, -0.06),
    )
    fig.suptitle(scenario_name.replace("_", " "), fontsize=11, fontweight="bold")
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _write_report(
    data: dict[str, Any], json_path: Path, image_map: dict[str, Path]
) -> Path:
    ts = int(data["timestamp"])
    method = data["methodology"]
    out = REPORT_DIR / f"benchmark_report_{ts}.md"

    md: list[str] = [
        "# Benchmark Report",
        "",
        f"- Source JSON: `{json_path}`",
        f"- Repeats: `{method['repeats']}`",
        f"- Warmup calls: `{method['warmup_calls']}`",
        f"- Target order: `{', '.join(method.get('target_order', []))}`",
        "",
        "## Scenario Charts",
        "",
    ]
    for scenario in [str(s["name"]) for s in method["scenarios"]]:
        img = image_map[scenario]
        md.extend([
            f"### {scenario}",
            "",
            f"![{scenario}]({img.relative_to(ROOT).as_posix()})",
            "",
        ])

    out.write_text("\n".join(md), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-scenario benchmark charts")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    json_path = args.json or _latest_json()
    data = _load(json_path)

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(data["timestamp"])

    scenarios = [str(s["name"]) for s in data["methodology"]["scenarios"]]
    image_map: dict[str, Path] = {}

    for scenario in scenarios:
        image_path = IMG_DIR / f"benchmark_external_{ts}_{scenario}.png"
        _plot_scenario(data, scenario, image_path)
        image_map[scenario] = image_path

    report = _write_report(data, json_path, image_map)
    latest_report = REPORT_DIR / "benchmark_report_latest.md"
    latest_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")

    for scenario, image in image_map.items():
        latest_image = IMG_DIR / f"benchmark_latest_{scenario}.png"
        latest_image.write_bytes(image.read_bytes())

    print(f"JSON: {json_path}")
    print(f"Report: {report}")
    for scenario, image in image_map.items():
        print(f"  {scenario}: {image.name}")


if __name__ == "__main__":
    main()

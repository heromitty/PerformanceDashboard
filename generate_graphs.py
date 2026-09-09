"""Generate full-frame performance graphs into GraphCache."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_loader import METRIC_COLUMNS, discover_measurements, load_frame_data


LOGGER = logging.getLogger(__name__)
TARGET_LINES = (16.7, 33.3)
COLORS = {
    "FrameTime": "#A6E3A1",
    "GameThread": "#89B4FA",
    "RenderThread": "#FAB387",
    "GPU": "#F38BA8",
}


def generate_graph(measurement, output_path: Path) -> None:
    frame_df = load_frame_data(measurement.csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(16, 8))
    try:
        for display_name, column in METRIC_COLUMNS.items():
            ax.plot(
                frame_df["Frame"],
                frame_df[column],
                label=display_name,
                color=COLORS[display_name],
                linewidth=0.7,
                alpha=0.9,
            )
        for value in TARGET_LINES:
            ax.axhline(value, color="#888888", linestyle=":", linewidth=0.8,
                       label=f"{value:.1f} ms")
        ax.set_title(f"{measurement.revision_folder} / {measurement.level_name}")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Time (ms)")
        ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
        ax.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(output_path, dpi=120)
    finally:
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate UE5 CSVProfiler graph cache")
    parser.add_argument("--sample-data", type=Path, default=Path(__file__).parent / "SampleData")
    parser.add_argument("--graph-cache", type=Path, default=Path(__file__).parent / "GraphCache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    measurements = discover_measurements(args.sample_data, args.graph_cache)
    generated = skipped = 0
    for measurement in measurements:
        output_path = measurement.graph_cache_path
        if output_path.exists():
            LOGGER.info("スキップ: %s", output_path)
            skipped += 1
            continue
        try:
            generate_graph(measurement, output_path)
            LOGGER.info("生成: %s", output_path)
            generated += 1
        except Exception as exc:
            LOGGER.error("グラフ生成に失敗しました (%s / %s): %s",
                         measurement.revision_folder, measurement.level_name, exc)

    LOGGER.info("完了: generated=%d, skipped=%d, total=%d", generated, skipped, len(measurements))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

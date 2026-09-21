"""Generate Phase 3 XY scatter performance maps from CSVProfiler data."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
import pandas as pd

from data_loader import extract_level_name, extract_revision_number


LOGGER = logging.getLogger(__name__)
INPUT_ROOT = Path(__file__).resolve().parent / "SanitizedData"
OUTPUT_ROOT = Path(__file__).resolve().parent / "HeatmapCache"
METRICS = ("FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime")
TIME_COLUMNS = METRICS
BASE_COLUMNS = ("EVENTS", "View/PosX", "View/PosY")

POINT_SIZE = 3.0
BACKGROUND_POINT_SIZE = POINT_SIZE - 0.5
HIGHLIGHT_POINT_SIZE = 5.0
BACKGROUND_ALPHA = 0.45
HIGHLIGHT_ALPHA = 0.95
MAX_MARKER_SIZE = 55
OVER_TARGET_MARKER_SIZE = 36
SUSTAINED_MARKER_SIZE = 14

COLOR_MIN = 0.0
COLOR_60_FPS = 16.67
COLOR_30_FPS = 33.33
COLOR_MAX = 50.0
TARGET_FRAME_TIME = COLOR_60_FPS

# GPU's sustained-load rule is intentionally kept as simple, adjustable
# constants for this experimental Phase 3 feature.
GPU_SUSTAINED_PERCENTILE = 0.95
GPU_SUSTAINED_MIN_RUN_LENGTH = 30

FRAME_TIME_CMAP = LinearSegmentedColormap.from_list(
    "frame_time",
    (
        (COLOR_MIN / COLOR_MAX, "#2166ac"),
        (COLOR_60_FPS / COLOR_MAX, "#fee08b"),
        (COLOR_30_FPS / COLOR_MAX, "#d73027"),
        (1.0, "#7f0000"),
    ),
)
FRAME_TIME_NORM = Normalize(vmin=COLOR_MIN, vmax=COLOR_MAX, clip=True)


def _read_frame_data(csv_path: Path) -> tuple[pd.DataFrame, int]:
    """Read Frame candidates using the existing dashboard filtering rules."""
    header = pd.read_csv(csv_path, nrows=0)
    missing = [column for column in BASE_COLUMNS if column not in header.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    available_time_columns = [
        column for column in TIME_COLUMNS if column in header.columns
    ]
    if not available_time_columns:
        raise ValueError("none of the time metric columns are present")
    usecols = [*BASE_COLUMNS, *available_time_columns]

    frame_df = pd.read_csv(
        csv_path,
        usecols=usecols,
        dtype=str,
        on_bad_lines="skip",
    )
    events = frame_df["EVENTS"].fillna("").astype(str).str.strip()
    not_command = ~events.str.startswith("Cmd:")
    for column in (*available_time_columns, "View/PosX", "View/PosY"):
        frame_df[column] = pd.to_numeric(frame_df[column], errors="coerce")
    for column in set(TIME_COLUMNS) - set(available_time_columns):
        frame_df[column] = pd.Series(pd.NA, index=frame_df.index, dtype="object")

    numeric_candidate = frame_df[list(TIME_COLUMNS)].notna().any(axis=1)
    valid_frames = frame_df.loc[not_command & numeric_candidate].copy()
    valid_frames.insert(0, "Frame", range(1, len(valid_frames) + 1))
    return valid_frames.reset_index(drop=True), len(valid_frames)


def _find_runs(mask: pd.Series, frame_numbers: pd.Series) -> list[tuple[int, int, int]]:
    """Return inclusive Frame-number runs for a boolean mask."""
    runs: list[tuple[int, int, int]] = []
    start: int | None = None
    previous_frame: int | None = None
    for index, active in enumerate(mask.tolist()):
        frame_number = int(frame_numbers.iloc[index])
        contiguous = previous_frame is not None and frame_number == previous_frame + 1
        if start is not None and (not active or not contiguous):
            end = index - 1
            runs.append((int(frame_numbers.iloc[start]), int(frame_numbers.iloc[end]), end - start + 1))
            start = None
        if active and start is None:
            start = index
        if start is not None and active and index == len(mask) - 1:
            runs.append((int(frame_numbers.iloc[start]), frame_number, index - start + 1))
            start = None
        previous_frame = frame_number
    return runs


def _sustained_gpu_frames(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[int, int, int]], float]:
    """Find GPU P95 runs meeting the experimental minimum length."""
    gpu_values = frame_df["GPUTime"]
    p95 = float(gpu_values.dropna().quantile(GPU_SUSTAINED_PERCENTILE))
    runs = [
        run
        for run in _find_runs(
            gpu_values.ge(p95) & gpu_values.notna(), frame_df["Frame"]
        )
        if run[2] >= GPU_SUSTAINED_MIN_RUN_LENGTH
    ]
    sustained_frames = frame_df[frame_df["Frame"].isin(
        frame for start, end, _ in runs for frame in range(start, end + 1)
    )]
    return sustained_frames, runs, p95


def _generate_heatmap(
    frame_df: pd.DataFrame,
    revision_name: str,
    level_name: str,
    metric: str,
    output_path: Path,
) -> dict[str, object]:
    drawable = frame_df.dropna(subset=["View/PosX", "View/PosY", metric]).copy()
    if drawable.empty:
        raise ValueError(f"no drawable Frame with numeric View/PosX, View/PosY, and {metric}")

    values = drawable[metric]
    max_index = values.idxmax()
    max_frame = drawable.loc[max_index]
    max_value = float(max_frame[metric])
    over_target = drawable[metric] > TARGET_FRAME_TIME
    sustained_frames = pd.DataFrame()
    sustained_runs: list[tuple[int, int, int]] = []
    sustained_p95: float | None = None
    if metric == "GPUTime":
        sustained_frames, sustained_runs, sustained_p95 = _sustained_gpu_frames(drawable)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 8))
    try:
        background = ax.scatter(
            drawable["View/PosX"], drawable["View/PosY"],
            c=values, cmap=FRAME_TIME_CMAP, norm=FRAME_TIME_NORM,
            s=BACKGROUND_POINT_SIZE, alpha=BACKGROUND_ALPHA, linewidths=0,
        )

        highlighted = drawable[drawable[metric] > TARGET_FRAME_TIME]
        ax.scatter(
            highlighted["View/PosX"], highlighted["View/PosY"],
            c=highlighted[metric], cmap=FRAME_TIME_CMAP, norm=FRAME_TIME_NORM,
            s=HIGHLIGHT_POINT_SIZE, alpha=HIGHLIGHT_ALPHA, linewidths=0,
            zorder=2,
        )

        if metric == "GPUTime" and not sustained_frames.empty:
            ax.scatter(
                sustained_frames["View/PosX"], sustained_frames["View/PosY"],
                facecolors="none", edgecolors="#111111",
                marker="o", s=SUSTAINED_MARKER_SIZE, linewidths=0.7,
                zorder=3,
            )

        # A black open diamond is deliberately independent of the colormap,
        # so even a single over-target Frame is discoverable after shrinking.
        # The extra outline is essential for rare threshold violations in the
        # three component metrics. FrameTime can exceed the target for many
        # Frames, so its existing color/front layer remains the clearer view.
        over_target_frames = drawable[over_target]
        if metric != "FrameTime":
            ax.scatter(
                over_target_frames["View/PosX"], over_target_frames["View/PosY"],
                facecolors="none", edgecolors="#000000", marker="D",
                s=OVER_TARGET_MARKER_SIZE, linewidths=1.3, zorder=4,
            )
            legend_handles = [
                Line2D(
                    [0], [0], marker="D", linestyle="None",
                    markerfacecolor="none", markeredgecolor="#000000",
                    markersize=6, markeredgewidth=1.1, label="> 16.67 ms",
                ),
                Line2D(
                    [0], [0], marker="X", linestyle="None",
                    markerfacecolor="#ffffff", markeredgecolor="#111111",
                    markersize=7, markeredgewidth=1.0, label="MAX",
                ),
            ]
            if metric == "GPUTime":
                legend_handles.insert(
                    1,
                    Line2D(
                        [0], [0], marker="o", linestyle="None",
                        markerfacecolor="none", markeredgecolor="#111111",
                        markersize=6, markeredgewidth=0.8,
                        label=(
                            f"Sustained GPU Load: >= P95 ({sustained_p95:.4f} ms), "
                            f">= {GPU_SUSTAINED_MIN_RUN_LENGTH} Frames"
                        ),
                    ),
                )
            fig.legend(
                handles=legend_handles,
                loc="lower center",
                bbox_to_anchor=(0.5, 0.02),
                fontsize=8,
                framealpha=0.88,
                borderpad=0.6,
            )
        ax.scatter(
            [max_frame["View/PosX"]], [max_frame["View/PosY"]],
            marker="X", s=MAX_MARKER_SIZE, facecolors="#ffffff",
            edgecolors="#111111", linewidths=1.2, zorder=5,
        )
        ax.annotate(
            f"MAX\n{max_value:.2f} ms",
            xy=(max_frame["View/PosX"], max_frame["View/PosY"]),
            xytext=(10, 10), textcoords="offset points", ha="left", va="bottom",
            fontsize=9, color="#111111",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.85},
            arrowprops={"arrowstyle": "->", "color": "#111111", "lw": 0.9},
            annotation_clip=True, zorder=6,
        )

        ax.set_aspect("equal", adjustable="box")
        ax.margins(x=0.03, y=0.03)
        ax.set_xlabel("View PosX")
        ax.set_ylabel("View PosY")
        over_count = int(over_target.sum())
        over_pct = over_count / len(drawable) * 100
        title_lines = [
            f"{revision_name} / {level_name} - {metric} Heatmap",
            f"Max {metric}: {max_value:.2f} ms | >16.67ms: {over_count} Frames ({over_pct:.3f}%)",
        ]
        if metric == "GPUTime":
            title_lines.append(f"Sustained High Load: {len(sustained_runs)} Runs")
        ax.set_title("\n".join(title_lines))

        colorbar = fig.colorbar(background, ax=ax, pad=0.02)
        colorbar.set_label(f"{metric} (ms)")
        colorbar.set_ticks([COLOR_MIN, COLOR_60_FPS, COLOR_30_FPS, COLOR_MAX])
        fig.tight_layout(rect=(0.03, 0.16, 0.97, 0.96))
        fig.savefig(output_path, dpi=120)
    finally:
        plt.close(fig)

    return {
        "drawable": len(drawable),
        "min": float(values.min()),
        "median": float(values.median()),
        "max": max_value,
        "over_count": over_count,
        "over_pct": over_pct,
        "max_frame": int(max_frame["Frame"]),
        "max_x": float(max_frame["View/PosX"]),
        "max_y": float(max_frame["View/PosY"]),
        "sustained_p95": sustained_p95,
        "sustained_runs": sustained_runs,
    }


def _revision_and_level(csv_path: Path) -> tuple[str, str]:
    relative = csv_path.relative_to(INPUT_ROOT)
    if not relative.parts:
        raise ValueError("CSV is not below a Revision directory")
    revision_name = relative.parts[0]
    if extract_revision_number(revision_name) is None:
        raise ValueError(f"invalid Revision directory: {revision_name}")
    level_name = extract_level_name(csv_path.name)
    if level_name is None:
        raise ValueError(f"Level name not found in file name: {csv_path.name}")
    return revision_name, level_name


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(INPUT_ROOT.rglob("*.csv")) if INPUT_ROOT.exists() else []
    generated = skipped = total = errors = 0

    for csv_path in csv_files:
        try:
            revision_name, level_name = _revision_and_level(csv_path)
            frame_df, valid_frames = _read_frame_data(csv_path)
            for metric in METRICS:
                total += 1
                output_path = OUTPUT_ROOT / revision_name / f"{level_name}-{metric}.png"
                if output_path.exists():
                    print(
                        f"Revision={revision_name} Level={level_name} Metric={metric} "
                        f"CSV={csv_path} Output={output_path} SKIP"
                    )
                    skipped += 1
                    continue
                try:
                    result = _generate_heatmap(
                        frame_df, revision_name, level_name, metric, output_path
                    )
                    print(
                        f"Revision={revision_name} Level={level_name} Metric={metric} "
                        f"ValidFrames={valid_frames} DrawableFrames={result['drawable']} "
                        f"Min={result['min']:.4f} Median={result['median']:.4f} Max={result['max']:.4f} "
                        f">16.67ms={result['over_count']} ({result['over_pct']:.3f}%) "
                        f"Output={output_path} GENERATED"
                    )
                    if metric == "GPUTime":
                        runs = result["sustained_runs"]
                        print(
                            f"  GPU P95={result['sustained_p95']:.4f} "
                            f"SustainedRuns={len(runs)} "
                            f"Lengths={[run[2] for run in runs]}"
                        )
                    generated += 1
                except Exception as exc:
                    errors += 1
                    print(f"Revision={revision_name} Level={level_name} Metric={metric} ERROR: {exc}")
                    LOGGER.debug("Heatmap generation failed", exc_info=True)
        except Exception as exc:
            errors += len(METRICS)
            total += len(METRICS)
            print(f"CSV={csv_path} ERROR: {exc}")
            LOGGER.debug("CSV processing failed", exc_info=True)

    print(f"Generated={generated} Skipped={skipped} Errors={errors}")
    print(f"generated={generated}, skipped={skipped}, total={total}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

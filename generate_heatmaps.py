"""Generate Phase 1.5 XY scatter performance maps from CSVProfiler data."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
import pandas as pd

from data_loader import extract_level_name, extract_revision_number


LOGGER = logging.getLogger(__name__)
INPUT_ROOT = Path(__file__).resolve().parent / "SanitizedData"
OUTPUT_ROOT = Path(__file__).resolve().parent / "HeatmapCache"
OUTPUT_NAME_SUFFIX = "-FrameTime.png"
POINT_SIZE = 3.0
BACKGROUND_POINT_SIZE = POINT_SIZE - 0.5
HIGHLIGHT_POINT_SIZE = 5.0
BACKGROUND_ALPHA = 0.45
HIGHLIGHT_ALPHA = 0.95
COLOR_MIN = 0.0
COLOR_60_FPS = 16.67
COLOR_30_FPS = 33.33
COLOR_MAX = 50.0
HIGHLIGHT_THRESHOLD = COLOR_60_FPS

REQUIRED_COLUMNS = (
    "EVENTS",
    "FrameTime",
    "GameThreadTime",
    "RenderThreadTime",
    "GPUTime",
    "View/PosX",
    "View/PosY",
)
TIME_COLUMNS = ("FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime")

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
    """Read frame candidates and return them with the valid-frame count."""
    header = pd.read_csv(csv_path, nrows=0)
    missing = [column for column in REQUIRED_COLUMNS if column not in header.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    frame_df = pd.read_csv(
        csv_path,
        usecols=list(REQUIRED_COLUMNS),
        dtype=str,
        on_bad_lines="skip",
    )
    events = frame_df["EVENTS"].fillna("").astype(str).str.strip()
    not_command = ~events.str.startswith("Cmd:")

    for column in (*TIME_COLUMNS, "View/PosX", "View/PosY"):
        frame_df[column] = pd.to_numeric(frame_df[column], errors="coerce")

    # Match data_loader.py: any one of the existing time metrics makes a
    # non-command row a valid Frame candidate.
    numeric_candidate = frame_df[list(TIME_COLUMNS)].notna().any(axis=1)
    valid_frames = frame_df.loc[not_command & numeric_candidate].copy()
    drawable = valid_frames.dropna(
        subset=["View/PosX", "View/PosY", "FrameTime"]
    ).copy()
    return drawable, len(valid_frames)


def _generate_heatmap(
    frame_df: pd.DataFrame,
    revision_name: str,
    level_name: str,
    output_path: Path,
) -> tuple[float, float, float]:
    """Render a fixed-scale FrameTime scatter plot and return its statistics."""
    frame_times = frame_df["FrameTime"]
    max_index = frame_times.idxmax()
    max_frame = frame_df.loc[max_index]
    max_frame_time = float(max_frame["FrameTime"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 8))
    try:
        # Draw every usable Frame as a subdued, color-mapped background so
        # the camera path remains visible even when most values are typical.
        ax.scatter(
            frame_df["View/PosX"],
            frame_df["View/PosY"],
            c=frame_times,
            cmap=FRAME_TIME_CMAP,
            norm=FRAME_TIME_NORM,
            s=BACKGROUND_POINT_SIZE,
            alpha=BACKGROUND_ALPHA,
            linewidths=0,
        )
        # Put performance-relevant points above the background.  This is only
        # a visual emphasis layer; no Frames are removed or aggregated.
        highlighted = frame_df[frame_times > HIGHLIGHT_THRESHOLD]
        ax.scatter(
            highlighted["View/PosX"],
            highlighted["View/PosY"],
            c=highlighted["FrameTime"],
            cmap=FRAME_TIME_CMAP,
            norm=FRAME_TIME_NORM,
            s=HIGHLIGHT_POINT_SIZE,
            alpha=HIGHLIGHT_ALPHA,
            linewidths=0,
        )
        ax.scatter(
            [max_frame["View/PosX"]],
            [max_frame["View/PosY"]],
            marker="X",
            s=55,
            facecolors="#ffffff",
            edgecolors="#111111",
            linewidths=1.2,
            zorder=4,
        )
        ax.annotate(
            f"MAX\n{max_frame_time:.2f} ms",
            xy=(max_frame["View/PosX"], max_frame["View/PosY"]),
            xytext=(10, 10),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=9,
            color="#111111",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.85},
            arrowprops={"arrowstyle": "->", "color": "#111111", "lw": 0.9},
            annotation_clip=True,
            zorder=5,
        )
        ax.set_aspect("equal", adjustable="box")
        ax.margins(x=0.03, y=0.03)
        ax.set_xlabel("View PosX")
        ax.set_ylabel("View PosY")
        ax.set_title(
            f"{revision_name} / {level_name} - FrameTime Heatmap\n"
            f"Max FrameTime: {max_frame_time:.2f} ms"
        )
        colorbar = fig.colorbar(ax.collections[0], ax=ax, pad=0.02)
        colorbar.set_label("FrameTime (ms)")
        colorbar.set_ticks([COLOR_MIN, COLOR_60_FPS, COLOR_30_FPS, COLOR_MAX])
        fig.tight_layout()
        fig.savefig(output_path, dpi=120)
    finally:
        plt.close(fig)

    return (float(frame_times.min()), float(frame_times.median()), max_frame_time)


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
    generated = skipped = errors = 0

    for csv_path in csv_files:
        try:
            revision_name, level_name = _revision_and_level(csv_path)
            output_path = OUTPUT_ROOT / revision_name / f"{level_name}{OUTPUT_NAME_SUFFIX}"
            if output_path.exists():
                print(
                    f"Revision={revision_name} Level={level_name} "
                    f"CSV={csv_path} Output={output_path} SKIP"
                )
                skipped += 1
                continue

            frame_df, valid_frames = _read_frame_data(csv_path)
            if frame_df.empty:
                raise ValueError("no drawable Frame with numeric View/PosX, View/PosY, and FrameTime")
            frame_min, frame_median, frame_max = _generate_heatmap(
                frame_df, revision_name, level_name, output_path
            )
            print(
                f"Revision={revision_name} Level={level_name} CSV={csv_path} "
                f"ValidFrames={valid_frames} DrawableFrames={len(frame_df)} "
                f"FrameTime(min/median/max)={frame_min:.4f}/{frame_median:.4f}/{frame_max:.4f} "
                f"Output={output_path} GENERATED"
            )
            generated += 1
        except Exception as exc:
            errors += 1
            print(f"CSV={csv_path} ERROR: {exc}")
            LOGGER.debug("Heatmap generation failed", exc_info=True)

    print(f"Generated={generated} Skipped={skipped} Errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

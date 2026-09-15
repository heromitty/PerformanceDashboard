"""Local Streamlit dashboard for comparing UE5 performance revisions."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from data_loader import (
    DuplicateRevisionError,
    METRIC_COLUMNS,
    Measurement,
    discover_measurements,
    discover_revisions,
    extract_revision_number,
    load_statistics,
)


ROOT = Path(__file__).resolve().parent
SANITIZED_DATA_ROOT = ROOT / "SanitizedData"
GRAPH_CACHE_ROOT = ROOT / "GraphCache"
HEATMAP_CACHE_ROOT = ROOT / "HeatmapCache"
DASHBOARD_IMAGE_WIDTH = 700
HEATMAP_METRICS = {
    "FrameTime": "FrameTime",
    "GameThread": "GameThreadTime",
    "RenderThread": "RenderThreadTime",
    "GPU": "GPUTime",
}
LOGGER = logging.getLogger(__name__)


@st.cache_data(show_spinner=False)
def cached_statistics(csv_path: str) -> dict[str, dict[str, float | None]]:
    return load_statistics(Path(csv_path))


def _revision_measurements(measurements: list[Measurement], revision: str) -> dict[str, Measurement]:
    return {
        item.level_name: item
        for item in measurements
        if item.revision_folder == revision
    }


def _format_value(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f} ms"


def _change_percent(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _format_change(change: float | None) -> str:
    return "N/A" if change is None else f"{change:+.1f}%"


def _cell_style(change: float | None) -> str:
    if change is None:
        return ""
    if change >= 10:
        return "background-color: #ffd6d6; color: #9b1c1c"
    if change >= 5:
        return "background-color: #fff0bf; color: #7a5600"
    if change <= -10:
        return "background-color: #d9f2d9; color: #1f6b1f"
    return ""


def _load_stats(item: Measurement | None) -> dict[str, dict[str, float | None]] | None:
    if item is None:
        return None
    try:
        return cached_statistics(str(item.csv_path))
    except Exception as exc:
        st.warning(f"CSVを読み込めません: {item.csv_path.name} ({exc})")
        return None


def _render_overview(
    current_items: dict[str, Measurement],
    previous_items: dict[str, Measurement],
    statistic: str,
) -> None:
    rows: list[dict[str, str]] = []
    styles: list[dict[str, str]] = []
    for level in sorted(current_items):
        current_stats = _load_stats(current_items[level])
        previous_stats = _load_stats(previous_items.get(level))
        row = {"Level": level}
        style_row = {"Level": ""}
        for display_name in METRIC_COLUMNS:
            current = current_stats.get(display_name, {}).get(statistic) if current_stats else None
            previous = previous_stats.get(display_name, {}).get(statistic) if previous_stats else None
            change = _change_percent(current, previous)
            row[display_name] = f"{_format_value(current)} ({_format_change(change)})"
            style_row[display_name] = _cell_style(change)
        rows.append(row)
        styles.append(style_row)

    if not rows:
        st.info("Current RevisionにLevelがありません。")
        return

    table = pd.DataFrame(rows).set_index("Level")
    style_table = pd.DataFrame(styles).set_index("Level")
    styled = table.style.apply(lambda _: style_table.to_numpy(), axis=None)
    st.dataframe(styled, width="stretch", hide_index=False)
    st.caption("セル内はCurrent値とPrevious比です。増加は負荷悪化、減少は改善を示します。")


def _render_statistics(
    current_item: Measurement,
    previous_item: Measurement | None,
) -> None:
    current_stats = _load_stats(current_item)
    previous_stats = _load_stats(previous_item)
    rows: list[dict[str, str]] = []
    for display_name in METRIC_COLUMNS:
        row: dict[str, str] = {"計測項目": display_name}
        for statistic in ("Mean", "Median", "Max"):
            current = current_stats.get(display_name, {}).get(statistic) if current_stats else None
            previous = previous_stats.get(display_name, {}).get(statistic) if previous_stats else None
            row[f"{statistic} Current"] = _format_value(current)
            row[f"{statistic} Previous"] = _format_value(previous)
            row[f"{statistic} 増減率"] = _format_change(_change_percent(current, previous))
        rows.append(row)
    st.dataframe(pd.DataFrame(rows).set_index("計測項目"), width="stretch")


def _render_cached_image(title: str, current_path: Path | None, previous_path: Path | None) -> None:
    st.subheader(title)
    choice = st.radio(
        f"{title}表示対象",
        ("Current", "Previous"),
        horizontal=True,
        key=f"{title}_revision_choice",
    )
    path = current_path if choice == "Current" else previous_path
    if path is None or not path.exists():
        if title == "フレーム推移グラフ":
            st.info("グラフが生成されていません。generate_graphs.py を実行してください。")
        else:
            st.info("Heatmapがありません。")
        return
    st.image(str(path), width=DASHBOARD_IMAGE_WIDTH)


def _heatmap_cache_path(item: Measurement, metric: str) -> Path:
    return HEATMAP_CACHE_ROOT / item.revision_folder / (
        f"{item.level_name}-{HEATMAP_METRICS[metric]}.png"
    )


def _render_performance_heatmap(
    level: str,
    current_item: Measurement,
    previous_item: Measurement | None,
) -> None:
    st.subheader("ヒートマップ")
    metric = st.radio(
        "計測項目",
        tuple(HEATMAP_METRICS),
        horizontal=True,
        key=f"performance_heatmap_metric_{level}",
    )
    revision_options = ("Current", "Previous") if previous_item else ("Current",)
    revision_choice = st.radio(
        "Revision",
        revision_options,
        horizontal=True,
        key=f"performance_heatmap_revision_{level}",
    )
    if previous_item is None:
        st.info("Previous revisionにこのLevelのHeatmapはありません。")

    selected_item = current_item if revision_choice == "Current" else previous_item
    if selected_item is None:
        st.info("Previous revisionにこのLevelは存在しません。")
        return

    heatmap_path = _heatmap_cache_path(selected_item, metric)
    if not heatmap_path.exists():
        st.warning(
            "Performance Heatmapがまだ生成されていません。"
            "generate_heatmaps.pyを実行してください。"
        )
        st.caption(
            f"Revision={selected_item.revision_folder} / Level={level} / "
            f"Metric={metric} / 期待されるPNG: {heatmap_path}"
        )
        return
    st.image(str(heatmap_path), width=DASHBOARD_IMAGE_WIDTH)


def _render_detail(
    level: str,
    current_items: dict[str, Measurement],
    previous_items: dict[str, Measurement],
) -> None:
    current_item = current_items[level]
    previous_item = previous_items.get(level)
    st.subheader(f"Level詳細: {level}")
    _render_statistics(current_item, previous_item)

    current_graph = current_item.graph_cache_path
    previous_graph = previous_item.graph_cache_path if previous_item else None
    _render_cached_image("フレーム推移グラフ", current_graph, previous_graph)

    _render_performance_heatmap(level, current_item, previous_item)


def main() -> None:
    st.set_page_config(page_title="UE5 Performance Dashboard", layout="wide")
    st.title("UE5 Performance Dashboard")

    try:
        revisions = discover_revisions(SANITIZED_DATA_ROOT)
        measurements = discover_measurements(SANITIZED_DATA_ROOT, GRAPH_CACHE_ROOT)
    except DuplicateRevisionError as exc:
        st.error(f"Revision番号が重複しているため、比較できません: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"データ探索に失敗しました: {exc}")
        st.stop()

    invalid_dirs = [
        path.name
        for path in SANITIZED_DATA_ROOT.iterdir()
        if path.is_dir() and extract_revision_number(path.name) is None
    ]
    if invalid_dirs:
        st.warning(f"Revision形式でないフォルダを除外しました: {', '.join(invalid_dirs)}")

    if not revisions:
        st.warning("有効なRevisionがありません。")
        return

    revision_names = [revision.folder_name for revision in revisions]
    current_revision = st.selectbox(
        "Current Revision",
        revision_names,
        index=len(revision_names) - 1,
    )
    current_index = revision_names.index(current_revision)
    previous_revision = revision_names[current_index - 1] if current_index > 0 else None
    st.write(f"Current : `{current_revision}`")
    st.write(f"Previous: `{previous_revision or 'N/A'}`")

    statistic = st.radio("Statistic", ("Mean", "Median", "Max"), horizontal=True, index=0)
    current_items = _revision_measurements(measurements, current_revision)
    previous_items = _revision_measurements(measurements, previous_revision) if previous_revision else {}

    st.divider()
    st.header("Level一覧")
    _render_overview(current_items, previous_items, statistic)

    previous_only = sorted(set(previous_items) - set(current_items))
    if previous_only:
        st.warning("Previous Revisionにのみ存在するLevel: " + ", ".join(previous_only))

    if not current_items:
        return
    st.divider()
    selected_level = st.selectbox("詳細を表示するLevel", sorted(current_items))
    _render_detail(selected_level, current_items, previous_items)


if __name__ == "__main__":
    main()

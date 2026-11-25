"""Local Streamlit dashboard for comparing UE5 performance revisions."""

from __future__ import annotations

import logging
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from data_loader import (
    DETAIL_METRIC_COLUMNS,
    DuplicateRevisionError,
    METRIC_COLUMNS,
    Measurement,
    discover_measurements,
    discover_revisions,
    extract_revision_number,
    load_statistics_cache,
)


ROOT = Path(__file__).resolve().parent
SANITIZED_DATA_ROOT = ROOT / "SanitizedData"
GRAPH_CACHE_ROOT = ROOT / "GraphCache"
HEATMAP_CACHE_ROOT = ROOT / "HeatmapCache"
STATISTICS_CACHE_ROOT = ROOT / "StatisticsCache"
DASHBOARD_IMAGE_WIDTH = 700
HEATMAP_METRICS = {
    "FrameTime": "FrameTime",
    "GameThread": "GameThreadTime",
    "RenderThread": "RenderThreadTime",
    "GPU": "GPUTime",
}
TREND_TIME_METRICS = ("FrameTime", "GameThread", "RenderThread", "GPU")
TREND_OVER_BUDGET_METRICS = (
    ("GT超過", "GameThread"),
    ("RT超過", "RenderThread"),
    ("GPU超過", "GPU"),
)
TREND_COLORS = {
    "FrameTime": "#A6E3A1",
    "GameThread": "#89B4FA",
    "RenderThread": "#FAB387",
    "GPU": "#F38BA8",
    "GT超過": "#89B4FA",
    "RT超過": "#FAB387",
    "GPU超過": "#F38BA8",
}
TREND_TIME_Y_MAX_MS = 35.0
TREND_FRAME_BUDGET_MS = 16.67
LOGGER = logging.getLogger(__name__)


@st.cache_data(show_spinner=False)
def cached_statistics_cache(
    cache_path: str,
    revision_folder: str,
    revision_number: int,
    level_name: str,
    cache_mtime_ns: int | None,
) -> dict[str, object] | None:
    # The mtime is an explicit cache key so an externally regenerated JSON is
    # observed on the next Streamlit rerun.
    del cache_mtime_ns
    return load_statistics_cache(
        Path(cache_path), revision_folder, revision_number, level_name
    )


def _revision_measurements(measurements: list[Measurement], revision: str) -> dict[str, Measurement]:
    return {
        item.level_name: item
        for item in measurements
        if item.revision_folder == revision
    }


def _initialize_revision_selection(revision_names: list[str]) -> None:
    latest_revision = revision_names[-1]
    previous_default = revision_names[-2] if len(revision_names) >= 2 else None
    previous_options: list[str | None] = (
        revision_names if len(revision_names) >= 2 else [None]
    )

    if (
        "current_revision" not in st.session_state
        or st.session_state["current_revision"] not in revision_names
    ):
        st.session_state["current_revision"] = latest_revision
    if (
        "previous_revision" not in st.session_state
        or st.session_state["previous_revision"] not in previous_options
    ):
        st.session_state["previous_revision"] = previous_default


def _format_value(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f} ms"


def _change_percent(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _format_change(change: float | None) -> str:
    return "N/A" if change is None else f"{change:+.2f}%"


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


def _statistics_cache_path(item: Measurement) -> Path:
    return STATISTICS_CACHE_ROOT / item.revision_folder / f"{item.level_name}.json"


def _load_stats(item: Measurement | None) -> dict[str, object] | None:
    if item is None:
        return None
    cache_path = _statistics_cache_path(item)
    mtime_ns = cache_path.stat().st_mtime_ns if cache_path.exists() else None
    return cached_statistics_cache(
        str(cache_path),
        item.revision_folder,
        item.revision_number,
        item.level_name,
        mtime_ns,
    )


def _load_over_budget_stats(
    item: Measurement | None,
) -> dict[str, object] | None:
    if item is None:
        return None
    return _load_stats(item)


def _measurement_key(item: Measurement) -> tuple[str, str]:
    return item.revision_folder, item.level_name


def _load_statistics_for_measurements(
    measurements: list[Measurement],
) -> tuple[dict[tuple[str, str], dict[str, object] | None], int]:
    """Load each discovered measurement's cache once and count missing caches once."""
    stats_by_key: dict[tuple[str, str], dict[str, object] | None] = {}
    for item in measurements:
        stats_by_key[_measurement_key(item)] = _load_stats(item)
    missing_count = sum(stats is None for stats in stats_by_key.values())
    return stats_by_key, missing_count


def _stats_for(
    item: Measurement | None,
    stats_by_key: dict[tuple[str, str], dict[str, object] | None] | None,
) -> dict[str, object] | None:
    if item is None:
        return None
    if stats_by_key is not None:
        return stats_by_key.get(_measurement_key(item))
    return _load_stats(item)


def _statistics_metrics(
    stats: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    """Return the metrics section of a validated StatisticsCache payload."""
    if not stats:
        return {}
    metrics = stats.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _metric_stats(
    stats: dict[str, object] | None,
    display_name: str,
) -> dict[str, object] | None:
    metric = _statistics_metrics(stats).get(display_name)
    return metric if isinstance(metric, dict) else None


def _format_over_budget(
    stats: dict[str, object] | None,
    previous_stats: dict[str, object] | None = None,
) -> str:
    if stats is None or stats.get("OverBudgetRate") is None:
        return "N/A"
    count = int(stats["OverBudgetFrameCount"] or 0)
    if previous_stats is None or previous_stats.get("OverBudgetRate") is None:
        return f"{count:,} (N/A)"
    previous_count = int(previous_stats.get("OverBudgetFrameCount") or 0)
    count_delta = count - previous_count
    delta_text = str(count_delta) if count_delta == 0 else f"{count_delta:+d}"
    return f"{count:,} ({delta_text})"


def _over_budget_style(stats: dict[str, int | float | None] | None) -> str:
    if stats is None or stats.get("OverBudgetRate") is None:
        return ""
    count = int(stats.get("OverBudgetFrameCount") or 0)
    if count >= 100:
        return "background-color: #ffd6d6; color: #9b1c1c"
    if count >= 10:
        return "background-color: #fff0bf; color: #7a5600"
    return ""


def _render_overview(
    current_items: dict[str, Measurement],
    previous_items: dict[str, Measurement],
    statistic: str,
    stats_by_key: dict[tuple[str, str], dict[str, object] | None] | None = None,
) -> None:
    rows: list[dict[str, str]] = []
    styles: list[dict[str, str]] = []
    for level in sorted(current_items):
        current_stats = _stats_for(current_items[level], stats_by_key)
        previous_stats = _stats_for(previous_items.get(level), stats_by_key)
        over_budget_stats = _statistics_metrics(current_stats)
        previous_over_budget_stats = _statistics_metrics(previous_stats)
        row = {"Level": level}
        style_row = {"Level": ""}
        for display_name in METRIC_COLUMNS:
            current_metric = _metric_stats(current_stats, display_name)
            previous_metric = _metric_stats(previous_stats, display_name)
            current = current_metric.get(statistic) if current_metric else None
            previous = previous_metric.get(statistic) if previous_metric else None
            change = _change_percent(current, previous)
            row[display_name] = f"{_format_value(current)} ({_format_change(change)})"
            style_row[display_name] = _cell_style(change)
            if display_name in ("GameThread", "RenderThread", "GPU"):
                over_budget = over_budget_stats.get(display_name)
                over_budget_column = {
                    "GameThread": "GT超過",
                    "RenderThread": "RT超過",
                    "GPU": "GPU超過",
                }[display_name]
                previous_over_budget = previous_over_budget_stats.get(display_name)
                row[over_budget_column] = _format_over_budget(
                    over_budget,
                    previous_over_budget,
                )
                style_row[over_budget_column] = _over_budget_style(over_budget)
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
    stats_by_key: dict[tuple[str, str], dict[str, object] | None] | None = None,
) -> None:
    current_stats = _stats_for(current_item, stats_by_key)
    previous_stats = _stats_for(previous_item, stats_by_key)
    rows: list[dict[str, str]] = []
    styles: list[dict[str, str]] = []
    for display_name in DETAIL_METRIC_COLUMNS:
        row: dict[str, str] = {"計測項目": display_name}
        style_row: dict[str, str] = {"計測項目": ""}
        current_metric = _metric_stats(current_stats, display_name)
        previous_metric = _metric_stats(previous_stats, display_name)
        for statistic in ("Mean", "Median", "Max", "P95"):
            current = current_metric.get(statistic) if current_metric else None
            previous = previous_metric.get(statistic) if previous_metric else None
            change = _change_percent(current, previous)
            row[f"{statistic} Current"] = _format_value(current)
            row[f"{statistic} Previous"] = _format_value(previous)
            row[f"{statistic} 増減率"] = _format_change(change)
            style_row[f"{statistic} 増減率"] = _cell_style(change)
        rows.append(row)
        styles.append(style_row)

    table = pd.DataFrame(rows).set_index("計測項目")
    style_table = pd.DataFrame(styles, index=table.index).reindex(
        columns=table.columns, fill_value=""
    )
    styled = table.style.apply(lambda _: style_table.to_numpy(), axis=None)
    st.dataframe(styled, width="stretch")


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
    stats_by_key: dict[tuple[str, str], dict[str, object] | None] | None = None,
) -> None:
    current_item = current_items[level]
    previous_item = previous_items.get(level)
    st.subheader(f"Level詳細: {level}")
    _render_statistics(current_item, previous_item, stats_by_key)

    current_graph = current_item.graph_cache_path
    previous_graph = previous_item.graph_cache_path if previous_item else None
    _render_cached_image("フレーム推移グラフ", current_graph, previous_graph)

    _render_performance_heatmap(level, current_item, previous_item)


def _trend_levels(measurements: list[Measurement]) -> list[str]:
    return sorted({item.level_name for item in measurements})


def _trend_data(
    measurements: list[Measurement],
    stats_by_key: dict[tuple[str, str], dict[str, object] | None],
    level_name: str,
    statistic: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build independent time and over-budget series for one Level."""
    revision_items = {
        item.revision_number: item
        for item in measurements
        if item.level_name == level_name
    }
    revisions = sorted({item.revision_number for item in measurements})
    time_rows: list[dict[str, object]] = []
    over_budget_rows: list[dict[str, object]] = []
    for revision in revisions:
        item = revision_items.get(revision)
        stats = stats_by_key.get(_measurement_key(item)) if item else None
        for metric_name in TREND_TIME_METRICS:
            metric = _metric_stats(stats, metric_name)
            value = metric.get(statistic) if metric else None
            valid_count = metric.get("ValidFrameCount", 0) if metric else 0
            actual_value = value if valid_count and value is not None else None
            time_rows.append(
                {
                    "revision": revision,
                    "revision_label": str(revision),
                    "metric": metric_name,
                    "actual_value": actual_value,
                    "display_value": min(float(actual_value), TREND_TIME_Y_MAX_MS)
                    if actual_value is not None
                    else None,
                    "is_overflow": actual_value is not None and actual_value > TREND_TIME_Y_MAX_MS,
                }
            )
        for display_name, metric_name in TREND_OVER_BUDGET_METRICS:
            metric = _metric_stats(stats, metric_name)
            count = metric.get("OverBudgetFrameCount") if metric else None
            valid_count = metric.get("ValidFrameCount", 0) if metric else 0
            over_budget_rows.append(
                {
                    "revision": revision,
                    "revision_label": str(revision),
                    "metric": display_name,
                    "value": count if valid_count and count is not None else None,
                }
            )
    return pd.DataFrame(time_rows), pd.DataFrame(over_budget_rows)


def _time_trend_chart(data: pd.DataFrame) -> alt.Chart:
    revision_sort = [str(value) for value in sorted(data["revision"].unique())]
    color_scale = alt.Scale(
        domain=list(TREND_TIME_METRICS),
        range=[TREND_COLORS[name] for name in TREND_TIME_METRICS],
    )
    base = alt.Chart(data).encode(
        x=alt.X("revision_label:O", title="Revision", sort=revision_sort),
        color=alt.Color("metric:N", title="指標", scale=color_scale),
    )
    lines = base.mark_line(point=True, invalid="break-paths-show-domains").encode(
        y=alt.Y(
            "display_value:Q",
            title="処理時間 (ms)",
            scale=alt.Scale(domain=[0, TREND_TIME_Y_MAX_MS], nice=False),
        ),
        tooltip=[
            alt.Tooltip("revision:Q", title="Revision", format="d"),
            alt.Tooltip("metric:N", title="指標"),
            alt.Tooltip("actual_value:Q", title="実測値 (ms)", format=".2f"),
        ],
    )
    overflow = base.transform_filter("datum.is_overflow").mark_point(
        shape="triangle-up", size=100, filled=True, clip=False
    ).encode(
        y=alt.Y("display_value:Q", scale=alt.Scale(domain=[0, TREND_TIME_Y_MAX_MS], nice=False)),
        tooltip=[
            alt.Tooltip("revision:Q", title="Revision", format="d"),
            alt.Tooltip("metric:N", title="指標"),
            alt.Tooltip("actual_value:Q", title="実測値 (ms)", format=".2f"),
        ],
    )
    labels = base.transform_filter("datum.is_overflow").mark_text(
        align="left", dx=6, dy=-5, clip=False
    ).encode(
        y=alt.Y("display_value:Q", scale=alt.Scale(domain=[0, TREND_TIME_Y_MAX_MS], nice=False)),
        text=alt.Text("actual_value:Q", format=".2f"),
    )
    budget = alt.Chart(pd.DataFrame({"budget": [TREND_FRAME_BUDGET_MS]})).mark_rule(
        color="#666666", strokeDash=[4, 4]
    ).encode(y=alt.Y("budget:Q", title="処理時間 (ms)"))
    return alt.layer(budget, lines, overflow, labels).resolve_scale(color="shared")


def _over_budget_trend_chart(data: pd.DataFrame) -> alt.Chart:
    revision_sort = [str(value) for value in sorted(data["revision"].unique())]
    color_scale = alt.Scale(
        domain=[name for name, _ in TREND_OVER_BUDGET_METRICS],
        range=[TREND_COLORS[name] for name, _ in TREND_OVER_BUDGET_METRICS],
    )
    return (
        alt.Chart(data)
        .mark_line(point=True, invalid="break-paths-show-domains")
        .encode(
            x=alt.X("revision_label:O", title="Revision", sort=revision_sort),
            y=alt.Y("value:Q", title="超過回数 (回)", scale=alt.Scale(zero=True)),
            color=alt.Color("metric:N", title="指標", scale=color_scale),
            tooltip=[
                alt.Tooltip("revision:Q", title="Revision", format="d"),
                alt.Tooltip("metric:N", title="指標"),
                alt.Tooltip("value:Q", title="超過回数", format=".0f"),
            ],
        )
    )


def _render_revision_trends(
    measurements: list[Measurement],
    stats_by_key: dict[tuple[str, str], dict[str, object] | None],
    statistic: str,
) -> None:
    st.header("Revision推移グラフ")
    if not measurements:
        st.info("Revision推移グラフの対象データがありません。")
        return
    for level_name in _trend_levels(measurements):
        time_data, over_budget_data = _trend_data(
            measurements, stats_by_key, level_name, statistic
        )
        st.subheader(level_name)
        if time_data["actual_value"].notna().any():
            st.altair_chart(_time_trend_chart(time_data), width="stretch")
        else:
            st.info("処理時間の有効な統計値がありません。")
        if over_budget_data["value"].notna().any():
            st.altair_chart(_over_budget_trend_chart(over_budget_data), width="stretch")
        else:
            st.info("超過回数の有効な統計値がありません。")


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

    stats_by_key, missing_statistics_cache_count = _load_statistics_for_measurements(
        measurements
    )
    if missing_statistics_cache_count:
        st.warning(
            "StatisticsCacheが不足しています。\n"
            f"{missing_statistics_cache_count}件の計測データに対応する有効なStatisticsCacheが存在しません。\n"
            "generate_statistics.py を実行してください。"
        )

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
    _initialize_revision_selection(revision_names)
    current_revision = st.selectbox(
        "Current Revision",
        revision_names,
        key="current_revision",
    )
    previous_revision = st.selectbox(
        "Previous Revision",
        revision_names if len(revision_names) >= 2 else [None],
        format_func=lambda value: "N/A" if value is None else value,
        disabled=len(revision_names) < 2,
        key="previous_revision",
    )
    st.write(f"Current : `{current_revision}`")
    st.write(f"Previous: `{previous_revision or 'N/A'}`")

    statistic = st.radio("Statistic", ("Mean", "Median", "Max"), horizontal=True, index=0)
    current_items = _revision_measurements(measurements, current_revision)
    previous_items = _revision_measurements(measurements, previous_revision) if previous_revision else {}

    st.divider()
    st.header("Level一覧")
    _render_overview(current_items, previous_items, statistic, stats_by_key)

    previous_only = sorted(set(previous_items) - set(current_items))
    if previous_only:
        st.warning("Previous Revisionにのみ存在するLevel: " + ", ".join(previous_only))

    st.divider()
    _render_revision_trends(measurements, stats_by_key, statistic)

    if not current_items:
        return
    st.divider()
    selected_level = st.selectbox("詳細を表示するLevel", sorted(current_items))
    _render_detail(selected_level, current_items, previous_items, stats_by_key)


if __name__ == "__main__":
    main()

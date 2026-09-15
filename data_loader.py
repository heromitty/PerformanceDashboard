"""Discovery and CSV analysis helpers for the performance dashboard."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


LOGGER = logging.getLogger(__name__)

REVISION_DIR_RE = re.compile(r"^Rev(?P<number>\d+)(?:_|$)")
LEVEL_RE = re.compile(r"(?<![A-Za-z0-9_])L_[A-Za-z0-9_]+")

METRIC_COLUMNS = {
    "FrameTime": "FrameTime",
    "GameThread": "GameThreadTime",
    "RenderThread": "RenderThreadTime",
    "GPU": "GPUTime",
}


class DuplicateRevisionError(ValueError):
    """Raised when two folders have the same numeric revision."""


@dataclass(frozen=True)
class RevisionInfo:
    folder_name: str
    path: Path
    number: int


@dataclass(frozen=True)
class Measurement:
    revision_folder: str
    revision_number: int
    level_name: str
    csv_path: Path
    graph_cache_path: Path


def extract_revision_number(folder_name: str) -> Optional[int]:
    match = REVISION_DIR_RE.match(folder_name)
    return int(match.group("number")) if match else None


def extract_level_name(file_name: str) -> Optional[str]:
    """Extract the first UE5 Level token from a file name."""
    matches = LEVEL_RE.findall(Path(file_name).stem)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"複数のLevel名候補があります: {file_name}: {matches}")
    return matches[0]


def discover_revisions(sample_root: Path) -> list[RevisionInfo]:
    """Find valid direct-child revision folders and fail on duplicate numbers."""
    revisions: list[RevisionInfo] = []
    seen: dict[int, Path] = {}

    if not sample_root.exists():
        raise FileNotFoundError(f"SampleDataが見つかりません: {sample_root}")

    for path in sorted(p for p in sample_root.iterdir() if p.is_dir()):
        number = extract_revision_number(path.name)
        if number is None:
            LOGGER.warning("Revision形式でないフォルダを除外します: %s", path)
            continue
        if number in seen:
            raise DuplicateRevisionError(
                f"Revision番号が重複しています: {number} ({seen[number].name}, {path.name})"
            )
        seen[number] = path
        revisions.append(RevisionInfo(path.name, path, number))

    return sorted(revisions, key=lambda item: item.number)


def _asset_map(
    revision: RevisionInfo, suffix: str
) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    for path in sorted(revision.path.rglob(f"*{suffix}")):
        try:
            level = extract_level_name(path.name)
        except ValueError as exc:
            LOGGER.warning("Level名が曖昧なファイルを除外します: %s", exc)
            continue
        if level is None:
            LOGGER.warning("Level名を抽出できないファイルを除外します: %s", path)
            continue
        if level in assets:
            LOGGER.warning("同一Revision内で%sが重複しています: %s", level, path.parent)
            continue
        assets[level] = path
    return assets


def discover_measurements(
    sample_root: Path, graph_cache_root: Optional[Path] = None
) -> list[Measurement]:
    """Discover CSVs and map them to pre-generated graph cache paths."""
    graph_cache_root = graph_cache_root or sample_root.parent / "GraphCache"
    measurements: list[Measurement] = []

    for revision in discover_revisions(sample_root):
        csvs = _asset_map(revision, ".csv")
        for level, csv_path in sorted(csvs.items()):
            measurements.append(
                Measurement(
                    revision.folder_name,
                    revision.number,
                    level,
                    csv_path,
                    graph_cache_root / revision.folder_name / f"{level}.png",
                )
            )
    return measurements


def load_frame_data(csv_path: Path) -> pd.DataFrame:
    """Load frame candidates while retaining per-metric missing values.

    Non-frame command rows are excluded by the semantic ``EVENTS`` prefix.
    Repeated headers and metadata rows become all-NaN after numeric conversion
    and are removed without relying on a fixed footer length.
    """
    required = ["EVENTS", *METRIC_COLUMNS.values()]
    header = pd.read_csv(csv_path, nrows=0)
    missing = [column for column in required if column not in header.columns]
    if missing:
        raise ValueError(f"対象列がありません: {csv_path}: {', '.join(missing)}")

    frame_df = pd.read_csv(
        csv_path,
        usecols=required,
        dtype=str,
        on_bad_lines="skip",
    )
    events = frame_df["EVENTS"].fillna("").astype(str).str.strip()
    not_command = ~events.str.startswith("Cmd:")

    for column in METRIC_COLUMNS.values():
        frame_df[column] = pd.to_numeric(frame_df[column], errors="coerce")

    numeric_candidate = frame_df[list(METRIC_COLUMNS.values())].notna().any(axis=1)
    frame_df = frame_df.loc[not_command & numeric_candidate].copy()
    frame_df.insert(0, "Frame", range(1, len(frame_df) + 1))
    return frame_df.reset_index(drop=True)


def calculate_statistics(frame_df: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    """Return Mean, Median, and Max for each display metric."""
    result: dict[str, dict[str, float | None]] = {}
    for display_name, column in METRIC_COLUMNS.items():
        values = pd.to_numeric(frame_df[column], errors="coerce").dropna()
        result[display_name] = {
            "Mean": float(values.mean()) if not values.empty else None,
            "Median": float(values.median()) if not values.empty else None,
            "Max": float(values.max()) if not values.empty else None,
        }
    return result


def load_statistics(csv_path: Path) -> dict[str, dict[str, float | None]]:
    return calculate_statistics(load_frame_data(csv_path))


def graph_cache_path(
    graph_cache_root: Path, revision_folder: str, level_name: str
) -> Path:
    return graph_cache_root / revision_folder / f"{level_name}.png"

"""Generate persistent per-Revision/Level statistics caches."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from data_loader import (
    calculate_statistics_cache,
    discover_measurements,
    load_frame_data,
    save_statistics_cache,
    validate_statistics_cache,
)


LOGGER = logging.getLogger(__name__)


def statistics_cache_path(
    statistics_cache_root: Path, revision_folder: str, level_name: str
) -> Path:
    return statistics_cache_root / revision_folder / f"{level_name}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate UE5 CSVProfiler statistics cache"
    )
    parser.add_argument(
        "--input-data", type=Path, default=Path(__file__).parent / "SanitizedData"
    )
    parser.add_argument(
        "--statistics-cache",
        type=Path,
        default=Path(__file__).parent / "StatisticsCache",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    measurements = discover_measurements(args.input_data)
    generated = regenerated = skipped = errors = 0
    for measurement in measurements:
        output_path = statistics_cache_path(
            args.statistics_cache, measurement.revision_folder, measurement.level_name
        )
        valid, reason = validate_statistics_cache(
            output_path,
            measurement.revision_folder,
            measurement.revision_number,
            measurement.level_name,
        )
        if valid:
            LOGGER.info("スキップ: %s", output_path)
            skipped += 1
            continue

        is_regeneration = output_path.exists()
        try:
            frame_df = load_frame_data(measurement.csv_path)
            payload = calculate_statistics_cache(
                frame_df,
                measurement.revision_folder,
                measurement.revision_number,
                measurement.level_name,
            )
            save_statistics_cache(output_path, payload)
            if is_regeneration:
                regenerated += 1
                LOGGER.info("再生成: %s (%s)", output_path, reason)
            else:
                generated += 1
                LOGGER.info("生成: %s", output_path)
        except Exception as exc:
            errors += 1
            LOGGER.error("統計キャッシュ生成に失敗しました (%s): %s", measurement.csv_path, exc)

    total = len(measurements)
    LOGGER.info(
        "完了: 対象CSV数=%d, 新規生成数=%d, 再生成数=%d, スキップ数=%d, エラー数=%d",
        total,
        generated,
        regenerated,
        skipped,
        errors,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Sanitize UE5 CSVProfiler CSV files for external sharing.

Input files are read from RawData/ and written to SanitizedData/ without
modifying the originals.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


INPUT_DIR = Path(__file__).resolve().parent / "RawData"
OUTPUT_DIR = Path(__file__).resolve().parent / "SanitizedData"
METADATA_MARKER = "HasHeaderRowAtEnd"


def sanitize_file(input_path: Path, output_path: Path) -> bool:
    """Sanitize one CSV and return whether a warning was emitted."""
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))

    if not rows:
        raise ValueError("CSV is empty")

    header = rows[0]
    keep_indexes = [
        index
        for index, column in enumerate(header)
        if not (
            column.startswith("Ticks/") and column != "Ticks/Total"
        )
        and not (
            column.startswith("ActorCount/")
            and column != "ActorCount/TotalActorCount"
        )
    ]
    removed_ticks = sum(
        column.startswith("Ticks/") and column != "Ticks/Total"
        for column in header
    )
    removed_actor_counts = sum(
        column.startswith("ActorCount/")
        and column != "ActorCount/TotalActorCount"
        for column in header
    )

    metadata_removed = bool(
        rows[-1] and any(METADATA_MARKER in value for value in rows[-1])
    )
    data_rows = rows[:-1] if metadata_removed else rows
    warning = not metadata_removed

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, lineterminator="\n")
        for row in data_rows:
            writer.writerow([row[index] for index in keep_indexes if index < len(row)])

    print(f"処理: {input_path}")
    print(f"  削除 Ticks/* 列: {removed_ticks}")
    print(f"  削除 ActorCount/* 列: {removed_actor_counts}")
    print(
        "  HasHeaderRowAtEnd 行: "
        + ("削除" if metadata_removed else "未検出（警告）")
    )
    print(f"  出力先: {output_path}")
    return warning


def main() -> int:
    """Sanitize all CSV files below RawData/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    input_files = sorted(INPUT_DIR.rglob("*.csv")) if INPUT_DIR.exists() else []

    success_count = 0
    warning_count = 0
    error_count = 0

    for input_path in input_files:
        output_path = OUTPUT_DIR / input_path.relative_to(INPUT_DIR)
        try:
            if sanitize_file(input_path, output_path):
                warning_count += 1
            success_count += 1
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            error_count += 1
            print(f"エラー: {input_path}: {error}", file=sys.stderr)

    print("--- 集計 ---")
    print(f"処理成功ファイル数: {success_count}")
    print(f"警告ファイル数: {warning_count}")
    print(f"エラーファイル数: {error_count}")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

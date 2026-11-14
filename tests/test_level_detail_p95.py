import unittest

import pandas as pd

from app import _cell_style, _change_percent, _format_change, _format_over_budget
from data_loader import DETAIL_METRIC_COLUMNS, calculate_statistics


class LevelDetailP95Tests(unittest.TestCase):
    def test_calculates_p95_for_all_detail_metrics(self):
        frame_df = pd.DataFrame(
            {
                "FrameTime": [1, 2, 3, 4, 100],
                "GameThreadTime": [2, 3, 4, 5, 100],
                "RenderThreadTime": [3, 4, 5, 6, 100],
                "GPUTime": [4, 5, 6, 7, 100],
                "GPU/Translucency": [5, 6, 7, 8, 100],
            }
        )

        result = calculate_statistics(frame_df)

        for display_name, column in DETAIL_METRIC_COLUMNS.items():
            values = result[display_name]
            self.assertEqual(values["Mean"], float(values["Mean"]))
            self.assertEqual(values["Median"], float(values["Median"]))
            self.assertEqual(values["Max"], float(values["Max"]))
            if column in frame_df:
                self.assertEqual(values["P95"], float(frame_df[column].quantile(0.95)))
            else:
                self.assertIsNone(values["P95"])

    def test_change_percent_and_existing_threshold_colors_apply_to_p95(self):
        self.assertAlmostEqual(_change_percent(110, 100), 10)
        self.assertAlmostEqual(_change_percent(105, 100), 5)
        self.assertAlmostEqual(_change_percent(90, 100), -10)
        self.assertIsNone(_change_percent(10, 0))
        self.assertIsNone(_change_percent(None, 100))
        for change, expected in (
            (4.96, "+4.96%"),
            (5, "+5.00%"),
            (10, "+10.00%"),
            (-10, "-10.00%"),
        ):
            self.assertEqual(_format_change(change), expected)
        self.assertEqual(_format_change(None), "N/A")
        self.assertEqual(_cell_style(4.96), "")
        self.assertEqual(_cell_style(10), "background-color: #ffd6d6; color: #9b1c1c")
        self.assertEqual(_cell_style(5), "background-color: #fff0bf; color: #7a5600")
        self.assertEqual(_cell_style(-10), "background-color: #d9f2d9; color: #1f6b1f")
        self.assertEqual(_cell_style(None), "")

    def test_empty_and_missing_detail_values_are_safe(self):
        result = calculate_statistics(
            pd.DataFrame(
                {
                    "FrameTime": [],
                    "GameThreadTime": [],
                    "RenderThreadTime": [],
                    "GPUTime": [],
                }
            )
        )

        self.assertIsNone(result["FrameTime"]["P95"])
        self.assertIsNone(result["Translucency"]["P95"])

    def test_over_budget_displays_count_delta(self):
        def stats(count):
            return {"OverBudgetFrameCount": count, "OverBudgetRate": 1.0}

        self.assertEqual(_format_over_budget(stats(0), stats(2)), "0 (-2)")
        self.assertEqual(_format_over_budget(stats(5), stats(5)), "5 (0)")
        self.assertEqual(_format_over_budget(stats(14), stats(11)), "14 (+3)")

    def test_over_budget_previous_zero_uses_count_delta(self):
        current = {"OverBudgetFrameCount": 5, "OverBudgetRate": 1.0}
        previous = {"OverBudgetFrameCount": 0, "OverBudgetRate": 0.0}

        self.assertEqual(_format_over_budget(current, previous), "5 (+5)")


if __name__ == "__main__":
    unittest.main()

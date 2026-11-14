import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd

from generate_heatmaps import _generate_heatmap


class GenerateHeatmapsTests(unittest.TestCase):
    def _generate(self, x_values, y_values):
        frame_df = pd.DataFrame(
            {
                "Frame": list(range(1, len(x_values) + 1)),
                "View/PosX": x_values,
                "View/PosY": y_values,
                "FrameTime": [10.0, 20.0, 40.0][:len(x_values)],
            }
        )
        with patch("generate_heatmaps.plt.close"):
            with patch("matplotlib.figure.Figure.savefig"):
                result = _generate_heatmap(
                    frame_df,
                    "Revision1",
                    "TestLevel",
                    "FrameTime",
                    Path("heatmap.png"),
                )
        figure = plt.gcf()
        axis = figure.axes[0]
        self.addCleanup(plt.close, figure)
        return result, axis

    def test_axes_are_inverted_for_positive_negative_and_mixed_coordinates(self):
        for x_values, y_values in (
            ([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]),
            ([-1.0, -2.0, -3.0], [-1.0, -2.0, -3.0]),
            ([-1.0, 0.0, 2.0], [-2.0, 0.0, 1.0]),
        ):
            with self.subTest(x_values=x_values, y_values=y_values):
                _, axis = self._generate(x_values, y_values)

                self.assertFalse(axis.xaxis_inverted())
                self.assertTrue(axis.yaxis_inverted())
                self.assertEqual(
                    list(axis.collections[0].get_offsets()[:, 0]), x_values
                )
                self.assertEqual(
                    list(axis.collections[0].get_offsets()[:, 1]), y_values
                )

    def test_threshold_and_max_metadata_keep_original_coordinates(self):
        result, axis = self._generate([-2.0, 1.0, 3.0], [4.0, -1.0, 2.0])

        self.assertEqual(result["over_count"], 2)
        self.assertEqual(result["max_frame"], 3)
        self.assertEqual(result["max_x"], 3.0)
        self.assertEqual(result["max_y"], 2.0)
        self.assertEqual(axis.texts[0].xy, (3.0, 2.0))


if __name__ == "__main__":
    unittest.main()

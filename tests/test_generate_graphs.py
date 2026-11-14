import unittest

import matplotlib.pyplot as plt
import pandas as pd

from generate_graphs import GRAPH_Y_MAX_MS, _plot_metric


class GenerateGraphsTests(unittest.TestCase):
    def setUp(self):
        self.frame_df = pd.DataFrame(
            {
                "Frame": [1, 2, 3, 4, 5, 6],
                "FrameTime": [34.9, 35.0, 35.1, 40.0, 35.2, 20.0],
            }
        )
        self.figure, self.ax = plt.subplots()

    def tearDown(self):
        plt.close(self.figure)

    def test_values_below_and_at_limit_are_not_overflow(self):
        _plot_metric(self.ax, self.frame_df.iloc[[0, 1]], "FrameTime", "FrameTime")

        self.assertEqual(len(self.ax.collections), 0)
        self.assertEqual(list(self.ax.lines[0].get_ydata()), [34.9, 35.0])

    def test_overflow_values_are_clipped_and_marked_with_original_values(self):
        _plot_metric(self.ax, self.frame_df, "FrameTime", "FrameTime")

        self.assertEqual(len(self.ax.collections), 1)
        self.assertEqual(list(self.ax.lines[0].get_ydata()), [34.9, 35.0, 35.0, 35.0, 35.0, 20.0])
        self.assertEqual(len(self.ax.texts), 3)
        self.assertEqual([text.get_text() for text in self.ax.texts], ["35.1", "40.0", "35.2"])
        self.assertEqual(list(self.frame_df["FrameTime"]), [34.9, 35.0, 35.1, 40.0, 35.2, 20.0])

    def test_no_overflow_data_has_no_marker_or_annotation(self):
        data = self.frame_df.assign(FrameTime=[10.0, 20.0, 30.0, 35.0, 1.0, 2.0])
        _plot_metric(self.ax, data, "FrameTime", "FrameTime")

        self.assertEqual(len(self.ax.collections), 0)
        self.assertEqual(len(self.ax.texts), 0)

    def test_graph_upper_limit_is_fixed(self):
        self.ax.set_ylim(bottom=0, top=GRAPH_Y_MAX_MS)

        self.assertEqual(self.ax.get_ylim(), (0.0, GRAPH_Y_MAX_MS))


if __name__ == "__main__":
    unittest.main()

"""闭环仿真关键行为测试。"""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import numpy as np

from calligrapher.sim_brush import BrushWorld, StrokeAction, binary_ink, render_stroke
from calligrapher.sim_cli import DEFAULT_GRAPHICS
from calligrapher.sim_control import run_character
from calligrapher.sim_data import load_glyph_target, svg_path_polygons
from calligrapher.sim_planner import calibrate_brush, plan_actions
from calligrapher.sim_suite import run_suite


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.target = load_glyph_target(DEFAULT_GRAPHICS, "永", size=128)

    def test_svg_curves_and_target_strokes(self) -> None:
        polygons = svg_path_polygons("M 0 0 Q 5 10 10 0 C 11 0 12 1 13 0 Z")
        self.assertEqual(len(polygons), 1)
        self.assertGreater(len(polygons[0]), 5)
        self.assertEqual(len(self.target.paths), 5)
        self.assertTrue(all(mask.max() > 0 for mask in self.target.stroke_masks))

    def test_virtual_calibration_follows_depth_and_speed(self) -> None:
        world = BrushWorld()
        calibration = calibrate_brush(world, 128)
        self.assertLess(calibration.rmse_px, 1.0)
        self.assertGreater(float(calibration.width(0.8, 0.9)), float(calibration.width(0.4, 0.9)))
        self.assertGreater(float(calibration.width(0.6, 0.55)), float(calibration.width(0.6, 1.25)))
        line = np.column_stack((np.linspace(0.2, 0.8, 32), np.full(32, 0.5)))
        shallow = render_stroke(StrokeAction(line, np.full(32, 0.4), np.full(32, 0.9)), world, 128)
        deep = render_stroke(StrokeAction(line, np.full(32, 0.8), np.full(32, 0.9)), world, 128)
        self.assertGreater(binary_ink(deep).sum(), binary_ink(shallow).sum())

    def test_visual_feedback_corrects_position_disturbance(self) -> None:
        world = BrushWorld(xy_bias=(0.012, -0.009), paper_warp=0.005)
        actions = plan_actions(self.target, calibrate_brush(world, 128))
        opened = run_character(self.target, actions, world, feedback=False)
        closed = run_character(self.target, actions, world, feedback=True)
        self.assertLess(closed.final_metrics["weighted_error"], opened.final_metrics["weighted_error"])
        self.assertNotEqual(closed.outcomes[1].applied_dx, 0.0)
        self.assertEqual(opened.outcomes[1].applied_dx, 0.0)

    def test_batch_output_is_summary_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            results = run_suite("永", ["standard"], DEFAULT_GRAPHICS, output, 128)
            self.assertEqual(len(results), 1)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"suite_metrics.csv", "实验结果.md"},
            )


if __name__ == "__main__":
    unittest.main()

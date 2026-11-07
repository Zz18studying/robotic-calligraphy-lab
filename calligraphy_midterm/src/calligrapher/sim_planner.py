"""通过虚拟标定数据学习笔触宽度，再从目标轮廓反推动作。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .geometry import normalized_curvature
from .sim_brush import BrushWorld, StrokeAction, binary_ink, render_stroke
from .sim_data import GlyphTarget


@dataclass
class Calibration:
    coefficients: list[float]
    rmse_px: float
    samples: list[dict[str, float]]

    def width(self, depth: float | np.ndarray, speed: float | np.ndarray) -> np.ndarray:
        a, b, c, d = self.coefficients
        return a + b * depth + c / speed + d * depth / speed

    def depth_for_width(self, width: np.ndarray, speed: np.ndarray) -> np.ndarray:
        a, b, c, d = self.coefficients
        denominator = b + d / speed
        return np.clip((width - a - c / speed) / np.maximum(denominator, 1e-5), 0.12, 1.10)

    def to_dict(self) -> dict:
        return asdict(self)


def calibrate_brush(world: BrushWorld, size: int) -> Calibration:
    """虚拟试笔：多档下压量、速度 -> 墨迹宽度的回归模型。"""
    x = np.linspace(0.17, 0.83, 82)
    line = np.column_stack((x, np.full_like(x, 0.28)))
    rows: list[list[float]] = []
    widths: list[float] = []
    samples: list[dict[str, float]] = []
    for depth in (0.26, 0.42, 0.58, 0.74, 0.90):
        for speed in (0.55, 0.90, 1.25):
            action = StrokeAction(line, np.full(len(line), depth), np.full(len(line), speed))
            image = render_stroke(action, world, size)
            area = int(binary_ink(image).sum())
            length = (x[-1] - x[0]) * (size - 1)
            width = area / length
            rows.append([1.0, depth, 1.0 / speed, depth / speed])
            widths.append(width)
            samples.append({"depth_command": depth, "speed_command": speed, "observed_width_px": round(width, 4)})
    design = np.asarray(rows)
    observed = np.asarray(widths)
    coefficients, *_ = np.linalg.lstsq(design, observed, rcond=None)
    fitted = design @ coefficients
    rmse = float(np.sqrt(np.mean((fitted - observed) ** 2)))
    if coefficients[1] + coefficients[3] / 1.0 <= 0:
        raise ValueError("标定失败：笔触宽度未随下压量增加")
    return Calibration(coefficients.tolist(), rmse, samples)


def _mean_filter(values: np.ndarray, window: int = 7) -> np.ndarray:
    if window <= 1:
        return values.copy()
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def target_cross_sections(path: np.ndarray, target_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """沿中线法向量测笔画轮廓，返回目标宽度和中心线修正量。"""
    size = target_mask.shape[0]
    gradient = np.gradient(path, axis=0)
    tangent = gradient / np.maximum(np.linalg.norm(gradient, axis=1, keepdims=True), 1e-8)
    normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    binary = target_mask >= 0.5
    widths = []
    offsets = []
    for point, direction in zip(path, normal):
        center = point * (size - 1)
        side_lengths = []
        for sign in (-1.0, 1.0):
            extent = 0
            for distance in range(0, min(30, size // 5)):
                xy = np.rint(center + sign * direction * distance).astype(int)
                x, y = int(xy[0]), int(xy[1])
                if x < 0 or x >= size or y < 0 or y >= size or not binary[y, x]:
                    break
                extent = distance
            side_lengths.append(extent)
        minus, plus = side_lengths
        widths.append(float(minus + plus + 1))
        offsets.append(float(plus - minus) / 2.0)
    return _mean_filter(np.asarray(widths)), _mean_filter(np.asarray(offsets))


def plan_actions(target: GlyphTarget, calibration: Calibration) -> list[StrokeAction]:
    planned: list[StrokeAction] = []
    for path, mask in zip(target.paths, target.stroke_masks):
        curvature = normalized_curvature(path)
        speed = np.clip(1.05 - 0.36 * curvature, 0.55, 1.10)
        speed[:3] *= 0.8
        speed[-3:] *= 0.8
        desired_width, offset_px = target_cross_sections(path, mask)
        offset_px = np.clip(offset_px, -target.size * 0.023, target.size * 0.023)
        gradient = np.gradient(path, axis=0)
        tangent = gradient / np.maximum(np.linalg.norm(gradient, axis=1, keepdims=True), 1e-8)
        normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
        corrected_path = path + normal * (offset_px / target.size)[:, None]
        depth = calibration.depth_for_width(np.clip(desired_width, 2.5, 24.0), speed)
        depth = _mean_filter(depth, window=5)
        planned.append(StrokeAction(corrected_path, depth, speed))
    return planned

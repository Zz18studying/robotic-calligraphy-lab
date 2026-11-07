"""开环和逐笔视觉反馈控制对照。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .sim_brush import BrushWorld, StrokeAction, binary_ink, composite, render_stroke
from .sim_data import GlyphTarget


@dataclass
class StrokeOutcome:
    stroke_index: int
    iou: float
    missing_pixels: int
    excess_pixels: int
    target_area: int
    actual_area: int
    centroid_error_x_px: float
    centroid_error_y_px: float
    applied_dx: float
    applied_dy: float
    applied_depth_scale: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunResult:
    mode: str
    image: np.ndarray
    stroke_images: list[np.ndarray]
    executed_actions: list[StrokeAction]
    outcomes: list[StrokeOutcome]
    final_metrics: dict[str, float]


def mask_metrics(target: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    reference = binary_ink(target, threshold=0.5)
    observed = binary_ink(actual)
    intersection = int(np.logical_and(reference, observed).sum())
    union = int(np.logical_or(reference, observed).sum())
    missing = int(np.logical_and(reference, ~observed).sum())
    excess = int(np.logical_and(observed, ~reference).sum())
    area = int(reference.sum())
    return {
        "iou": intersection / max(union, 1),
        "missing_pixels": float(missing),
        "excess_pixels": float(excess),
        "target_area": float(area),
        "actual_area": float(observed.sum()),
        "weighted_error": (missing + 2.0 * excess) / max(area, 1),
    }


def _centroid(mask: np.ndarray, threshold: float) -> np.ndarray:
    ys, xs = np.nonzero(mask >= threshold)
    if len(xs) == 0:
        return np.array((np.nan, np.nan))
    return np.array((float(xs.mean()), float(ys.mean())))


def run_character(
    target: GlyphTarget,
    actions: list[StrokeAction],
    world: BrushWorld,
    feedback: bool,
    position_gain: float = 0.40,
    width_gain: float = 0.14,
) -> RunResult:
    if len(actions) != len(target.stroke_masks):
        raise ValueError("动作与目标笔画数量不一致")
    canvas = np.zeros((target.size, target.size), dtype=np.float32)
    target_canvas = np.zeros_like(canvas)
    stroke_images = []
    executed_actions = []
    outcomes = []
    offset = np.zeros(2, dtype=float)
    depth_scale = 1.0
    for index, (base_action, desired) in enumerate(zip(actions, target.stroke_masks)):
        action = StrokeAction(
            path=np.clip(base_action.path + offset, 0.0, 1.0),
            depth=np.clip(base_action.depth * depth_scale, 0.10, 1.15),
            speed=base_action.speed,
        )
        executed_actions.append(action)
        actual = render_stroke(action, world, target.size, stroke_index=index)
        stroke_images.append(actual)
        before = canvas.copy()
        canvas = composite(canvas, actual)
        # 真正可由相机观测的是前后图像差，而非隐藏的单笔墨迹。
        visible_actual = np.logical_and(binary_ink(canvas), ~binary_ink(before)).astype(np.float32)
        visible_target = np.logical_and(binary_ink(desired, 0.5), ~binary_ink(target_canvas, 0.5)).astype(np.float32)
        target_canvas = np.maximum(target_canvas, desired)
        metrics = mask_metrics(visible_target, visible_actual)
        target_center = _centroid(visible_target, 0.5)
        actual_center = _centroid(visible_actual, 0.5)
        error = actual_center - target_center
        if not np.isfinite(error).all():
            error = np.zeros(2)
        outcomes.append(
            StrokeOutcome(
                stroke_index=index + 1,
                iou=metrics["iou"],
                missing_pixels=int(metrics["missing_pixels"]),
                excess_pixels=int(metrics["excess_pixels"]),
                target_area=int(metrics["target_area"]),
                actual_area=int(metrics["actual_area"]),
                centroid_error_x_px=float(error[0]),
                centroid_error_y_px=float(error[1]),
                applied_dx=float(offset[0]),
                applied_dy=float(offset[1]),
                applied_depth_scale=float(depth_scale),
            )
        )
        if feedback:
            offset = np.clip(offset - position_gain * error / target.size, -0.035, 0.035)
            if metrics["actual_area"] > 0:
                # 已落在目标外的墨迹无法撤销，宽度更新必须对越界更保守。
                effective_target_area = max(1.0, metrics["target_area"] - 1.5 * metrics["excess_pixels"])
                ratio = effective_target_area / metrics["actual_area"]
                depth_scale = float(np.clip(depth_scale * ratio**width_gain, 0.70, 1.35))
    return RunResult(
        mode="closed_loop" if feedback else "open_loop",
        image=canvas,
        stroke_images=stroke_images,
        executed_actions=executed_actions,
        outcomes=outcomes,
        final_metrics=mask_metrics(target.mask, canvas),
    )

"""用于算法验证的虚拟毛笔与纸面模型，不等同于真实毛笔物理。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BrushWorld:
    base_sigma_px: float = 3.15
    contact_gain: float = 1.13
    contact_threshold: float = 0.065
    lag: float = 0.33
    ink_gain: float = 0.94
    paper_spread: float = 1.12
    xy_bias: tuple[float, float] = (0.006, -0.004)
    paper_warp: float = 0.003
    ink_decay_per_stroke: float = 0.025


@dataclass
class StrokeAction:
    path: np.ndarray
    depth: np.ndarray
    speed: np.ndarray

    def validate(self) -> None:
        if self.path.ndim != 2 or self.path.shape[1] != 2:
            raise ValueError("path 应为 N×2 坐标")
        if len(self.path) < 2 or len(self.depth) != len(self.path) or len(self.speed) != len(self.path):
            raise ValueError("path、depth、speed 的长度必须一致且至少为 2")
        if not np.isfinite(self.path).all() or not np.isfinite(self.depth).all() or not np.isfinite(self.speed).all():
            raise ValueError("动作中存在非有限值")


def render_stroke(action: StrokeAction, world: BrushWorld, size: int, stroke_index: int = 0) -> np.ndarray:
    """每个轨迹点落下各向异性笔触，含接触滞后、笔毫拖曳与墨量衰减。"""
    action.validate()
    ink = np.zeros((size, size), dtype=np.float32)
    path = np.asarray(action.path, dtype=float)
    gradient = np.gradient(path, axis=0)
    tangent = gradient / np.maximum(np.linalg.norm(gradient, axis=1, keepdims=True), 1e-8)
    bias = np.array(world.xy_bias, dtype=float)
    brush_tip = path[0] + bias
    force = 0.0

    for point, direction, depth, speed in zip(path, tangent, action.depth, action.speed):
        speed = float(np.clip(speed, 0.25, 2.0))
        desired = point + bias
        desired += world.paper_warp * np.array((np.sin(2 * np.pi * point[1]), np.cos(2 * np.pi * point[0])))
        brush_tip += (1.0 - world.lag) * (desired - brush_tip)
        target_force = np.clip((float(depth) - world.contact_threshold) * world.contact_gain, 0.0, 1.5)
        force += 0.38 * (target_force - force)
        if force < 0.02:
            continue

        normal = np.array((-direction[1], direction[0]))
        sigma_perp = world.base_sigma_px * world.paper_spread * (0.48 + 1.38 * force)
        sigma_perp *= 1.0 - 0.13 * (speed - 1.0)
        sigma_parallel = sigma_perp * (1.18 + 0.24 * force)
        center = (brush_tip - direction * (0.31 * sigma_parallel / size)) * (size - 1)
        radius = int(np.ceil(3.0 * max(sigma_parallel, sigma_perp)))
        cx, cy = float(center[0]), float(center[1])
        left, right = max(0, int(cx) - radius), min(size, int(cx) + radius + 1)
        top, bottom = max(0, int(cy) - radius), min(size, int(cy) + radius + 1)
        if left >= right or top >= bottom:
            continue
        yy, xx = np.mgrid[top:bottom, left:right]
        dx, dy = xx - cx, yy - cy
        along = dx * direction[0] + dy * direction[1]
        across = dx * normal[0] + dy * normal[1]
        footprint = np.exp(-0.5 * ((along / sigma_parallel) ** 2 + (across / sigma_perp) ** 2))
        opacity = world.ink_gain * (1.0 - world.ink_decay_per_stroke * stroke_index)
        opacity *= 0.23 * (0.55 + 0.5 * force) / (0.65 + 0.35 * speed)
        splat = np.clip(opacity * footprint, 0.0, 0.92).astype(np.float32)
        patch = ink[top:bottom, left:right]
        patch[:] = 1.0 - (1.0 - patch) * (1.0 - splat)
    return ink


def composite(previous: np.ndarray, new_stroke: np.ndarray) -> np.ndarray:
    return 1.0 - (1.0 - previous) * (1.0 - new_stroke)


def binary_ink(image: np.ndarray, threshold: float = 0.42) -> np.ndarray:
    return image >= threshold

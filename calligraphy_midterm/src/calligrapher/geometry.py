from __future__ import annotations

import numpy as np


def as_points(points: list[list[float]] | np.ndarray) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError("轨迹点应为 N×2 数组")
    if len(array) < 2:
        raise ValueError("一条轨迹至少需要两个点")
    keep = np.ones(len(array), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(array, axis=0), axis=1) > 1e-9
    array = array[keep]
    if len(array) < 2:
        raise ValueError("轨迹点不能全部重合")
    return array


def resample_polyline(points: np.ndarray, step: float = 0.008) -> np.ndarray:
    points = as_points(points)
    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    total = float(cumulative[-1])
    count = max(12, int(np.ceil(total / step)) + 1)
    targets = np.linspace(0.0, total, count)
    x = np.interp(targets, cumulative, points[:, 0])
    y = np.interp(targets, cumulative, points[:, 1])
    return np.column_stack((x, y))


def smooth_polyline(points: np.ndarray, passes: int = 2) -> np.ndarray:
    result = as_points(points).copy()
    for _ in range(max(0, passes)):
        padded = np.pad(result, ((1, 1), (0, 0)), mode="edge")
        filtered = (padded[:-2] + 2.0 * padded[1:-1] + padded[2:]) / 4.0
        filtered[0] = result[0]
        filtered[-1] = result[-1]
        result = filtered
    return result


def tangent_angles(points: np.ndarray) -> np.ndarray:
    gradient = np.gradient(points, axis=0)
    return np.arctan2(gradient[:, 1], gradient[:, 0])


def normalized_curvature(points: np.ndarray) -> np.ndarray:
    angles = np.unwrap(tangent_angles(points))
    curvature = np.abs(np.gradient(angles))
    scale = float(np.percentile(curvature, 90)) if len(curvature) else 0.0
    if scale < 1e-8:
        return np.zeros(len(points), dtype=np.float64)
    return np.clip(curvature / scale, 0.0, 1.0)


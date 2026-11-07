"""Make Me a Hanzi 笔画轮廓与中心线的统一坐标读取。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .geometry import resample_polyline, smooth_polyline


_TOKEN = re.compile(r"[MLQCZ]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARITY = {"M": 2, "L": 2, "Q": 4, "C": 6, "Z": 0}


@dataclass
class GlyphTarget:
    character: str
    paths: list[np.ndarray]
    stroke_masks: list[np.ndarray]
    mask: np.ndarray
    size: int


def _xy(point: np.ndarray) -> np.ndarray:
    """上游 SVG 坐标转换为左上原点、宽高 1 的纸面坐标。"""
    return np.array((point[0] / 1024.0, (900.0 - point[1]) / 1024.0), dtype=float)


def _sample_curve(start: np.ndarray, controls: list[np.ndarray], end: np.ndarray) -> list[np.ndarray]:
    vertices = [start, *controls, end]
    length = sum(float(np.linalg.norm(b - a)) for a, b in zip(vertices[:-1], vertices[1:]))
    count = max(5, int(np.ceil(length / 13.0)))
    t = np.linspace(0, 1, count + 1)[1:]
    if len(controls) == 1:
        c = controls[0]
        return [(1 - u) ** 2 * start + 2 * (1 - u) * u * c + u**2 * end for u in t]
    a, b = controls
    return [
        (1 - u) ** 3 * start + 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u**2 * b + u**3 * end
        for u in t
    ]


def svg_path_polygons(path: str) -> list[np.ndarray]:
    """解析上游数据实际使用的 M/L/Q/C/Z 绝对命令。"""
    tokens = _TOKEN.findall(path)
    polygons: list[np.ndarray] = []
    current = np.zeros(2, dtype=float)
    subpath: list[np.ndarray] = []
    command: str | None = None
    index = 0
    while index < len(tokens):
        if tokens[index] in _ARITY:
            command = tokens[index]
            index += 1
        if command is None:
            raise ValueError("SVG 路径缺少起始命令")
        if command == "Z":
            if len(subpath) >= 3:
                polygons.append(np.asarray(subpath))
            subpath = []
            command = None
            continue
        arity = _ARITY[command]
        if index + arity > len(tokens):
            raise ValueError(f"不完整的 SVG {command} 命令")
        values = [float(token) for token in tokens[index:index + arity]]
        index += arity
        if command == "M":
            if subpath:
                polygons.append(np.asarray(subpath))
            current = np.array(values)
            subpath = [current.copy()]
            command = "L"
        elif command == "L":
            current = np.array(values)
            subpath.append(current.copy())
        elif command == "Q":
            control = np.array(values[:2])
            end = np.array(values[2:])
            subpath.extend(_sample_curve(current, [control], end))
            current = end
        elif command == "C":
            controls = [np.array(values[:2]), np.array(values[2:4])]
            end = np.array(values[4:])
            subpath.extend(_sample_curve(current, controls, end))
            current = end
    if subpath:
        polygons.append(np.asarray(subpath))
    return polygons


def _rasterize_stroke(path: str, size: int) -> np.ndarray:
    scale = 2
    image = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(image)
    for polygon in svg_path_polygons(path):
        points = [_xy(point) * (size * scale - 1) for point in polygon]
        draw.polygon([(float(p[0]), float(p[1])) for p in points], fill=255)
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def load_glyph_target(graphics_path: str | Path, character: str, size: int = 192) -> GlyphTarget:
    if len(character) != 1:
        raise ValueError("一次仿真只处理一个汉字")
    if size < 96:
        raise ValueError("图像边长至少为 96 像素")
    source = Path(graphics_path)
    if not source.is_file():
        raise FileNotFoundError(f"缺少数据文件：{source}")
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("character") == character:
                break
        else:
            raise KeyError(f"数据文件中没有 {character!r}")
    strokes = record["strokes"]
    medians = record["medians"]
    if len(strokes) != len(medians):
        raise ValueError("笔画轮廓与中心线数量不一致")
    paths = []
    for median in medians:
        points = np.asarray([_xy(np.asarray(point, dtype=float)) for point in median])
        points = resample_polyline(points, step=0.009)
        paths.append(smooth_polyline(points, passes=1))
    masks = [_rasterize_stroke(stroke, size) for stroke in strokes]
    target = np.maximum.reduce(masks)
    return GlyphTarget(character, paths, masks, target, size)

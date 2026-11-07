"""可复现的书法动作标定、轮廓规划与逐笔闭环仿真。"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .sim_brush import BrushWorld, StrokeAction, binary_ink, composite, render_stroke
from .sim_control import RunResult, run_character
from .sim_data import GlyphTarget, load_glyph_target
from .sim_planner import Calibration, calibrate_brush, plan_actions


DEFAULT_GRAPHICS = Path(__file__).resolve().parents[2] / "data" / "graphics.txt"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "outputs" / "ppt_demo"

WORLD_PROFILES = {
    "standard": BrushWorld(),
    "drying": BrushWorld(ink_decay_per_stroke=0.07, paper_spread=1.08),
    "offset": BrushWorld(xy_bias=(0.012, -0.009), paper_warp=0.005),
}


def _flat_action(path: np.ndarray) -> StrokeAction:
    return StrokeAction(path.copy(), np.full(len(path), 0.54), np.full(len(path), 1.0))


def _rgb_ink(image: np.ndarray) -> Image.Image:
    # 仅对展示做纸面色调映射；指标仍在原始合成图像上计算。
    coverage = np.clip((image - 0.08) / 0.55, 0.0, 1.0) ** 0.7
    value = np.clip(248 - 235 * coverage, 0, 255).astype(np.uint8)
    return Image.fromarray(value, mode="L").convert("RGB")


def _error_image(target: np.ndarray, actual: np.ndarray) -> Image.Image:
    t = binary_ink(target, threshold=0.5)
    a = binary_ink(actual)
    pixels = np.full((*t.shape, 3), (248, 246, 239), dtype=np.uint8)
    pixels[t & a] = (36, 56, 44)       # 正确墨迹
    pixels[t & ~a] = (43, 113, 212)    # 漏写
    pixels[~t & a] = (215, 67, 55)     # 越界
    return Image.fromarray(pixels, mode="RGB")


def _comparison_panel(target: GlyphTarget, baseline: RunResult, opened: RunResult, closed: RunResult) -> Image.Image:
    size = target.size
    margin = 14
    label_height = 32
    panel = Image.new("RGB", (size * 4 + margin * 5, size * 2 + label_height * 2 + margin * 3), (236, 236, 232))
    draw = ImageDraw.Draw(panel)
    legend = Image.new("RGB", (size, size), (250, 249, 244))
    legend_draw = ImageDraw.Draw(legend)
    legend_draw.text((10, 12), "ERROR MAP", fill=(30, 34, 36))
    legend_draw.text((10, 42), "BLUE: missing ink", fill=(43, 113, 212))
    legend_draw.text((10, 68), "RED: excess ink", fill=(215, 67, 55))
    legend_draw.text((10, 94), "DARK: overlap", fill=(36, 56, 44))
    legend_draw.text((10, 137), "IoU", fill=(30, 34, 36))
    for index, result in enumerate((baseline, opened, closed)):
        legend_draw.text((10, 160 + index * 23), f"{result.mode if index else 'fixed'}: {result.final_metrics['iou']:.3f}", fill=(30, 34, 36))
    items = [
        ("TARGET", _rgb_ink(target.mask)),
        ("FIXED", _rgb_ink(baseline.image)),
        ("OPEN LOOP", _rgb_ink(opened.image)),
        ("CLOSED LOOP", _rgb_ink(closed.image)),
        ("FIXED ERROR", _error_image(target.mask, baseline.image)),
        ("OPEN ERROR", _error_image(target.mask, opened.image)),
        ("CLOSED ERROR", _error_image(target.mask, closed.image)),
        ("METRICS / LEGEND", legend),
    ]
    for index, (label, picture) in enumerate(items):
        row, column = divmod(index, 4)
        x = margin + column * (size + margin)
        y = margin + row * (size + label_height + margin)
        draw.text((x + 4, y + 5), label, fill=(30, 34, 36))
        panel.paste(picture, (x, y + label_height))
    return panel


def _save_writing_animation(result: RunResult, world: BrushWorld, size: int, path: Path) -> None:
    frames = []
    completed = np.zeros((size, size), dtype=np.float32)
    for stroke_index, action in enumerate(result.executed_actions):
        checkpoints = sorted({max(2, int(len(action.path) * k / 8)) for k in range(1, 9)})
        for stop in checkpoints:
            partial = StrokeAction(action.path[:stop], action.depth[:stop], action.speed[:stop])
            current = composite(completed, render_stroke(partial, world, size, stroke_index))
            frames.append(_rgb_ink(current))
        completed = composite(completed, result.stroke_images[stroke_index])
        frames.extend([_rgb_ink(completed)] * 2)
    if frames:
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def _write_calibration(calibration: Calibration, directory: Path) -> None:
    (directory / "calibration.json").write_text(
        json.dumps(calibration.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (directory / "calibration.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["depth_command", "speed_command", "observed_width_px"])
        writer.writeheader()
        writer.writerows(calibration.samples)


def _write_actions(actions: list[StrokeAction], directory: Path, filename: str) -> None:
    data = [
        {
            "stroke_index": index,
            "points": [
                {"x": round(float(x), 6), "y": round(float(y), 6),
                 "depth_command": round(float(depth), 6), "speed_command": round(float(speed), 6)}
                for (x, y), depth, speed in zip(action.path, action.depth, action.speed)
            ],
        }
        for index, action in enumerate(actions, 1)
    ]
    (directory / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_experiment(
    character: str,
    profile: str,
    graphics_path: Path,
    output_dir: Path,
    size: int = 192,
    make_animation: bool = True,
    save_artifacts: bool = True,
) -> dict:
    if profile not in WORLD_PROFILES:
        raise ValueError(f"未知环境：{profile}")
    world = WORLD_PROFILES[profile]
    target = load_glyph_target(graphics_path, character, size=size)
    calibration = calibrate_brush(world, size)
    fixed_actions = [_flat_action(path) for path in target.paths]
    outline_actions = plan_actions(target, calibration)

    fixed = run_character(target, fixed_actions, world, feedback=False)
    opened = run_character(target, outline_actions, world, feedback=False)
    closed = run_character(target, outline_actions, world, feedback=True)
    if save_artifacts:
        directory = output_dir / f"{character}_{profile}"
        directory.mkdir(parents=True, exist_ok=True)
        _write_calibration(calibration, directory)
        _write_actions(outline_actions, directory, "planned_actions.json")
        _write_actions(closed.executed_actions, directory, "executed_actions.json")
        _rgb_ink(target.mask).save(directory / "target.png")
        _rgb_ink(fixed.image).save(directory / "fixed.png")
        _rgb_ink(opened.image).save(directory / "open_loop.png")
        _rgb_ink(closed.image).save(directory / "closed_loop.png")
        _comparison_panel(target, fixed, opened, closed).save(directory / "comparison.png")
        if make_animation:
            _save_writing_animation(closed, world, size, directory / "writing.gif")

        stroke_dir = directory / "strokes"
        stroke_dir.mkdir(exist_ok=True)
        for index, (goal, actual) in enumerate(zip(target.stroke_masks, closed.stroke_images), 1):
            _rgb_ink(goal).save(stroke_dir / f"target_{index:02d}.png")
            _rgb_ink(actual).save(stroke_dir / f"closed_{index:02d}.png")
            _error_image(goal, actual).save(stroke_dir / f"error_{index:02d}.png")

    summary = {
        "character": character,
        "profile": profile,
        "image_size": size,
        "stroke_count": len(target.paths),
        "method": "synthetic brush calibration + outline-guided planning + per-stroke visual feedback",
        "data_source": "Make Me a Hanzi graphics.txt",
        "world_parameters_used_by_controller": False,
        "calibration_rmse_px": calibration.rmse_px,
        "fixed": fixed.final_metrics,
        "open_loop": opened.final_metrics,
        "closed_loop": closed.final_metrics,
        "stroke_feedback": [asdict(item) for item in closed.outcomes],
    }
    if save_artifacts:
        (directory / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="轮廓引导的毛笔书写闭环仿真")
    parser.add_argument("--char", default="永", help="单个汉字")
    parser.add_argument("--graphics", type=Path, default=DEFAULT_GRAPHICS)
    parser.add_argument("--profile", choices=tuple(WORLD_PROFILES), default="standard")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=192)
    args = parser.parse_args(argv)
    try:
        result = run_experiment(args.char, args.profile, args.graphics, args.out, args.size)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(f"字符 {result['character']}，笔画 {result['stroke_count']}，环境 {result['profile']}")
    for name in ("fixed", "open_loop", "closed_loop"):
        row = result[name]
        print(f"{name:11s} IoU={row['iou']:.4f}  weighted_error={row['weighted_error']:.4f}")
    print(f"输出：{(args.out / f'{args.char}_{args.profile}').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

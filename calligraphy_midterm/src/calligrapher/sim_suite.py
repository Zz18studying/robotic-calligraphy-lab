"""多汉字、多环境的可复现实验与自动生成中期结果表。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .sim_cli import DEFAULT_GRAPHICS, WORLD_PROFILES, run_experiment


DEFAULT_CHARACTERS = "永木人大水山十"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "outputs" / "closed_loop_sim"


def run_suite(characters: str, profiles: list[str], graphics: Path, output: Path, size: int) -> list[dict]:
    if not characters or len(set(characters)) != len(characters):
        raise ValueError("请提供不重复的汉字列表")
    results = []
    for profile in profiles:
        for character in characters:
            result = run_experiment(
                character, profile, graphics, output, size,
                make_animation=False,
                save_artifacts=False,
            )
            results.append(result)
            print(
                f"{character} {profile:8s}  fixed={result['fixed']['iou']:.3f} "
                f"open={result['open_loop']['iou']:.3f} closed={result['closed_loop']['iou']:.3f}"
            )

    rows = []
    for item in results:
        row = {"character": item["character"], "profile": item["profile"], "strokes": item["stroke_count"]}
        for name in ("fixed", "open_loop", "closed_loop"):
            for metric in ("iou", "missing_pixels", "excess_pixels", "weighted_error"):
                row[f"{name}_{metric}"] = round(item[name][metric], 6)
        row["feedback_improved_weighted_error"] = item["closed_loop"]["weighted_error"] < item["open_loop"]["weighted_error"]
        rows.append(row)

    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "suite_metrics.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    total = len(results)
    avg = {
        name: (
            sum(item[name]["iou"] for item in results) / total,
            sum(item[name]["weighted_error"] for item in results) / total,
        )
        for name in ("fixed", "open_loop", "closed_loop")
    }
    wins = sum(row["feedback_improved_weighted_error"] for row in rows)
    lines = [
        "# 毛笔书写闭环仿真实验结果",
        "",
        f"数据：Make Me a Hanzi 原始笔画轮廓与中心线；{len(characters)} 个汉字，{len(profiles)} 种虚拟环境，共 {total} 次仿真。",
        "",
        "这些是**合成环境中的算法结果**。标定笔画、墨迹和扰动都由本项目虚拟毛笔生成，尚未使用真实机械臂或真实力传感器数据。",
        "",
        "## 汇总",
        "",
        "| 方法 | 平均 IoU（越大越好） | 平均加权误差（越小越好） |",
        "|---|---:|---:|",
    ]
    for name, label in (("fixed", "固定深度+中心线"), ("open_loop", "轮廓引导+标定开环"), ("closed_loop", "轮廓引导+逐笔反馈")):
        iou, error = avg[name]
        lines.append(f"| {label} | {iou:.4f} | {error:.4f} |")
    lines += [
        "",
        f"闭环相对开环在 {wins}/{total} 个案例中降低加权误差。若更换字符或环境出现失败，也应如实报告。",
        "",
        "加权误差 = (漏写像素 + 2 × 越界像素) / 目标墨迹像素；越界权重大是因为墨迹不可擦除。",
        "",
        "## 逐案例结果",
        "",
        "| 汉字 | 环境 | 固定 IoU | 开环 IoU | 闭环 IoU | 开环加权误差 | 闭环加权误差 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['character']} | {row['profile']} | {row['fixed_iou']:.3f} | "
            f"{row['open_loop_iou']:.3f} | {row['closed_loop_iou']:.3f} | "
            f"{row['open_loop_weighted_error']:.3f} | {row['closed_loop_weighted_error']:.3f} |"
        )
    lines += [
        "",
        "## 实验设计与边界",
        "",
        "- 虚拟试笔：5 档下压指令 × 3 档速度，15 个标定笔画；用最小二乘拟合笔触宽度。",
        "- 字形规划：从每笔目标轮廓沿中心线法向测量宽度与偏移，反推下压曲线；转折处降低速度。",
        "- 闭环观察：控制器只使用写前、写后合成图像之差估计新墨迹，不读取虚拟毛笔隐藏参数。",
        "- 扰动：位置偏移、纸面轻微形变和墨量随笔画递减。相同环境和目标下运行三个对照方法。",
        "- 局限：虚拟笔刷尚未由真机数据标定，纸张吸墨、笔毫分叉、含墨量与力的真实关系仍需后期采集。",
        "- 所有字符与环境用于展示和检验原型；本表不是独立测试集，不应据此宣称跨书体或跨硬件泛化。",
        "",
        "单字图片与动画请另运行 `calligraphy-sim` 生成；批量命令只保存结果表，避免重复文件。",
        "",
    ]
    (output / "实验结果.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"汇总已写入 {csv_path.resolve()}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行中期闭环仿真对照实验")
    parser.add_argument("--chars", default=DEFAULT_CHARACTERS, help="不重复的汉字串")
    parser.add_argument("--profiles", nargs="+", default=list(WORLD_PROFILES), choices=tuple(WORLD_PROFILES))
    parser.add_argument("--graphics", type=Path, default=DEFAULT_GRAPHICS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=192)
    args = parser.parse_args(argv)
    try:
        run_suite(args.chars, args.profiles, args.graphics, args.out, args.size)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

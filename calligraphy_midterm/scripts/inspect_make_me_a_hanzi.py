"""从本地 graphics.txt 提取单字记录，并生成逐笔着色 SVG。"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


COLORS = (
    "#c23616", "#1565c0", "#2e7d32", "#8e24aa", "#ef6c00",
    "#00838f", "#6d4c41", "#ad1457", "#5e35b1", "#558b2f",
)


def load_record(path: Path, character: str) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("character") == character:
                return record
    raise KeyError(f"数据文件中没有找到 {character!r}")


def render_svg(record: dict) -> str:
    character = html.escape(record["character"])
    strokes = record.get("strokes", [])
    medians = record.get("medians", [])
    layers: list[str] = []
    legend: list[str] = []
    for index, stroke in enumerate(strokes):
        color = COLORS[index % len(COLORS)]
        layers.append(
            f'<path d="{html.escape(stroke, quote=True)}" fill="{color}" '
            'fill-opacity="0.82" stroke="none"/>'
        )
        if index < len(medians) and len(medians[index]) >= 2:
            points = " ".join(f"{float(x):.1f},{float(y):.1f}" for x, y in medians[index])
            layers.append(
                f'<polyline points="{points}" fill="none" stroke="white" '
                'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        column = index // 18
        row = index % 18
        legend.append(
            f'<text x="{1050 + column * 145}" y="{110 + row * 42}" '
            f'fill="{color}" font-size="26">第 {index + 1} 笔</text>'
        )
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 1024">',
            '<rect width="1400" height="1024" fill="#f7f5ef"/>',
            f'<text x="32" y="55" fill="#222" font-size="32">{character}：逐笔着色与白色中线</text>',
            '<g transform="scale(1,-1) translate(0,-900)">',
            *layers,
            '</g>',
            *legend,
            '</svg>',
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="本地查看 Make Me a Hanzi 的单字记录")
    parser.add_argument("character", help="要查看的一个汉字，例如 永")
    parser.add_argument(
        "--data", type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "graphics.txt",
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path(__file__).resolve().parents[1] / "outputs" / "ppt_demo" / "dataset",
    )
    args = parser.parse_args()
    if len(args.character) != 1:
        parser.error("一次只能查看一个汉字")
    if not args.data.is_file():
        parser.error(f"数据文件不存在：{args.data}")
    try:
        record = load_record(args.data, args.character)
    except KeyError as exc:
        parser.error(str(exc))

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / f"{args.character}_record.json"
    svg_path = args.out / f"{args.character}_strokes.svg"
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    svg_path.write_text(render_svg(record), encoding="utf-8")
    print(f"字符：{args.character}")
    print(f"笔画：{len(record.get('strokes', []))}；中心线：{len(record.get('medians', []))}")
    print(f"原始单字记录：{json_path.resolve()}")
    print(f"逐笔着色图：{svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

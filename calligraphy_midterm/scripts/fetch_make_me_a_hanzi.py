from pathlib import Path
from urllib.request import urlopen


URL = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt"
DESTINATION = Path(__file__).resolve().parents[1] / "data" / "graphics.txt"


def main() -> None:
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在从 {URL} 下载……")
    with urlopen(URL, timeout=60) as response:
        content = response.read()
    DESTINATION.write_bytes(content)
    print(f"已保存到 {DESTINATION}，大小 {len(content) / 1024 / 1024:.1f} MiB")
    print("使用前请阅读上游仓库中的许可证文件。")


if __name__ == "__main__":
    main()


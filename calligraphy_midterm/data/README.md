# 数据目录

已下载 Make Me a Hanzi 项目的两份核心数据到这里：

```text
data/graphics.txt
data/dictionary.txt
```

该文件每行是一条 JSON 记录。`character` 是汉字，`strokes` 是按笔顺排列的 SVG 笔画轮廓，`medians` 是对应的中心线坐标。当前仿真同时使用 `strokes` 和 `medians`，分别作为目标墨迹和初始路径。

本地查看“永”字：

```powershell
cd calligraphy_midterm
python scripts/inspect_make_me_a_hanzi.py 永
```

脚本会生成 `outputs/ppt_demo/dataset/永_record.json` 和 `永_strokes.svg`。用浏览器打开 SVG 即可看每笔轮廓与白色中心线；JSON 可用 VS Code 打开。

数据源及许可证请参考：

https://github.com/skishore/makemeahanzi

`graphics.txt` 包含笔顺、笔画轮廓和中心线，适用 `makemeahanzi_license/ARPHICPL.TXT`；`dictionary.txt` 包含字典信息，适用 `makemeahanzi_license/LGPL`。`makemeahanzi_license/COPYING` 说明了两者的来源与许可证。当前轨迹程序只使用 `graphics.txt`。

真实书法实验数据建议单独建立版本化目录，并记录书写者、字形、毛笔、纸张、墨量、轨迹设备和力传感器标定信息。不要把未脱敏的参与者信息提交到公共仓库。


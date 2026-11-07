# 机器人毛笔书写闭环仿真：中期项目

**从这里开始**：[项目研究进度报告](docs/项目研究进度报告.md)逐项说明已完成、未完成和下一阶段任务；[截至目前的研究报告](docs/截至目前的研究报告.md)详细解释方法、实验结果和局限；[中期汇报准备清单](docs/中期汇报准备清单.md)列出该看什么、运行什么、理解什么。

本仓库的当前实现：输入一个汉字，读取 Make Me a Hanzi 的有序笔画轮廓和中线；在合成毛笔环境中试笔，拟合下压/速度与笔触宽度关系；规划每笔轨迹、下压与相对速度；虚拟写完一笔后根据可见墨迹纠正下一笔。输出逐笔动画、误差图、动作 JSON 和三组对照指标。**目前没有连接真实机械臂，也没有训练大模型或深度网络。**

## 文件夹一览

```text
calligraphy_midterm/
├─ README.md                         项目入口
├─ pyproject.toml                    Python 依赖和命令行入口
├─ data/                             Make Me a Hanzi 原始数据及许可
├─ docs/
│  ├─ 截至目前的研究报告.md            方法、实验、结论、研究边界
│  ├─ 项目研究进度报告.md              进度总览、证据、差距和后续节点
│  ├─ 中期汇报准备清单.md              阅读、运行、报告和 PPT 准备
│  ├─ OnOff_阅读导引.md                相关论文导读
│  └─ OnOff_arXiv_2608.03198.pdf     本地论文
├─ src/calligrapher/
│  ├─ sim_data.py                     汉字笔画与轮廓读取
│  ├─ geometry.py                     路径重采样、平滑、曲率
│  ├─ sim_brush.py                    合成毛笔和纸面
│  ├─ sim_planner.py                  虚拟试笔标定和动作规划
│  ├─ sim_control.py                  逐笔视觉反馈与评价
│  ├─ sim_cli.py                      单字演示入口和文件导出
│  └─ sim_suite.py                    批量对照实验
├─ scripts/                          数据下载和单字原始数据查看
├─ tests/                            当前仿真测试
└─ outputs/
   ├─ ppt_demo/                      代表性单字图、动画、动作数据
   ├─ closed_loop_sim/               开发组 21 组结果表
   └─ heldout_sim/                   补充组 15 组结果表
```

## 运行

需要 Python 3.10+，依赖 NumPy、Pillow；项目已有 `data/graphics.txt`。在本文件夹打开 PowerShell：

```powershell
python -m pip install -e .
calligraphy-sim --char 永 --profile standard --size 256
calligraphy-sim-suite --size 192
calligraphy-sim-suite --chars 中天春秋月 --size 192 --out outputs/heldout_sim
python -m unittest discover -s tests -v
```

若没有安装命令行入口，可执行 `$env:PYTHONPATH='src'`，然后运行 `python -m calligrapher.sim_cli --char 永` 或 `python -m calligrapher.sim_suite`。原始数据可用 `python scripts/inspect_make_me_a_hanzi.py 永` 查看。

`calligraphy-sim` 默认把单字图片和动画写到 `outputs/ppt_demo/永_standard/`。可选环境：`standard`、`drying`（墨量衰减）、`offset`（较大位置偏差）。`calligraphy-sim-suite` 默认只保存 `suite_metrics.csv` 与 `实验结果.md`，避免批量产生重复图片。

## 看什么结果

- [永字对照图](outputs/ppt_demo/永_standard/comparison.png)：目标、固定参数、轮廓标定开环、逐笔闭环及误差。蓝色是漏写，红色是越界。
- [逐笔书写动画](outputs/ppt_demo/永_standard/writing.gif)：动态书写过程。
- [批量对照结果](outputs/closed_loop_sim/实验结果.md)与[补充汉字结果](outputs/heldout_sim/实验结果.md)：平均和逐案例指标。
- `outputs/ppt_demo/永_standard/calibration.csv`：15 次虚拟试笔；`planned_actions.json` 与 `executed_actions.json`：规划和执行的逐点动作；`strokes/`：每笔误差。

`depth_command` 和 `speed_command` 是归一化虚拟指令，分别不是 N、mm 或 mm/s。动作 JSON 是下一阶段机器人接口的候选中间表示，不能直接下发真实机械臂。原申报书与开题 PPT 保留在本项目文件夹的上一级目录，不由代码运行时读取。

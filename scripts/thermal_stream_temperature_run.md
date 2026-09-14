# 热流仪高低温控制与温度过程记录

`thermal_stream_temperature_run.py` 通过已验证的 TCP 入口 `192.168.1.50:3000`，
将高温 R103、常温 R104 或低温 R105 设为指定温度，逐秒记录温度过程，
并在测试完成后停止设备。默认选择低温模式、目标 -25℃。
该脚本会实际写入设备，与只读的 `thermal_stream_tcp_probe.py` 不同。

## 运行

从项目根目录运行，使用 Python 3.11，无第三方依赖：

```powershell
python .\scripts\thermal_stream_temperature_run.py --target -25
```

设置 125℃高温并记录：

```powershell
python .\scripts\thermal_stream_temperature_run.py --mode hot --target 125
```

`--mode hot` 使用 R103/C14，`--mode ambient` 使用 R104/C15，`--mode cold` 使用 R105/C16；模式不根据目标正负自动推断。
125℃编码为 `0x04E2`。产品控温时，目标针对产品传感器反馈，空气温度可能明显高于目标；
两路温度均记录，只有选定的反馈温度用于稳定判定。

默认沿用当前空气或产品温度控温选择。显式指定产品温度控制：

```powershell
python .\scripts\thermal_stream_temperature_run.py --target -25 --control product
```

默认条件为每秒采样一次、所选控温温度进入目标 ±1℃并连续保持 60 秒、最长记录 1200 秒。
这些是本次测试的工程条件，不是厂家承诺的控温精度或制冷时间。可以使用
`--interval`、`--tolerance`、`--hold-seconds`、`--max-seconds` 修改。

2026-09-11 的 125℃测试最初采用 ±0.5℃，用户反馈该要求过高，随后采用 ±1℃复核已记录数据，
并把后续默认值改为 1℃。原始 CSV、运行摘要及脚本快照仍保留当时的 0.5℃条件，复核结论另存。

测试稳定完成、超时、设备自行停止、通信或配置异常，以及正常收到 Ctrl+C 时，
脚本会尝试停止设备并读取 C10 确认。仅在明确需要成功后继续控温时，使用 `--keep-running`；
该选项不影响超时或错误后的停止处理。

只检查当前状态而不写入：

```powershell
python .\scripts\thermal_stream_temperature_run.py --inspect
```

## 控制过程

1. 读取温度、限值、当前模式、控温对象和所选模式的目标，保存预检查快照。
2. 核对目标位于设备配置的温度上下限内，设备不处于除霜或温度整定。
3. 先记录约 5 秒写入前数据。如果设备原来就在运行，这段数据也会标注 running=True。
4. 如果当前正在运行但模式或目标不同，先停止；如果已处于相同目标和模式，则接续现有运行。
5. 将所选 R103、R104 或 R105 写为目标温度并读回确认。-25℃ 编码为 `0xFF06`。
6. 选择定值、不定时及指定控温对象，先关闭其他温度模式，再打开所选模式；逐项读回，并在启动前整体核对配置。
7. 设备尚未运行时发送启动，并读取 C10 确认；已运行则记录接续事件。
8. 持续记录空气和产品温度，按照所选反馈温度判断稳定。超出温差带或采样间隔出现明显缺口时，重新计时。
9. 结束时停止并确认 C10 为 0，保存最终状态。

该脚本仅通过 `0x05` 写 C0、C1、C14、C15、C16、C20、C21、C22，
通过 `0x06` 仅允许写本次模式对应的 R103、R104 或 R105；没有改温度限值、流量、斜率、程式参数，
也没有写入有权限矛盾的 C17 至 C19。采样时读取 C17 至 C19 记录状态。
“温度在带内持续 60 秒”依据离散采样判断，不代表两次采样之间的温度有独立验证。

发生通信错误后不自动重放设温或启动命令。停止确认允许重连后先读 C10，
只有仍在运行时才再次发送停止；如仍无法确认，终端和摘要会报告 STOP NOT CONFIRMED。
强制结束 Python 进程、断电等情况无法保证执行清理逻辑，不应把脚本清理机制视为硬件联锁。

## 记录文件

默认输出至 `results/thermal_stream/temperature_run_<UTC时间>/`，可通过 `--output-dir` 指定不存在的新目录。

| 文件 | 内容 |
| --- | --- |
| `temperature.csv` | 时间、经过秒数、阶段、空气温度、产品温度、选定反馈温度、目标、目标读回、误差、稳定计时、运行与模式状态、原始流量、温度出力、温度斜率、除霜及整定状态 |
| `wire.jsonl` | 每次请求和响应的原始十六进制报文、地址、成功状态或错误 |
| `events.jsonl` | 预检查、设定值读回、配置、启动或接续运行、异常和停止确认事件 |
| `summary.json` | 结束原因、初始状态、末次样本、总时间、采样数和停止确认结果 |
| `temperature_curve.png` | 运行绘图脚本后生成的温度变化曲线 |

每行 CSV 写入后均刷新并执行文件同步。两个温度和各状态通过顺序请求读取，
不是硬件同时采样；时间戳记录本轮读取完成后的时间。流量记录为原始数值，未擅自套用未确认的倍率。
后续记录会逐轮采集 R2、R126、C24、C25，除霜或整定期间不累计到温稳定时间。
这些字段在首次 17:00 至 17:14 的历史 CSV 中不存在，原始记录保持原样。

脚本运行时会输出本次记录目录。创建目录下的 `STOP` 文件可以请求停止，例如：

```powershell
New-Item -ItemType File .\results\thermal_stream\本次记录目录\STOP
```

在下一轮采样前检测停止请求，随后执行停止及确认流程。

## 绘制曲线

绘图脚本需要 matplotlib；记录脚本本身不依赖它。可对完整记录或正在增长的 CSV 作图：

```powershell
python .\scripts\plot_thermal_stream_temperature.py .\results\thermal_stream\本次记录目录
```

本次将绘图依赖安装在项目的 `tmp/thermal_plot_dependencies` 内。采用相同隔离方式时：

```powershell
python -m pip install --target .\tmp\thermal_plot_dependencies matplotlib
python .\scripts\plot_thermal_stream_temperature.py .\results\thermal_stream\本次记录目录 --dependency-dir .\tmp\thermal_plot_dependencies
```

首次安装完成后，后续复图只需执行第二条命令。

图中分别显示空气温度、产品温度、目标线和存在时的停止确认位置。
图上的时间原点是开始记录，不一定是设备启动时刻；若脚本接续运行，无法恢复此前未采集的温度过程。

## 离线验证

```powershell
python -m unittest discover -s scripts -p test_thermal_stream_temperature_run.py -v
```

测试使用模拟设备，覆盖 -25℃/125℃ 编码及写入报文、错误回显、禁止写入的地址、
温度离带或采样缺口后的稳定计时重置、正常完成、通信失败、超时后的停止，以及只读预检查。
另验证停止报文与 C10 确认顺序、停止回包丢失后的状态查询，以及事件日志失败不掩盖已确认停止。
除霜期间即使温度落入目标带也不能判定稳定。另验证高温模式先关低温再启动、
高低温目标写入隔离、启动前模式未保持时不启动，以及运行中模式变化后的停止。
增加常温单点控制回归后，本文件对应 15 项测试通过；与三阶段脚本合计 26 项通过。
三阶段固定计时入口见 [三阶段使用说明](thermal_stream_temperature_sequence.md)，本脚本仍按连续稳定时间判定。
完整协议能力和地址疑点见 [热流仪 TCP 接口说明](../docs/instruments/thermal_stream_tcp.md)。

## 不降温时的只读诊断

```powershell
python .\scripts\thermal_stream_diagnostics.py
```

读取温度、控温对象、模式、目标、限值、流量、温度出力、温度斜率及除霜参数，结果保存为
`results/thermal_stream/diagnostics_<UTC时间>.json` 及同名 `.wire.jsonl`。
诊断客户端只允许 FC01/FC03，既不改参数，也不启动或停止设备。
出力、实际流量和斜率中的未确认单位保留为原始值；斜率为 0 的含义尚无文档依据。
停止状态的出力读数不能代替运行期间的出力记录。
除霜温度和周期存在地址表与报文不一致的问题，诊断脚本仅记录 R14/R15/R16 候选地址的原始值；
2026-09-11 已对照本机面板确认 R125 原始值 150 对应 15 分钟，诊断脚本暂按 0.1 分钟/计数显示；
这是一组读值的现场核对，不代表确认了全部取值范围或 H/M 组合方式。脚本不自行纠正这些设置。

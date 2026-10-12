# 三阶段产品温度自动测试

入口为 `thermal_stream_temperature_sequence.py`。固定采用产品控温，依次运行：

| 阶段 | 目标 | 首次到温范围（含边界） | 到温后固定计时 | 接口 |
| --- | --- | --- | --- | --- |
| 1，低温 | −40℃ | −41～−39℃ | 300 秒 | R105 / C16 |
| 2，常温 | 27℃ | 26～28℃ | 300 秒 | R104 / C15 |
| 3，高温 | 125℃ | 124～126℃ | 300 秒 | R103 / C14 |

**首次进入范围后，计时不会因后续温度越界而暂停或清零。** 各段独立计时，等待首次到温没有超时。
固定时间完成只表示“首次到温后已持续运行规定时间”，不表示这段时间始终保持在 ±1℃内。
原单温度脚本仍采用连续稳定计时；两种计时逻辑独立。

2026-09-11 按用户最新要求只完成代码、离线模拟和绘图验证，未执行三阶段实机测试。
常温 R104/C15 等新增路径尚不能标为实机验证通过。

2026-09-13 经用户授权执行实机测试，−40℃阶段首次到温约 57 秒后开始计时，累计约 149 秒时通信中断；
未执行到 27℃或 125℃。自动重连停机未确认，随后独立恢复连接、发送 STOP 并确认 C10=0。
本次完整流程验证未通过，详见 实机记录（该历史结果已于2026-10-12移除）。

## 运行

从项目根目录使用 Python 3.11 运行。以下命令会实际控制设备：

```powershell
python .\scripts\thermal_stream_temperature_sequence.py
```

默认连接 `192.168.1.50:3000`、Unit ID `0`，每秒采样一次。等价显式参数：

```powershell
python .\scripts\thermal_stream_temperature_sequence.py --host 192.168.1.50 --port 3000 --unit-id 0 --interval 1 --tolerance 1 --hold-seconds 300
```

`--timeout` 默认为 3 秒，仅用于通信；它不限制等待到温的时长。
`--output-dir` 可指定一个尚不存在的新目录；省略时输出至
`results/thermal_stream/sequence_<UTC时间>/`。

控制和采样使用 Python 标准库；自动绘图需要 matplotlib。本机已有
`tmp/thermal_plot_dependencies`，脚本会自动使用该目录。其他环境可安装或显式指定：

```powershell
python -m pip install --target .\tmp\thermal_plot_dependencies matplotlib
python .\scripts\thermal_stream_temperature_sequence.py --plot-dependency-dir .\tmp\thermal_plot_dependencies
```

绘图依赖在建立设备连接前检查。温度上下限及产品反馈在设备预检查中核对。
每段均先停止并确认 C10=0，再写入目标、确认产品控温和模式，最后启动并确认 C10=1。
最终阶段完成后执行停止并确认，关闭连接、保存原始记录，再绘图。
本脚本不控制外部压缩机电源，沿用设备当前流量、斜率、除霜等设置。

## 停止和异常

在运行终端按 Ctrl+C，或创建启动时打印的 `STOP` 文件：

```powershell
New-Item -ItemType File .\results\thermal_stream\本次目录\STOP
```

也可用 `--stop-file` 指定停止请求文件。等待采样期间每隔不超过 0.2 秒检查停止请求；
正在进行的通信请求仍受通信超时限制。

通信失败、配置被修改、设备停止、产品反馈超出配置限值、进入除霜或整定时，终止流程，
不跳过失败阶段，也不自动重新启动。停止确认可以重连，但先读取 C10，避免盲目重发命令。
停止无法确认时输出 `STOP NOT CONFIRMED`，并在摘要中保留 `stop_confirmed=false`。

绘图失败单独记录，不能阻碍停止清理或覆盖停止确认结果；已有 CSV 可以重新绘图。
Windows 短暂文件占用只触发有次数限制的摘要发布重试，不重发设备设温或启动命令。
强制终止进程或断电无法保证 Python 清理代码执行。

## 记录和曲线

| 文件 | 内容 |
| --- | --- |
| `temperature.csv` | UTC 时间、总经过时间、阶段、产品／空气温度、目标及读回、误差、是否在范围内、首次到温时间、已计时和剩余秒数，以及模式、运行、除霜和整定状态 |
| `events.jsonl` | 阶段停机、目标确认、模式确认、启动、首次到温、阶段完成、异常和最终停止确认 |
| `wire.jsonl` | 每次原始 Modbus 请求和响应，及失败原因 |
| `summary.json` | 总体结果、每段首次到温和完成时刻、保持期间温度范围及越界样本数、停止和绘图结果 |
| `code_snapshot/` | 此次控制入口、共享客户端及绘图代码快照，摘要保存 SHA-256 |
| `temperature_curve.png` | 产品温度、空气温度、目标阶梯线、阶段与首次到温标记、固定计时阴影和最终停止位置 |

CSV 逐行刷新并同步；温度及状态是顺序请求读取，不是同时采样。
计时使用单调时钟，UTC 时间用于关联日志。到时后的确认样本可能使实际计时略超过 300 秒。
初始检查和配置阶段也会记录样本，因此总样本数不必等于总运行秒数。

摘要的 `sequence_completed` 表示三段计时均完成，`stop_confirmed` 单独表示停止确认。
退出码 0 要求三段完成、停止已确认、绘图成功且关键记录无错误；其他情况为 1。

需要重新绘图时：

```powershell
python .\scripts\plot_thermal_stream_temperature.py .\results\thermal_stream\本次目录 --dependency-dir .\tmp\thermal_plot_dependencies
```

## 离线验证

```powershell
python -m unittest discover -s scripts -p "test_thermal_stream_temperature*.py" -v
```

当前共 26 项测试通过，包含原单温度回归和三阶段流程测试。
模拟器解码真实客户端生成的二进制请求，返回分段 Modbus 回包；测试显式禁止真实网络连接。
覆盖边界到温、离带后固定计时、各段计时独立、超过原 20 分钟仍等待、停止请求、
通信／模式异常、启停失败、日志和绘图错误、Windows 摘要文件短暂占用，以及停止文件检查耗时跨过采样等待截止点的情况。

完整三段、每段 300 秒的虚拟时间模拟及曲线见
离线验证记录（该历史结果已于2026-10-12移除）。

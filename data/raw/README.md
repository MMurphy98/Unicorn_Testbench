# Local raw data

此目录用于本地暂存原始数据，除本说明外均被 `.gitignore` 忽略。权威数据应保存在团队认可的外部存储，
并通过测试结论和 PR 提供链接。

## T-20260814-01 OPA189 正式噪声数据结构

```text
data/raw/opa189/formal_test/
|-- pm3v_no_shield/run_01 ... run_10
|-- pm3v_with_shield/run_01 ... run_10
|-- pm18v_no_shield/run_01 ... run_10
`-- pm18v_with_shield/run_01 ... run_10
```

每个 `run_XX` 必须包含一份 InstrumentStudio `Waveform Data.csv`。Measurements CSV 和 Panel
Configuration JSON 应与原始波形一起在外部存储归档，但 MATLAB 频谱仅以完整时域波形为输入。

本次采集统一为 CH0、50 kS/s、977,436 点（19.54872 s），四个条件各十次。稳定的团队原始数据链接
尚待补充，Git 仓库不接收这些大文件。

## 2026-08-19 Unicorn COB RevA DUT 与 PXI-5922 噪声数据

原始波形位于本地目录：

```text
data/raw/PXI-5922/
|-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_01/
|   `-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA (1) ... (10)
|       Oscilloscope - Waveform Data.csv
|-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_02/
|   `-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_dc (1) ... (10)
|       Oscilloscope - Waveform Data.csv
`-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_03/
    `-- Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_floatingInput, (2) ... (10)
        Oscilloscope - Waveform Data.csv
```

测试条件：被测对象为 Unicorn COB RevA DUT，测量链路电压增益为 1001 倍，采集设备为 PXI-5922，
`run_01` 输入采用 AC 耦合，`run_02` 输入采用 DC 耦合。每种耦合方式各采集十份 CH0 波形，采样率
均为 50 kS/s，每份元数据声明 954,869 点；正式频谱分析统一使用每份波形的前 900,000 点。

`run_03` 用于标定 PXI-5922 的 floating-input 噪声底：CH0 输入浮空，不连接 DUT 或 1001 倍放大
链路；Panel Configuration 记录为 DC 耦合、1 MOhm 输入、1 倍 probe 和 10 mV/div。共采集十份波形，
采样率和点数处理规则与前两组相同。该结果直接表示 PXI-5922 在此浮空配置下的 ASD，无需除以 1001。

`run_01` 和 `run_02` 原始 CSV 中的电压值是 1001 倍增益后的 DUT 输出测量值，对应分析 ASD 未除以
1001；如需换算为增益前的输入等效 ASD，应再除以 1001。`run_03` 的 floating input 可能拾取环境
电磁干扰，因此它标定的是浮空条件下的综合噪声底，不等同于输入短路或 50 Ohm 终端条件下的本征噪声。

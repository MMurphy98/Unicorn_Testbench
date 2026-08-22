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
## 2026-08-21 DUT COB 1--3 偏置电流扫描

本轮原始波形保存在仓库外的同级目录 `../Chip_Benchmark/data/DUT_noise/`，不复制进 Git。已完成的
COB 1--3 数据结构为：

```text
NO.<1|2|3>_3V3_1001gain_Ibias_<1|2|4>uA/
`-- run_01 ... run_10/
    `-- *Waveform Data.csv
```

每块 COB 在正负 3 V 电源、1001 倍测量增益下，分别设置 `Ib2 = Ib3 = 1/2/4 uA`，每种条件十次，
共 90 份 CH0 波形。每份数据必须为 50 kS/s 且至少包含 900,000 个有限采样点；分析统一只取前
900,000 点。文件夹中必须且只能有一份以 `Waveform Data.csv` 结尾的波形文件。原始大文件需另行
归档；仓库仅提交 `data/processed/dut_noise/3V3_1001gain_COB1-3/` 下可复图的小型处理结果。

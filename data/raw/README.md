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
## 2026-08-21 至 2026-08-22 DUT 噪声数据

本轮原始波形保存在仓库外的同级目录 `../Chip_Benchmark/data/DUT_noise/`，不复制进 Git。正式
COB 1--5 数据结构为：

```text
NO.<1|2|3|4|5>_3V3_1001gain_Ibias_<1|2|4>uA/
`-- run_01 ... run_10/
    `-- *Waveform Data.csv
```

每块 COB 在辅助运放50 Ohm电阻断开、正负 3 V 电源、1001 倍测量增益下，分别设置
`Ib2 = Ib3 = 1/2/4 uA`，每种条件十次，共 150 份 CH0 波形。每份数据必须为 50 kS/s 且至少包含
900,000 个有限采样点；分析统一只取前900,000 点。文件夹中必须且只能有一份以
`Waveform Data.csv` 结尾的波形文件。原始大文件需另行
归档；仓库提交 `data/processed/dut_noise/3V3_1001gain_COB1-5/` 下可复图的小型处理结果，并保留
COB 1--3 阶段快照用于追踪当日分析过程。

两项异常排查数据为：

```text
NO.1_3V3_1001gain_Ibias_1uA/
|-- With50Ohm_01 ... With50Ohm_10/
|   `-- *Waveform Data.csv
NO.1_6V6_1001gain_Ibias_1uA/
`-- run_01 ... run_10/
    `-- *Waveform Data.csv
```

正负 3 V 的目录明确记录辅助运放50 Ohm电阻已接入；操作人员于2026-08-22确认，正负6 V采集时
该电阻已断开。由于这两组同时改变了供电电压和50 Ohm连接状态，叠图只作为双变量配置对照，不能
用于单独归因供电电压或该电阻的影响。详细映射见
`data/processed/dut_noise/evidence_manifest.csv`。

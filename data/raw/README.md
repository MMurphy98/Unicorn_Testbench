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

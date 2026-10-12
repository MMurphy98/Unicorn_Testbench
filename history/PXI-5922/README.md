# PXI-5922 历史噪声

`data/` 保存原始三组采集文件夹及其 ZIP，`results/` 保存已有结果。

| 条件 | 原始目录结尾 |
|---|---|
| DUT，AC 耦合，1001 倍增益 | `run_01` |
| DUT，DC 耦合，1001 倍增益 | `run_02` |
| 浮空输入，无 DUT/放大链路 | `run_03` |

每组十份 CH0 Waveform Data CSV，50 kS/s，每份元数据声明 954869 点；分析统一取前 900000 点，用周期 Hann 窗计算单边 PSD，先平均十份 PSD 再开平方。Measurements CSV、Panel Configuration JSON 与原始波形一起保留。

本目录现只保留原始数据和历史结果，原 MATLAB 分析、绘图入口及其源码快照已移除。CSV、PNG、MAT、FIG 结果继续保留；删除代码前的数值核对记录见 `../verification_20261012.json`。

run_01/run_02 单组 ASD 仍为放大链路输出端 V/√Hz；输入等效对比图除以 1001 并转换为 nV/√Hz。run_03 不除以 1001，其浮空输入可能拾取环境干扰，不能当作短路或 50 Ω 终端的本征噪声底。

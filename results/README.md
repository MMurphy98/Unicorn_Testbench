# Generated results

此目录用于本地生成的图表、日志和中间结果，除本说明外均被 `.gitignore` 忽略。需要进入版本控制的关键
指标和结论应整理到 `docs/test-reports/`；确需提交的小型最终产物应在 PR 中说明原因。

OPA189 正式入口生成：

- `opa189_four_condition_analysis.mat`
- `opa189_four_condition_summary.csv`
- `opa189_four_condition_run_summary.csv`
- `opa189_four_condition_0p1_to_100hz.png`
- `opa189_with_shield_voltage_comparison_0p1_to_100hz.png`

没有本地原始波形时，同一入口会从 `data/processed/opa189/formal_test/` 复写上述产物；这些文件仍然
属于本地生成结果，不进入 Git。仓库中随任务提交的参考 CSV、PNG 和频谱 MAT 位于 `data/processed/`。
## DUT COB 偏置电流扫描

`matlab/scripts/runDutNoiseAnalysis.m` 的默认参数保留 90 份波形的 COB 1--3 阶段快照；本轮显式传入
`1:5` 后从 150 份仓库外原始波形生成：

```text
results/DUT_noise/3V3_1001gain_COB1-5/
|-- dut_noise_full_analysis.mat
|-- dut_noise_full_average_input_asd.csv
|-- dut_noise_run_summary.csv
|-- dut_noise_condition_summary.csv
|-- dut_noise_by_cob.fig
`-- dut_noise_by_bias.fig
```

完整 MAT、全频率 CSV 和可编辑 FIG 仅在本地保存，不进入 Git。相应的压缩频谱、脱敏摘要和 PNG
位于 `data/processed/dut_noise/3V3_1001gain_COB1-5/`，可在没有原始 CSV 时复图。

辅助运放 50 Ohm 接入诊断、正负 6 V 单条件结果以及正负 3 V/正负 6 V 临时对比分别归档到
`data/processed/dut_noise/3V3_1001gain_COB1_With50Ohm/`、
`data/processed/dut_noise/6V6_1001gain_COB1_1uA/` 和
`data/processed/dut_noise/3V3_vs_6V6_1001gain_COB1_1uA/`。这些目录中的小型 MAT、CSV 与 PNG 是
提交证据；完整时域波形仍留在仓库外。

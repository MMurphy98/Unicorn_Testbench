# Generated results

此目录的最终图表和 CSV、JSON、TXT、Markdown 摘要进入 Git；其他层级的 `results/`、
`analysis_results/` 和 `validation_results/` 使用相同原则。关键指标和结论同时整理到
`docs/test-reports/`。原始 `data/`、`spectra/`、逐次 FFT、NPZ/MAT/FIG 和完整分辨率频谱 CSV
由 `.gitignore` 排除，保留在本地。

OPA189 正式入口生成：

- `opa189_four_condition_analysis.mat`
- `opa189_four_condition_summary.csv`
- `opa189_four_condition_run_summary.csv`
- `opa189_four_condition_0p1_to_100hz.png`
- `opa189_with_shield_voltage_comparison_0p1_to_100hz.png`

没有本地原始波形时，同一入口会从历史已提交的 `data/processed/opa189/formal_test/` 复写上述产物；
其中 CSV 和 PNG 作为最终结果提交，MAT 留在本地。历史参考文件继续用于离线回归测试，新的
`data/` 内容不再自动进入 Git。

## PXI-5922 Unicorn COB RevA 噪声结果

- `matlab/scripts/runPxi5922NoiseAnalysis.m`
- `runPxi5922DcNoiseAnalysis.m`
- `runPxi5922FloatingInputNoiseAnalysis.m`

分别生成：

```text
results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_01/  # DUT, 1001x, AC coupling
results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_02/  # DUT, 1001x, DC coupling
results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_03/  # PXI-5922 floating input
```

每个目录包含 `average_noise_asd.csv`、`average_noise_asd.mat`、`average_noise_asd.png` 和
`average_noise_asd.fig`。其中 PNG 入库；完整频率网格 CSV、MAT 和 FIG 留在本地。

三组数据均为 50 kS/s、每种条件十次采集；每份波形统一取前 900,000 点，以 900,000 点周期 Hann
窗计算一份单边 PSD。每种条件先在功率域平均十份 PSD，再开平方得到最终 ASD，不能直接对十份 ASD
做算术平均。中间频谱不绘图，只保留每种条件的最终双对数 ASD 图。

- `run_01` 与 `run_02` 的单组 ASD 保留 1001 倍增益后的输出端单位 V/sqrt(Hz)；
- `run_03` 不连接 DUT 或放大链路，结果直接表示 floating-input 条件下的 PXI-5922 测量量级。

`run_03` 的 1 MOhm 浮空输入可能拾取环境电磁干扰，因此只能作为 floating-input 条件下的综合噪声
诊断，不能等同于输入短路或 50 Ohm 终端条件下的 PXI-5922 本征噪声底。

`matlab/scripts/plotPxi5922AcDcComparison.m` 只加载 `run_01` 和 `run_02` 已保存的 MAT 文件，不重新
处理原始波形。它将两组输出端 ASD 除以 1001，并乘以 `1e9` 换算成输入等效噪声 nV/sqrt(Hz)，输出：

```text
results/PXI-5922/2026-08-19_Unicorn_COB_RevA_ac_dc_comparison/
|-- ac_dc_average_noise_asd_comparison.png
`-- ac_dc_average_noise_asd_comparison.fig
```

`matlab/scripts/plotPxi5922Run02NoiseReference.m` 从 `run_02` 的 MAT 结果生成 1 Hz 至 25 kHz 输入等效
噪声图，并标出 5.1 nV/sqrt(Hz) 参考线，不重新读取原始 CSV。输出为：

```text
results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_02/
|-- run02_input_referred_noise_1Hz_25kHz.png
`-- run02_input_referred_noise_1Hz_25kHz.fig
```

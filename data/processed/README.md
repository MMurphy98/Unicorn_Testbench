# Processed data

此目录保存可以进入 Git 的小型处理结果。它们用于在没有大型原始波形时复现正式图表，并不替代
`data/raw/` 中的完整测量数据。

## T-20260814-01 OPA189

`opa189/formal_test/opa189_four_condition_analysis.mat` 来自四种条件各十次原始波形的正式 Welch
分析，保存每次及每条件的 PSD/ASD、汇总表和分析元数据，不包含时域电压采样。MAT 文件 SHA-256：

```text
906E903236BB4B1DEF94B291522AE9A45C33120B9B843D75D5735C0BFA9C1910
```

同目录的两份 CSV 是条件和逐次汇总，两张 PNG 是本次提交时的参考输出。运行
`runOpa189NoiseAnalysis()` 时，如果本地没有 `data/raw/opa189/formal_test/`，入口会读取该 MAT 并
重新生成 `results/opa189/` 下的五项产物。此路径只验证处理后数据到图表的可复现性；若要更改
去趋势、Welch 段长、窗函数或重叠比例，必须下载原始波形并重新运行完整分析。

## 2026-08-21 DUT COB 1--3 偏置电流扫描

`dut_noise/3V3_1001gain_COB1-3/` 保存正负 3 V、1001 倍增益、三块 COB 和三档
`Ib2 = Ib3 = 1/2/4 uA` 的小型结果。完整分析对每份 50 kS/s 波形取前 900,000 点并去均值，使用
900,000 点周期 Hann 窗计算单边 PSD；每条件十份 PSD 在功率域平均，开方后除以 1001，得到输入
等效 ASD。用于绘图的对数频率压缩仍在功率域取平均，不直接平均 ASD。

- `dut_noise_plot_data.mat`：压缩后的 PSD/ASD、条件、配置和脱敏摘要，可独立复图；
- `dut_noise_plot_spectra.csv`：九个条件的输入等效 ASD，单位 nV/sqrt(Hz)；
- `dut_noise_run_summary.csv`、`dut_noise_condition_summary.csv`：逐次与逐条件指标；
- `dut_noise_by_cob.png`、`dut_noise_by_bias.png`：按 COB 和按偏置电流组织的双对数图。

MAT 文件 SHA-256：

```text
73F323A684194D8D312461FD6449303E20E6D4B8F4DC773C700053277B941140
```

不需要原始波形即可在仓库根目录重新生成两张 PNG：

```matlab
addpath("matlab/src");
dut.replayProcessedCampaign( ...
    "data/processed/dut_noise/3V3_1001gain_COB1-3");
```

该 MAT 只保留约 3,000 个绘图频点，不能用于更换窗函数、点数或重新计算完整频谱；这些操作必须从
仓库外的原始 CSV 重新运行。逐次摘要中的原始路径已统一替换为说明文字，不包含本机绝对路径。

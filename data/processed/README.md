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

## 2026-08-21 DUT COB 1--3 阶段快照

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

## 2026-08-22 DUT COB 1--5 正式扫描

`dut_noise/3V3_1001gain_COB1-5/` 扩展为五块COB、三档偏置、每条件十次，共150份波形。处理方法与
上述阶段快照相同。运行下列命令可从已提交的小型MAT重新生成按COB和按偏置组织的PNG：

```matlab
addpath("matlab/src");
dut.replayProcessedCampaign( ...
    "data/processed/dut_noise/3V3_1001gain_COB1-5");
```

`dut_noise_plot_data.mat` SHA-256：

```text
67100B34B144FF0A9E2C311ED664727D23426126BABB0F3A61597AC64B028CDD
```

## 50 Ohm重复测量

`dut_noise/3V3_1001gain_COB1_With50Ohm/` 保存COB 1、正负3 V、1001倍、1 uA的十次功率域平均结果。
`initial_measurement_reference.png` 是初测时保留的参考截图；原始全频图作为测量证据保留，另可从
小型MAT生成带 `_replayed` 后缀的压缩频谱图和左右对比图：

```matlab
dut.replayRepeatedCondition( ...
    "data/processed/dut_noise/3V3_1001gain_COB1_With50Ohm");
```

`with50ohm_plot_data.mat` SHA-256：

```text
EED4C57E056560EC47367F833D2A130DAFD7E79D73189138BCDBA75A1FDF3311
```

## 正负6 V单条件测量

`dut_noise/6V6_1001gain_COB1_1uA/` 保存 COB 1、正负6 V、1001倍、1 uA的十次测量结果，处理方法与
正负3 V正式扫描一致。它是下述临时供电对比的正负6 V数据源。`dut_noise_plot_data.mat` SHA-256：

```text
E5625FC45C2473D07430D17EA296A745F2E6B0CFDE247B7922EDB60FB7FBC147
```

## 正负3 V / 正负6 V临时对比

`dut_noise/3V3_vs_6V6_1001gain_COB1_1uA/` 保存两种供电的压缩频谱、汇总和对比PNG。正负3 V来源为
明确接入50 Ohm电阻的十次测量；正负6 V的电阻状态仅由连续实验操作推定，未编码在原始目录名中，
所以该结果标记为 `provisional`，不能替代硬件记录确认。离线复图命令为：

```matlab
dut.replaySupplyComparison( ...
    "data/processed/dut_noise/3V3_vs_6V6_1001gain_COB1_1uA");
```

`supply_voltage_plot_data.mat` SHA-256：

```text
D5BB9192A850AA2B6356490CFBDCD1AA87EE5CA07F94002E751D7299C8A31AA9
```

原始目录映射和证据等级统一记录在 `dut_noise/evidence_manifest.csv`。小型MAT不能用于改变窗函数或
重新计算PSD；完整算法复算仍需仓库外原始CSV。

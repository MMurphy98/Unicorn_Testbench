# MATLAB 代码组织

- `src/`：可复用函数、算法和包。函数应尽量避免依赖调用者工作区。
- `scripts/`：面向具体任务的分析入口，负责加载配置、调用 `src/` 和保存摘要。
- `tests/`：基于 `matlab.unittest` 的测试及统一入口 `run_all_tests.m`。
- `config/`：可提交的非敏感配置。密钥、机器专用路径和大文件不得提交。

从仓库根目录运行全部测试：

```powershell
matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"
```

OPA189 正式分析入口：

```matlab
addpath("matlab/scripts");
runOpa189NoiseAnalysis();
```

若仓库内没有大型原始波形，上述同一入口会自动使用已提交的处理后频谱数据复图；若原始数据目录存在，
则执行完整 Welch 分析。命令行会明确打印实际选择的路径。

- 使用已提交频谱数据离线复图：需要 MATLAB R2026a。
- 从原始时域波形重新计算 Welch PSD 或运行完整测试：还需要 Signal Processing Toolbox。

核心算法及其 `private/` 辅助函数位于 `src/+opa189/`。

## DUT COB 偏置电流扫描

2026-08-21 的 COB 1--3、正负 3 V、1001 倍增益数据可从仓库根目录运行：

```matlab
addpath("matlab/scripts");
[result, outputPaths] = runDutNoiseAnalysis();
```

入口默认读取同级 `Chip_Benchmark/data/DUT_noise/` 中九种条件、每种十次的 InstrumentStudio CSV。
它验证每份波形为 50 kS/s 且至少有 900,000 点，对前 900,000 点去均值，以整段周期 Hann 窗计算
单边 PSD；每条件十份 PSD 先平均，随后开方并除以 1001，得到输入等效 ASD。完整频率数据与 FIG
写入已忽略的 `results/DUT_noise/3V3_1001gain_COB1-3/`；小型频谱、摘要和 PNG 写入
`data/processed/dut_noise/3V3_1001gain_COB1-3/`。

没有原始 CSV 时，可只凭已提交的小型 MAT 复图：

```matlab
addpath("matlab/src");
dut.replayProcessedCampaign( ...
    "data/processed/dut_noise/3V3_1001gain_COB1-3");
```

该复图入口不执行 FFT，也不能用于修改频谱处理参数。核心代码位于 `src/+dut/`。

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

## DUT COB 偏置电流扫描与异常证据复图

默认入口保留COB 1--3阶段快照。正式COB 1--5、正负3 V、1001倍增益数据可从仓库根目录显式运行：

```matlab
addpath("matlab/scripts");
[result, outputPaths] = runDutNoiseAnalysis( ...
    "../Chip_Benchmark/data/DUT_noise", ...
    "results/DUT_noise/3V3_1001gain_COB1-5", ...
    "data/processed/dut_noise/3V3_1001gain_COB1-5", ...
    1:5);
```

入口验证每份InstrumentStudio波形为50 kS/s且至少有900,000点，对前900,000点去均值，以整段
periodic Hann窗计算单边PSD；每条件十份PSD先平均，随后除以 `1001^2` 并开方，得到输入等效ASD。
完整频率数据与FIG写入已忽略的 `results/DUT_noise/`；小型频谱、摘要和PNG写入 `data/processed/`。

没有原始CSV时，可只凭已提交的小型MAT复图：

```matlab
addpath("matlab/src");
dut.replayProcessedCampaign( ...
    "data/processed/dut_noise/3V3_1001gain_COB1-5");
dut.replayRepeatedCondition( ...
    "data/processed/dut_noise/3V3_1001gain_COB1_With50Ohm");
dut.replaySupplyComparison( ...
    "data/processed/dut_noise/3V3_vs_6V6_1001gain_COB1_1uA");
```

三种复图入口均不执行FFT，也不能用于修改频谱处理参数。操作人员已确认正负6 V测量时辅助运放
50 Ohm电阻断开，而对照中的正负3 V数据为电阻接入状态；因此该图标为双变量配置对照，不能隔离
供电电压的影响。核心代码位于 `src/+dut/`。

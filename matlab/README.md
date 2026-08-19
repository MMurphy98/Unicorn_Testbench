# MATLAB 代码组织

- `src/`：可复用函数、算法和包。函数应尽量避免依赖调用者工作区。
- `scripts/`：面向具体任务的分析入口，负责加载配置、调用 `src/` 和保存摘要。
- `tests/`：基于 `matlab.unittest` 的测试及统一入口 `run_all_tests.m`。
- `config/`：可提交的非敏感配置。密钥、机器专用路径和大文件不得提交。

从仓库根目录运行全部测试：

```powershell
matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"
```

## 通用噪声频谱

`src/noiseSpectrum.m` 使用 50% 重叠的周期 Hann 窗和 Welch 方法计算单边功率谱密度（PSD）。
`N` 同时表示 Welch 分段长度和 FFT 点数，且不能超过输入波形长度：

```matlab
addpath("matlab/src");

fs = 100e3;                 % 采样率，Hz
N = 4096;                   % Welch 分段/FFT 点数
x = readmatrix("noise.csv");

[pxx, f] = noiseSpectrum(x, fs, N, true);  % true：绘图
asd = sqrt(pxx);                              % 幅度谱密度
```

`pxx` 的单位是“输入波形单位平方/Hz”；若 `x` 的单位为 V，则 `pxx` 为 V^2/Hz，`asd` 为
V/sqrt(Hz)。不需要绘图时省略第 4 个参数，或传入 `false`。

## PXI-5922 DUT 与 floating-input 十次采集平均 ASD

2026-08-19 Unicorn COB RevA 数据的测试条件为：DUT 测量、1001 倍电压增益和 PXI-5922 采集。
AC 耦合 `run_01` 的任务级入口为：

```matlab
addpath("matlab/scripts");
[averageAsdVrtHz, frequencyHz, outputPaths] = ...
    runPxi5922NoiseAnalysis();
```

DC 耦合 `run_02` 使用完全相同的频谱参数和输出格式，入口为：

```matlab
addpath("matlab/scripts");
[dcAverageAsdVrtHz, dcFrequencyHz, dcOutputPaths] = ...
    runPxi5922DcNoiseAnalysis();
```

入口从 `data/raw/PXI-5922/Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_01/`
读取编号 `(1)` 至 `(10)` 的 Waveform Data CSV。每份取前 900,000 点，不绘制逐次频谱；十份 PSD
平均后只绘制最终的双对数 ASD，并在 `results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_01/`
保存 PNG、MATLAB FIG、CSV 和 MAT 文件。若任何一份数据少于 900,000 点，入口会停止并指出需重新
导出的文件。`average_noise_asd.fig` 可用 MATLAB 重新打开并继续编辑坐标轴、标题和曲线属性。
DC 结果使用相同的四个文件名，保存到
`results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_02/`，不会覆盖 AC 结果。

PXI-5922 floating-input 噪声底标定使用 `run_03`。这组数据不连接 DUT 或 1001 倍放大链路，
Panel Configuration 为 DC 耦合、1 MOhm 输入、1 倍 probe 和 10 mV/div：

```matlab
addpath("matlab/scripts");
[floatingAsdVrtHz, floatingFrequencyHz, floatingOutputPaths] = ...
    runPxi5922FloatingInputNoiseAnalysis();
```

输出格式与前两组一致，写入
`results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_03/`。该 ASD 直接表示 floating-input 条件下的
PXI-5922 综合噪声底，不除以 1001；浮空输入可能包含环境拾取，不能直接等同于短路或 50 Ohm 终端
条件下的仪器本征噪声。

### AC/DC 最终 ASD 离线对比图

下列入口只加载 `run_01` 和 `run_02` 已保存的 `average_noise_asd.mat`，不会读取原始波形或重新计算
PSD：

```matlab
addpath("matlab/scripts");
[figureHandle, comparisonPaths, comparison] = ...
    plotPxi5922AcDcComparison();
```

入口将 MAT 中保存的输出端 ASD 除以 1001，再从 V/sqrt(Hz) 换算为 nV/sqrt(Hz)。输出是带 legend
的 AC/DC 双对数输入等效噪声对比图，纵轴为 `Input-referred noise (nV/sqrt(Hz))`；PNG 和 MATLAB
FIG 保存在 `results/PXI-5922/2026-08-19_Unicorn_COB_RevA_ac_dc_comparison/`。换算关系为：

```matlab
inputReferredNoiseNvRtHz = averageAsdVrtHz/1001*1e9;
```

## 运行 OPA189 噪声分析并绘图

从仓库根目录在 Git Bash 中批处理运行：

```bash
matlab -batch "addpath('matlab/scripts'); [outputPaths, comparison] = runOpa189NoiseAnalysis(); disp(outputPaths)"
```

也可以先将 MATLAB 的 Current Folder 切换到仓库根目录，再在 MATLAB 命令窗口运行：

```matlab
addpath("matlab/scripts");
[outputPaths, comparison] = runOpa189NoiseAnalysis();

fprintf("四条件图：%s\n", outputPaths.fourConditionFigurePath);
fprintf("有屏蔽罩对比图：%s\n", outputPaths.shieldedFigurePath);

winopen(outputPaths.fourConditionFigurePath);
winopen(outputPaths.shieldedFigurePath);
```

入口默认在 `data/raw/opa189/formal_test/` 查找四条件原始波形。若该目录不存在，则自动读取
`data/processed/opa189/formal_test/opa189_four_condition_analysis.mat` 离线复图；若原始数据存在，
则重新执行完整 Welch 分析。命令行会明确打印实际选择的路径。

两张 PNG、两份 CSV 和分析 MAT 文件默认写入 `results/opa189/`。该目录中的生成结果已被 Git 忽略；
随任务提交的参考结果仍位于 `data/processed/opa189/formal_test/`。

- 使用已提交频谱数据离线复图：已在 MATLAB R2023b 验证；MATLAB R2025a 及以上会显式应用浅色 graphics theme。
- 从原始时域波形重新计算 Welch PSD 或运行完整测试：还需要 Signal Processing Toolbox。

核心算法及其 `private/` 辅助函数位于 `src/+opa189/`。

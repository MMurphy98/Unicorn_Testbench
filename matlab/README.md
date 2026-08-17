# MATLAB 代码组织

- `src/`：可复用函数、算法和包。函数应尽量避免依赖调用者工作区。
- `scripts/`：面向具体任务的分析入口，负责加载配置、调用 `src/` 和保存摘要。
- `tests/`：基于 `matlab.unittest` 的测试及统一入口 `run_all_tests.m`。
- `config/`：可提交的非敏感配置。密钥、机器专用路径和大文件不得提交。

从仓库根目录运行全部测试：

```powershell
matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"
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

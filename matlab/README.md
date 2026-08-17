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

核心算法及其 `private/` 辅助函数位于 `src/+opa189/`。

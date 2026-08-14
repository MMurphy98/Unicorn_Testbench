# MATLAB 代码组织

- `src/`：可复用函数、算法和包。函数应尽量避免依赖调用者工作区。
- `scripts/`：面向具体任务的分析入口，负责加载配置、调用 `src/` 和保存摘要。
- `tests/`：基于 `matlab.unittest` 的测试及统一入口 `run_all_tests.m`。
- `config/`：可提交的非敏感配置。密钥、机器专用路径和大文件不得提交。

从仓库根目录运行全部测试：

```powershell
matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"
```

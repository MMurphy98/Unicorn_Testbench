# Unicorn Testbench

面向 MATLAB 分析与测试的双人协作仓库。任务由负责人在
[`docs/TODO.md`](docs/TODO.md) 发布；执行人通过任务分支每日提交代码，并将测试结论按日期记录在
[`docs/test-reports/`](docs/test-reports/)；所有变更通过 Pull Request 进入 `main`。

## 目录

```text
Unicorn_Testbench/
|-- .github/                  # CODEOWNERS、PR 模板和 PR 自动检查
|-- .githooks/                # 本地 main 分支提交保护
|-- data/
|   |-- raw/                  # 原始数据不入库，仅保留说明和外部链接
|   `-- README.md
|-- docs/
|   |-- TODO.md               # 负责人发布和验收任务
|   |-- WORKFLOW.md           # 分支、提交、PR、审核规则
|   `-- test-reports/         # 按 YYYY/MM/YYYY-MM-DD-任务编号.md 记录结论
|-- matlab/
|   |-- src/                  # 可复用 MATLAB 函数和算法
|   |-- scripts/              # 分析入口与可重复执行脚本
|   |-- tests/                # matlab.unittest 自动化测试
|   `-- config/               # 非敏感配置
`-- results/                  # 本地生成结果不入库
```

## 开始工作

1. 从 `main` 创建任务分支：`git switch -c task/T-YYYYMMDD-NN-short-name`。
2. 在 `docs/TODO.md` 找到任务验收标准。
3. 每日推送代码，并更新对应日期的测试结论文件。
4. 运行 `matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"`。
5. 使用仓库 PR 模板发起 PR，指定 `@MMurphy98` 审核。

完整规则见 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)。

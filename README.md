# Unicorn Testbench

面向 MATLAB 分析与测试的双人协作仓库。任务由负责人直接在
[`测试安排.md`](测试安排.md) 发布；执行人通过任务分支每日提交代码，并将测试结论按日期记录在
[`docs/test-reports/`](docs/test-reports/)；所有变更通过 Pull Request 进入 `main`。

任务发布是唯一例外：负责人可以直接在 `main` 提交测试安排文件，其他文件的交付必须走 PR。

## 目录

```text
Unicorn_Testbench/
|-- 测试安排.md               # 唯一任务源，负责人可直接发布任务
|-- .github/                  # CODEOWNERS、PR 模板和 PR 自动检查
|-- .githooks/                # 本地 main 分支提交保护
|-- data/
|   |-- raw/                  # 原始数据不入库，仅保留说明和外部链接
|   |-- processed/            # 可提交的小型频谱结果，用于离线复图
|   `-- README.md
|-- docs/
|   |-- WORKFLOW.md           # 分支、提交、PR、审核规则
|   |-- reference/            # 原始需求与总体测试方案
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
2. 在根目录 `测试安排.md` 找到任务内容和验收标准。
3. 每日推送代码，并更新对应日期的测试结论文件。
4. 运行 `matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"`。
5. 使用仓库 PR 模板发起 PR，指定 `@MMurphy98` 审核。

完整规则见 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)。

## OPA189 正式噪声分析

任务 `T-20260814-01` 的 MATLAB 实现在 `matlab/src/+opa189/`，入口为
`matlab/scripts/runOpa189NoiseAnalysis.m`。从仓库根目录在 MATLAB 中运行：

```matlab
addpath("matlab/scripts");
runOpa189NoiseAnalysis();
```

入口会自动选择可用路径：若存在 `data/raw/opa189/formal_test/`，则从四条件、每条件十次的
完整时域 CSV 重新计算 Welch PSD；若原始数据未下载，则读取仓库内
`data/processed/opa189/formal_test/opa189_four_condition_analysis.mat`，重新生成两份 CSV 和
两张正式图。离线复图不会重新计算 Welch，完整算法复算仍需要 `data/raw/README.md` 规定的原始波形。

算法从 InstrumentStudio 原始时域 CSV 重新计算 Welch PSD，不使用仪器 FFT：线性去趋势、
10 s periodic Hann 窗、50% 重叠、单边 PSD；每条件十次先平均 PSD，再开方得到 ASD。

## DUT COB 噪声扫描

COB 1--5 在正负3 V、1001倍增益和 `Ib2 = Ib3 = 1/2/4 uA` 下的入口为
`matlab/scripts/runDutNoiseAnalysis.m`。150份原始波形保存在仓库外；完整输出留在忽略的 `results/`，
可提交的小型MAT、CSV和PNG位于 `data/processed/dut_noise/3V3_1001gain_COB1-5/`。

同目录还保存50 Ohm接入复现实验、正负6 V实验和临时供电对比。`dut.replayProcessedCampaign`、
`dut.replayRepeatedCondition` 与 `dut.replaySupplyComparison` 可在没有原始CSV时重画相应图片。测试结论、
来源限制和待师兄接手的问题见
[`2026-08-22 测试记录`](docs/test-reports/2026/08/2026-08-22-T-20260817-01.md)。

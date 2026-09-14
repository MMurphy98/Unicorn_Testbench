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
|   |-- instruments/          # 仪器接口能力、接入参数与验证范围
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

克隆后先启用 Git LFS 和仓库 hooks：

```powershell
git lfs install
git config core.hooksPath .githooks
```

1. 从 `main` 创建任务分支：`git switch -c task/T-YYYYMMDD-NN-short-name`。
2. 在根目录 `测试安排.md` 找到任务内容和验收标准。
3. 每日推送代码，并更新对应日期的测试结论文件。
4. 运行 `matlab -batch "addpath('matlab/tests'); results = run_all_tests; assertSuccess(results)"`。
5. 使用仓库 PR 模板发起 PR，指定 `@MMurphy98` 审核。

完整规则见 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)。

## 测试数据与二进制结果

- 所有层级的 `results/`、`analysis_results/` 和 `validation_results/` 均允许提交结果图表与
  CSV、JSON、TXT、Markdown 摘要。
- `data/`、`spectra/`、`per_run_fft/`，原始 `*.tdms` / `*.tdms_index`，以及 NPZ、MAT、FIG
  和完整分辨率频谱 CSV 留在本地；原有已入库参考数据继续作为回归测试基准。
- `.gitattributes` 为两个历史选定的 MATLAB 产物保留 Git LFS 配置，但本次不新增这些二进制文件；
  后续确需归档时应单独审查。

## 热流仪 TCP 接口

[热流仪 TCP 接口能力与接入说明](docs/instruments/thermal_stream_tcp.md) 记录实际连接参数、
控制能力、线圈和寄存器地址、报文示例、验证结果及厂家文档疑点。
当前实机通信入口为 `192.168.1.50:3000`，Unit ID 为 `0`；空气温度、产品温度和运行状态读取已验证。
运行入口见 [只读探测脚本说明](scripts/thermal_stream_tcp_probe.md)。

[高低温控制与记录脚本](scripts/thermal_stream_temperature_run.py) 可设置高温或低温目标、逐秒记录空气和产品温度，
并在稳定完成、超时或异常时停止并确认运行状态。默认低温目标为 -25℃；125℃测试使用 `--mode hot --target 125`。
参数、记录格式、绘图方法和停止方法见 [使用说明](scripts/thermal_stream_temperature_run.md)。

[三阶段产品温度脚本](scripts/thermal_stream_temperature_sequence.py) 依次执行 −40℃、27℃、125℃，
每段首次进入 ±1℃后固定计时 5 分钟，最终停止并自动绘图；等待到温不设超时。
运行方式及验证情况见 [三阶段使用说明](scripts/thermal_stream_temperature_sequence.md)。
2026-09-13 实机尝试在低温阶段因通信中断结束，随后重连并确认停机；
曲线及原始记录见 [本次实机报告](results/thermal_stream/sequence_20260913_run01/README.md)。

[三温度 offset drift 联动](scripts/thermal_stream_offset_drift.md) 将热流仪与独立 DMM7510 进程连接：
每个温度首次进入 ±1℃后计时 5 分钟，再采集 1000 点（增益 1001），确认 DMM 完成标志后才切换温度。
点数可统一或按温度分别配置；本轮只做代码和离线验证。

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

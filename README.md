# Unicorn Testbench

当前主线是 **Unicorn CSA RevB（with PMU）**。从 [RevB 测试结果](Unicorn_CSA_RevB-COB/README.md)
查看最新芯片的噪声、温漂、失败记录及复现入口。

当前保留测试均由项目负责人本人完成，归属依据为本人于 2026-10-12 的确认。
早期委托安排不作为当前保留成果的执行人依据；用户已另行备份，仓库中的旧快照已删除。

## 查看测试

| 入口 | 内容 |
| --- | --- |
| [测试安排](测试安排.md) | 当前待办、优先级和状态 |
| [测试日志](测试日志.md) | 按日期记录实际测试及失败尝试 |
| [RevB 全部任务](Unicorn_CSA_RevB-COB/tasks/README.md) | 13 组噪声、9 月 18 日三颗芯片温漂记录 |
| [详细报告](docs/test-reports/README.md) | 测试条件、结论、限制与复现命令 |
| [历史测试](history/README.md) | RevA、PXI-5922 和 OPA189 |

RevB 噪声共 1300 次采集。温漂 Chip 1、3 各有三温度 × 1000 点，但温度振荡明显；
Chip 2 首点超量程中止，保留失败证据，没有有效 offset 或温漂斜率。
数据完整、处理成功与器件规格通过分别记录。

## 文件结构

```text
Unicorn_CSA_RevB-COB/
  tasks/<task-id>/       data、spectra、results、logs、provenance
  field/                Windows 现场采集与现场依赖
  postprocess/          RevB noise / offset drift 后处理 Notebook
  results/              全任务索引、跨任务噪声对照
  comparisons/          三温度对比及统一 CSV
history/
  RevA/                 历史 RevA 测量与结果
  PXI-5922/             data、results
  OPA189/               data/raw、data/processed、results
scripts/                原仪器控制入口、DMM worker、辅助工具
fpga/                   工程源码、历史固件和编译报告
docs/                   流程、报告、仪器说明和整理记录
```

MATLAB 代码、Live Script 和专属配置已按要求删除，历史 MAT/FIG 测试数据与结果保留。
现场 FPGA 固件见 [固件说明](fpga/README.md)，
使用前核对对应时钟和接线。

## 使用入口

- [Windows 现场采集](Unicorn_CSA_RevB-COB/field/README.md)：安装现场依赖及 NI-SCOPE / NI-VISA 驱动。
- [RevB 后处理 Notebook](Unicorn_CSA_RevB-COB/postprocess/postprocess.ipynb)：输入 task-id，处理 noise / offset drift，可选重算 spectra。
- [热流仪控制与 DMM 联动](scripts/thermal_stream_offset_drift.md)：现场执行、温度阶段及 DMM worker 的使用说明。
- [热流仪 TCP 接口](docs/instruments/thermal_stream_tcp.md)：协议、地址及实机验证记录。

在仓库根目录安装并打开 RevB 后处理 Notebook：

```bash
python -m venv .venv-postprocess
.venv-postprocess/bin/python -m pip install -r Unicorn_CSA_RevB-COB/postprocess/requirements-notebook.txt
.venv-postprocess/bin/python -m ipykernel install --sys-prefix
.venv-postprocess/bin/python -m jupyterlab Unicorn_CSA_RevB-COB/postprocess/postprocess.ipynb
```

Windows 使用 `.venv-postprocess\Scripts\python.exe`。修改 Notebook 的 `TASK_ID` 和 `REGENERATE_SPECTRA`，运行全部单元；
安装与参数说明见 [后处理说明](Unicorn_CSA_RevB-COB/postprocess/README.md)。也可查看
[CSV 总览](Unicorn_CSA_RevB-COB/results/task_overview.csv) 或
[JSON 总览](Unicorn_CSA_RevB-COB/results/task_overview.json)。

## 代码与完整数据

Git 保存代码、文档、图表、摘要、采集证据和已有 OPA189 参考基准。
原始 TDMS、逐次 NPZ、历史原始波形及大部分 MAT/FIG 留在本地；仅克隆 main 不能恢复全部原始数据。
跨电脑复现需要另行复制完整任务或历史数据目录，具体见 [数据交付与 main 准备说明](docs/MAIN_BASELINE.md)。
OPA189 当前缺少原始波形，保留处理后基准、CSV 和图表；仓库不再提供其 MATLAB 重放入口。

仓库采用 [个人维护流程](docs/WORKFLOW.md)，PR 可用于审阅。初始化 Git LFS hooks：

```bash
git lfs install
git config core.hooksPath .githooks
```

[结构与验证记录](docs/RESULTS_LAYOUT.md)

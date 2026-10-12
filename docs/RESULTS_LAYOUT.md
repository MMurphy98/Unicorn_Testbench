# 2026-10-12 测试数据、目录与主线整理

本次以最新RevB芯片为主要结果入口，按用户确认保留13组正式噪声、9月18日Chip1/3及失败Chip2的offset drift，
同时保留RevA/PXI历史噪声与OPA189。demo仅留本地并忽略Git。其他早期offset、独立热流仪结果已删除。
第二阶段将历史测试集中归入history，统一实际测试归属、安排和日志，并调整为个人维护流程。
当前保留测试均由项目负责人本人完成，依据为本人于2026-10-12确认。

后续按本人要求删除全部项目MATLAB源码、Live Script、专属配置和验证辅助脚本，包括旧快照中的副本。
MAT/FIG测试数据、CSV、图表及既有验证记录继续保留。原迁移清单描述删除前状态；
本次删除清单与当前Python检查见 [MATLAB删除记录](verification/matlab_removal_20261012.json)。

## 保留与位置

- RevB：`Unicorn_CSA_RevB-COB/tasks/<task-id>/{data,spectra,results,logs,provenance}`。
- 三颗芯片的历史联动过程完整保存在各任务的 `provenance/legacy_run/`。其中小型原始数据和输出副本用于保留证据，
  canonical `data/` 和 `results/` 用于后处理，不使用跨平台不稳定的符号链接。
- 跨任务结果：`Unicorn_CSA_RevB-COB/results/` 和 `comparisons/offset_drift_20260918/`。
- RevA：`history/RevA/`，四个历史目录同级保留，含70份TDMS及单独的Instrument Capture，以及已有频谱、MAT/FIG和图表。
- PXI：`history/PXI-5922/`，包含三类各十份波形及配置、Measurements CSV和三份源ZIP。
- OPA189：`history/OPA189/`，四条件处理后基准与图表保留，原始波形仍需补充；MATLAB重放入口已删除。
- demo：`Unicorn_CSA_RevB-COB/demo/` 整体忽略；Notebook和源代码继续保留。

## 现场与后处理

新入口分别是 [Windows现场](../Unicorn_CSA_RevB-COB/field/README.md) 和
[离线分析](../Unicorn_CSA_RevB-COB/postprocess/README.md)。现场电脑复制完整仓库，
安装NI-SCOPE/NI-VISA驱动和现场依赖；后处理电脑只安装分析依赖，复制完整任务目录即可。
所有设备控制保持原实现，Mac本次没有连接仪器。新入口已离线验证命令转发和错误处理；
真实仪器连接需在Windows现场验证。

## 原代码与数据保护

整理期间曾保存两轮旧代码、Notebook、文档和规则快照。用户于2026-10-12确认已有备份后，
按要求删除整个 `legacy/` 目录。历史迁移与验证JSON中记录的快照路径、数量和哈希仅描述当时状态，
不代表这些快照仍在当前仓库中。现用代码、历史测试数据及任务内采集证据继续保留。
RevB五个采集/分析模块增加直接任务目录参数；数值算法保持原样。

[迁移清单](../Unicorn_CSA_RevB-COB/migration_20261012.json) 逐文件记录原位置、新位置、字节数和SHA-256。
`task.json.raw_file_sha256` 绑定1306份正式原始TDMS；旧噪声1000文件清单的哈希不变，path调整为新位置并保留original_path。
执行快照、完成/失败标志和TDMS内部元数据不改写。重跑迁移脚本不会覆盖已有元数据或后处理结果。

## 验证

- 13噪声任务编号0001–0100、1300份TDMS/NPZ；默认后处理1300频谱全复用。
- 16任务真实回放：13组噪声摘要与原记录一致；Chip1/3三温度数值及斜率与原记录一致。
- Chip2保留0有效读数、失败原因及温度/通信证据，不生成有效offset或温漂斜率。
- 75项Python测试通过：原scripts47项、现场入口16项、离线后处理12项。
- 13组各抽取一份真实TDMS重算Welch，与已保存PSD最大相对误差约1.0e-14。
- 回归覆盖任务路径、原算法数值一致性、缓存频谱、缺失记录、阶段错放、原始文件改变、单点offset和失败标志。
- 检查旧代码SHA-256、迁移原始数据SHA-256、Git忽略规则、现行文档本地链接及Windows dry-run。

[真实回放验证](../Unicorn_CSA_RevB-COB/postprocess/verification_20261012.json) ·
[迁移完整性验证](../Unicorn_CSA_RevB-COB/migration_verification_20261012.json)。

这些检查验证数据、目录和离线处理，不改变持续±1℃稳定性未通过的原实验结论。

### 删除MATLAB前的全仓迁移与历史重放记录

以下记录描述MATLAB删除前已完成的核对，不代表当前仍保留对应源码、快照副本或运行入口。

- RevB 1,306份原始TDMS的SHA-256全部匹配，1,300份频谱齐全。
- 历史迁移共518份文件：509份原字节保留，9份入口仅更新路径或可选输出位置，原文快照与修改后哈希分别记录。
  FPGA清单110份逐项核对，其中109份原字节保留、README更新导航；三个历史固件均有独立哈希。
- 两轮源码、文档和规则快照共150+123份全部匹配；Gain101 MAT从本地LFS缓存恢复并验证变量及SHA-256。
- Python三组共75项测试在当前目录和仅含Git交付文件的副本中分别通过。
- MATLAB R2025b既有15项测试通过；RevA无屏蔽条件的两种共用算法profile数值重放通过，
  另验证四个比较入口及三份导出的普通`.m`入口。逐run最大相对差约`1.50e-11`。
- PXI三类共30份CSV原生重算通过，最大相对差约`1.02e-11`；OPA189正式四条件处理后重放通过。
  Gain101的120段PSD与恢复MAT最大相对差约`1.76e-12`。数值核对阈值为相对`1e-10`、绝对`1e-24`。

当时Mac缺少MATLAB原生`mexTDMS`组件。RevA验证将真实原始波形经npTDMS解码为临时MAT输入，
只在临时副本中替换读入步骤。该结果验证了数值算法，未验证本机原生MATLAB TDMS读取；相关代码现已删除。
有屏蔽及1p2的其余分析包装入口核对了路径并运行比较，未逐一重算所有条件。
OPA189仍缺原始波形，不将处理后重放记作原始采集链验证。

详细证据见 [历史MATLAB验证](../history/verification_20261012.json) 和
[全仓验证汇总](verification/main_baseline_20261012.json)。

## 主线整理与交付

[历史测试入口](../history/README.md)集中介绍RevA/PXI/OPA189；
[测试安排](../测试安排.md)管理当前待办，[测试日志](../测试日志.md)记录实际执行；
[详细报告](test-reports/README.md)保存条件、数字与实验限制。
旧委托记录作为历史背景保存，不继续作为当前测试的执行人或完成状态依据。

FPGA源工程、固件和编译报告分别管理，编译缓存仅留本地。旧PR审批约束改为
[个人维护流程](WORKFLOW.md)，保留Git LFS hooks和离线回归检查。
历史文件与固件的移动清单分别见`history/migration_20261012.json`、`fpga/migration_20261012.json`。
快照、历史结果和采集证据使用局部Git属性保留原始行尾，避免提交时规范化文本而破坏SHA-256；
这些不可改写的历史内容不参加空白格式修复，现行脚本仍运行普通差异检查。
Git与本地数据的交付边界及后续main发布步骤见 [main准备说明](MAIN_BASELINE.md)。

## 当前Mac环境

项目内 `.venv-postprocess/` 已配置，安装的分析依赖见
[环境记录](../Unicorn_CSA_RevB-COB/postprocess/mac_environment_20261012.json)。
该环境未安装NI-SCOPE或PyVISA；12项后处理测试及真实Chip1三温度重放通过。
现场设备接入保持在Windows电脑执行。

后续已将 RevB 日常后处理入口改为 [postprocess.ipynb](../Unicorn_CSA_RevB-COB/postprocess/postprocess.ipynb)，
输入 task-id，自动处理 noise / offset drift；`REGENERATE_SPECTRA` 控制 noise 的频谱复用或重算。
本机环境已补装 Jupyter。12项既有后处理测试和5项真实内核Notebook测试均通过，
另用真实噪声、Chip1温漂、Chip2失败任务的临时副本核对数值与图表，原数据未修改。
版本和验证范围见 [Notebook验证](../Unicorn_CSA_RevB-COB/postprocess/notebook_verification_20261012.json)。
RevA及更早的历史文件仅保留归档，不纳入该Notebook。

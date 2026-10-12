# RevB 测试结果与执行入口

这里保存最新 RevB（with PMU）芯片的正式数据。每个 task ID 集中保存原始数据、频谱、结果和采集证据，
无需在三个顶层目录之间来回找文件。

这些保留测试由项目负责人本人完成，依据为本人于2026-10-12确认；早期委托安排不作为实际执行人依据。

## 查看结果

- [全部任务数值索引](results/task_overview.csv) · [JSON 索引](results/task_overview.json)。
- [13组噪声和3组温漂结果目录](tasks/)；每个任务的 `README.md` 指向本任务数据和图表。
- [三颗芯片 trim / 供电噪声对比](results/noise_retest_20260918/noise_comparison.png)。
- [Chip 1 / Chip 3 温漂对比](comparisons/offset_drift_20260918/chip1_vs_chip3_20260918_run01/README.md)。
- [两颗芯片6000点统一CSV](comparisons/offset_drift_20260918/chip1_chip3_dmm_combined_20260919_run01/README.md)。

| 类型 | 保留数据 | 状态 |
| --- | --- | --- |
| 噪声 | 13组，每组100次，50kSa/s、22s、Gain1001 | 数据齐全 |
| Chip 1 offset drift | −40/27/125℃各1000点 | 完成；温度振荡明显 |
| Chip 3 offset drift | −40/27/125℃各1000点 | 完成；温度振荡明显 |
| Chip 2 offset drift | −40℃首点超量程，无有效电压读数 | 失败证据保留，无offset/斜率结果 |

噪声包括五颗芯片的 default/±6V 基线、Chip1的1p2、Chip1–3的max、Chip3的±12V default/max、
Chip2的1001和Chip1的1111重复组。max与1111为同一码，两组重复实验继续分别报告。

## 任务目录

```text
tasks/<task-id>/
  task.json
  data/                    # 噪声: *.tdms；温漂: stage_01..03/*.tdms, temperature.csv
  spectra/                 # 噪声逐次NPZ；温漂任务为空
  results/                 # 图表和摘要；温漂含stage_01..03/
  logs/
  provenance/legacy_run/   # 历史三温度采集证据完整保留
```

`task.json` 保存芯片、测量类型、完成/失败状态、点数和原始文件 SHA-256。
迁移前的三温度记录保存在 `provenance/legacy_run/`，其中小型TDMS及阶段输出有证据副本；
正式后处理读取 `data/` 并写 `results/`，核对其与原阶段证据一致。
采集失败和数据完整性是两个独立状态；Chip2会进入任务索引，不会生成虚假的温漂值。

## 两台电脑的分工

**Windows 现场电脑**使用 [field/](field/README.md)，安装现场依赖和实际 NI-SCOPE / NI-VISA 驱动。
入口默认只采集噪声；三温度联动沿用原控制器与DMM worker，并保留每阶段完成/失败标志。
需要实时边采边绘图时，原 `run_dut_revb_pmu_noise_pipeline.py` 仍保留在本目录。

**Mac 或其他后处理电脑**使用 [后处理 Notebook](postprocess/postprocess.ipynb)。输入 task-id 自动处理 noise 或 offset drift，
通过 `REGENERATE_SPECTRA` 选择是否重新生成 noise 频谱。依赖为 Jupyter 和离线分析库；复制完整 task 目录后即可处理。

当前Mac已配置仓库根目录 `.venv-postprocess/`（Git忽略），可直接使用其Python。

在仓库根目录：

```bash
python -m venv .venv-postprocess
.venv-postprocess/bin/python -m pip install -r Unicorn_CSA_RevB-COB/postprocess/requirements-notebook.txt
.venv-postprocess/bin/python -m ipykernel install --sys-prefix
.venv-postprocess/bin/python -m jupyterlab Unicorn_CSA_RevB-COB/postprocess/postprocess.ipynb
```

Windows 使用 `.venv-postprocess\Scripts\python.exe`；参数与原批量CLI见 [后处理说明](postprocess/README.md)。
默认复用已有NPZ、缺失补算，并重新生成图表/摘要。原始数据哈希、NPZ来源和温漂阶段归属都参与检查；
只有字段和数据一致才标记完整。噪声数值沿用原算法：Welch Hann、262144点、50%重叠、
constant detrend、mean PSD，先在PSD域平均再开方，输入端只除一次增益1001。

## 原代码与兼容

本目录原有采集、分析、流水线脚本和三份 Notebook 全部保留，根目录热流仪/DMM实现也保留。
采集与分析脚本新增可选 `--task-dir`，直接使用该任务的 `data/`、`spectra/`、`results/`；
DMM分析另支持 `--input-directory`、`--result-directory` 选择温度阶段。旧参数仍兼容旧目录。
整理前的原文件由用户另行备份，仓库中的旧快照已删除。

`demo/` 的调试数据和结果仅留本地，不参与Git和正式任务索引。
原始TDMS/NPZ也继续遵守仓库忽略规则；迁移结果记录见 [迁移清单](migration_20261012.json)。

## 历史保留与验证

RevA / PXI 和 OPA189 数据与历史结果已集中到 [history/](../history/README.md)。MATLAB 源码、Live Script、专用验证脚本及其源码快照已移除，历史 MAT/FIG 和 JSON 验证证据保留；本目录的 Python 现场采集与离线后处理入口继续使用。
本次整理移除了其他早期offset与独立热流仪结果；保留9月18日三颗芯片的联动温度日志和失败证据。

真实16任务回放数值核对见 [离线验证](postprocess/verification_20261012.json)。
结构变更和数据完整性验证见 [整理记录](../docs/RESULTS_LAYOUT.md)。

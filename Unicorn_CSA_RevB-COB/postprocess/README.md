# RevB Jupyter 后处理

主要入口是 [postprocess.ipynb](postprocess.ipynb)。输入 RevB 的 **task-id**，自动识别 `noise` 或 `offset_drift`，运行后在 Notebook 中查看摘要和图表。
RevA 及更早的历史数据保持文件归档，不参与这个 Notebook。

## 安装与打开

在仓库根目录创建 Python 3.10+ 环境：

```sh
python -m venv .venv-postprocess
```

Windows 执行 `.venv-postprocess\Scripts\activate`；macOS/Linux 执行 `source .venv-postprocess/bin/activate`。随后：

```sh
python -m pip install -r Unicorn_CSA_RevB-COB/postprocess/requirements-notebook.txt
python -m ipykernel install --sys-prefix
python -m jupyterlab Unicorn_CSA_RevB-COB/postprocess/postprocess.ipynb
```

选择刚安装依赖的 Python 内核。依赖包含 Jupyter 和离线分析库，不需要 NI-SCOPE、PyVISA 或仪器驱动。
原 `requirements.txt` 仍是纯命令行分析依赖；Notebook 使用 `requirements-notebook.txt`。

## 只需改参数单元

```python
TASK_ID = "RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V"
REGENERATE_SPECTRA = False
```

点击 **Run → Run All Cells**。Notebook 会显示可用 task-id、所选任务条件、采集/数据/处理状态，以及该任务的结果。
更换任务或参数后重新运行全部单元。温漂示例：

```python
TASK_ID = "Offset_Chip_1_Gain1001_20260918"
```

| 参数 | 行为 |
| --- | --- |
| `TASK_ID` | `tasks/` 下的任务目录名；类型从 `task.json` 自动读取 |
| `REGENERATE_SPECTRA=False` | noise 复用已有 NPZ；缺失的频谱从原始 TDMS 补算；结果图和摘要重新生成 |
| `REGENERATE_SPECTRA=True` | noise 从 TDMS 全部重算，覆盖该任务的 NPZ；缺少对应原始波形时停止，不静默沿用旧频谱 |
| `TASKS_ROOT=None` | 自动使用仓库的 `Unicorn_CSA_RevB-COB/tasks/`；外置磁盘可填写完整 `tasks` 路径 |
| `WELCH_NPERSEG=262_144` | Welch 分段长度，只作用于新生成的频谱；修改该参数时应选择全部重算 |

offset drift 不使用 spectra 开关，每次分析有效温度阶段。Chip 2 失败记录保持 0 有效读数、无温漂斜率，显示失败原因；不会把已有旧 offset 图当作本次有效结果。

路径支持 Windows/macOS/Linux。请从仓库或 `postprocess/` 目录启动 Jupyter；Windows 外置数据示例：

```python
TASKS_ROOT = r"D:\Unicorn_Testbench\Unicorn_CSA_RevB-COB\tasks"
```

## 输入、输出与实验限制

输入目录为 `tasks/<task-id>/{data,spectra,provenance}`，须保留完整 `task.json`。原始 TDMS、NPZ 大部分不在 Git 中，跨电脑需另外复制完整任务目录。

- Noise 展示 1 Hz / 1 kHz 输入等效噪声、频谱新生成/复用数量、平均 ASD 和分布图。
- Offset drift 展示阶段读数、offset 均值和样本标准差、实测温度范围、按名义温度拟合的斜率，以及 offset 图和已有控温曲线。
- 结果写回该任务的 `results/`，noise 频谱写回同任务的 `spectra/`。同时刷新 `tasks/` 同级 `results/task_overview.csv` 和 `.json`。
- 原始 `data/` 与采集 `provenance/` 不改写。`.acquisition.lock` 或 `acquisition_status=acquiring` 的任务在处理前停止。
- 原始文件哈希、频谱 task/run/增益/采样参数与温漂阶段归属仍按原规则检查。数据完整、采集完成与器件规格通过分别表达；9月18日控温稳定性问题保持原结论。

提交 Notebook 前清空输出，避免重复保存图表和本机路径。

## 计算实现与命令行兼容

Notebook 复用 `process_tasks.py` 和原分析模块，Welch、PSD 域平均、局部功率估计和 DMM 数值算法不变。
原命令行仍可用于批量处理（`dcv_offset` 独立单点类型也保留 CLI 兼容）：

```sh
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --all
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --task-id Offset_Chip_1_Gain1001_20260918
```

安装 Notebook 依赖后运行后处理回归；新增测试会在真实 Jupyter 内核中执行 Notebook，使用临时合成数据，不连接仪器：

```sh
python -m unittest discover -s Unicorn_CSA_RevB-COB/postprocess -p 'test_*.py' -v
```

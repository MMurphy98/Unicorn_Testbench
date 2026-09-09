# DUT RevB（with PMU）噪声与 Offset 测试

本目录同时提供 PXI-5922 噪声测试流程和 Keithley DMM7510 DCV offset 测试流程。Notebook 仅保留为设备连接和单次采集模板，批量正式测试不依赖 Jupyter。

## 文件

- `capture_dut_revb_pmu_noise.py`：通过 NI-SCOPE 连续执行多次采集，每次写入一个经过回读验证的 `float64` TDMS。
- `analyze_dut_revb_pmu_noise.py`：逐个读取 TDMS，计算 Welch PSD，每个 TDMS 保存一个压缩的 NPZ 频谱文件。
- `plot_dut_revb_pmu_noise.py`：读取全部 NPZ，先平均 PSD，再转换为输入等效 ASD，并绘制平均曲线和平滑估计虚线。
- `run_dut_revb_pmu_noise_pipeline.py`：启动采集，并在采集过程中持续分析新增 TDMS、定期刷新平均频谱图。
- `dut_revb_pmu_noise_capture.ipynb`：换片后的单次快速验证模板；TDMS 输出到 `data/demo/`，采集后内联显示时域波形和单次噪声谱。
- `capture_dmm7510_offset.py`：通过 USB VISA 配置 DMM7510，保存经过回读验证的多读数 DCV TDMS。
- `analyze_dmm7510_offset.py`：汇总一个 task-id 的 DMM TDMS，计算并绘制输出及输入等效 offset。
- `keithley_dmm7510_dcv_offset_demo.ipynb`：DMM7510 连接、低电平 DCV 和短时平均的交互验证模板。
- `test_demo.ipynb`：最初的设备连接验证模板。

## 当前测试任务

当前开始执行的测试使用以下 `task_id`：

```text
RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V
```

字段含义：

| 字段 | 测试条件 |
|---|---|
| `RevB` | DUT 硬件版本为 RevB（with PMU） |
| `Chip_1` | 1 号芯片 |
| `wiShield` | 安装金属防护壳 |
| `Gmx_default` | Gmx 偏置电流使用默认设置，控制码为 `4'b0110` |
| `OSC_default` | 时钟频率使用默认设置 |
| `Vsup_pm6V` | DUT 供电电压为 ±6 V |

采集命令为：

```powershell
python .\capture_dut_revb_pmu_noise.py --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V
```

## 环境

当前测试环境为 **Windows 64 位、CPython 3.11.9**，使用标准 `venv` 虚拟环境
`C:\Users\jinge\Envs\ni-scope-2023q4`。以下版本于 2026-09-09 从该环境实际读取，
`python -m pip check` 检查通过。

| Python 库 | 当前版本 | 用途 |
|---|---|---|
| `niscope` | `1.4.7` | NI PXI-5922 采集接口 |
| `PyVISA` | `1.16.2` | Keithley DMM7510 USB VISA 通信 |
| `npTDMS` | `1.11.0` | TDMS 写入、读取及回读校验；采集脚本要求此固定版本 |
| `numpy` | `2.4.6` | 波形、PSD 和统计数组运算 |
| `scipy` | `1.17.1` | Welch PSD 与 offset 统计 |
| `matplotlib` | `3.11.1` | 时域、频谱和分布绘图 |

Notebook 环境另装有 `ipykernel==7.3.0`、`ipython==9.17.1`；当前 `pip` 为 `26.2.1`。
批量采集、分析和绘图脚本不需要 Notebook 内核。

### 使用现有环境

```powershell
& C:\Users\jinge\Envs\ni-scope-2023q4\Scripts\Activate.ps1
cd C:\Users\jinge\Projects\Unicorn_Testbench\Unicorn_CSA_RevB-COB
```

### 新建环境

先安装 64 位 CPython 3.11.9，再从本目录运行。`requirements.txt` 固定上表六个主要依赖的版本；
间接依赖由 pip 解析，此文件不是整个环境的完整锁文件。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -r requirements.txt
python -m pip check
```

需要运行 Notebook 时，在同一环境中安装并注册内核，然后在 Notebook 编辑器中选择它：

```powershell
python -m pip install ipykernel==7.3.0 ipython==9.17.1
python -m ipykernel install --user --name ni-scope-2023q4 --display-name "Python 3.11 (NI-SCOPE 2023 Q4)"
```

### 仪器驱动与环境检查

Python 包之外还需要独立安装仪器驱动。现有 NI-SCOPE Notebook 的设备回读记录为
**NI-SCOPE 23.8.0（2023 Q4）**；`niscope==1.4.7` 是 Python 接口包版本，两者分别管理。
DMM7510 USB 控制要求 Windows 已安装完整的 **NI-VISA Runtime**；仅安装 `PyVISA` 不包含此驱动。
离线 TDMS/NPZ 分析和绘图无需连接仪器。

可以确认当前解释器和依赖位置：

```powershell
python --version
python -c "import sys; print(sys.executable)"
python -m pip show niscope PyVISA npTDMS numpy scipy matplotlib
python -m pip check
```

## 一条命令持续执行三个步骤（推荐）

先关闭 InstrumentStudio，然后在已激活的虚拟环境中运行：

```powershell
python .\run_dut_revb_pmu_noise_pipeline.py `
  --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V `
  --runs 100
```

执行器始终使用启动它的同一个 Python 解释器，因此只需要在启动前激活一次虚拟环境。它会：

1. 在子进程中运行采集脚本，采集进度仍然实时打印到当前终端。
2. 每 5 秒检查一次已经完成并验证通过的 `.tdms`；不会读取正在写入的 `.partial.tdms`。
3. 发现新增 TDMS 后运行频谱分析；已经存在的 NPZ 会由分析脚本自动跳过。
4. 第一个频谱完成后立即绘图，此后默认每新增 10 个频谱刷新一次汇总图，避免频繁重复读取全部频谱。
5. 采集进程结束后强制执行一次最终分析和最终绘图。

如需每完成一份频谱就更新图，增加 `--plot-every 1`：

```powershell
python .\run_dut_revb_pmu_noise_pipeline.py `
  --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V `
  --runs 100 `
  --plot-every 1
```

以后数据不够时，用相同的 `task_id` 再补采即可。下面的命令会沿用已有编号、只分析新数据，最后重新生成包含全部数据的平均结果：

```powershell
python .\run_dut_revb_pmu_noise_pipeline.py `
  --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V `
  --runs 20
```

按 `Ctrl+C` 时，执行器会请求采集脚本正常停止，并对已经完整落盘的数据执行最终分析和绘图。只想重新处理现有数据而不连接 NI-SCOPE 时使用：

```powershell
python .\run_dut_revb_pmu_noise_pipeline.py `
  --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V `
  --process-existing-only
```

默认只保存图片；希望全部结束后打开最终交互图时增加 `--show-final`。可以先用 `--dry-run` 检查将要启动的三个命令而不真正执行。

## 第一步：采集 TDMS

开始前关闭 InstrumentStudio。默认命令会连接 `PXI1Slot2` 的 CH0，连续采集 100 个记录，每个记录为 50 kSa/s、1,100,000 点、22 秒、1 MΩ、2 Vpp：

```powershell
python .\capture_dut_revb_pmu_noise.py
```

等价的完整参数写法：

```powershell
python .\capture_dut_revb_pmu_noise.py `
  --task-id DUT_RevB_with_PMU `
  --runs 100 `
  --resource PXI1Slot2 `
  --channel 0 `
  --sample-rate 50000 `
  --samples 1100000 `
  --input-impedance 1000000 `
  --vertical-range 2.0 `
  --gain 1001 `
  --gbw 15000000
```

输出目录为：

```text
data/<task_id>/<task_id>_0001.tdms
data/<task_id>/<task_id>_0002.tdms
...
```

脚本在每次采集前扫描已有的最终文件和 `*.partial.tdms`，从当前最大编号继续，不覆盖旧文件。例如已经存在 `0001` 至 `0100` 时，再运行：

```powershell
python .\capture_dut_revb_pmu_noise.py --task-id DUT_RevB_with_PMU --runs 20
```

新文件将从 `0101` 开始。每个最终 TDMS 都经过 dtype、点数、采样间隔和逐点数据一致性检查；未通过验证的文件不会被提升为最终文件。控制台会显示采集进度、均值、AC RMS、峰峰值、削顶状态和预计剩余时间。

使用新的测试条件时应更换 `task_id`，避免把不同配置的数据混入同一次平均。`task_id` 可以包含英文字母、数字、点、下划线和连字符。

## 第二步：逐文件计算频谱

```powershell
python .\analyze_dut_revb_pmu_noise.py --task-id DUT_RevB_with_PMU
```

脚本读取：

```text
data/<task_id>/<task_id>_NNNN.tdms
```

并输出：

```text
spectra/<task_id>/<task_id>_NNNN_spectrum.npz
```

每个 NPZ 保存频率轴、输入等效 PSD（`V²/Hz`）、源 TDMS 路径、采集编号、闭环增益和 Welch 参数。默认 Welch 配置为：

- Hann 窗
- `nperseg=262144`
- 50% overlap
- constant detrend
- mean averaging
- one-sided、`scaling="density"`

已有 NPZ 默认跳过，因此补充采集后可以直接再次运行，只分析新增 TDMS。如需重新计算全部频谱：

```powershell
python .\analyze_dut_revb_pmu_noise.py `
  --task-id DUT_RevB_with_PMU `
  --overwrite
```

`--overwrite` 会替换该任务已经生成的 NPZ，请只在确实需要改变分析参数时使用。

## 第三步：平均和绘图

```powershell
python .\plot_dut_revb_pmu_noise.py --task-id DUT_RevB_with_PMU --show
```

脚本按照以下顺序处理：

1. 读取该任务的全部 NPZ。
2. 验证所有频率轴、Welch 参数和闭环带宽一致。
3. 对输入等效 PSD 做算术平均。
4. 对平均 PSD 开平方并乘以 `1e9`，得到 `nV/√Hz`。
5. 绘制 1 Hz 至 25 kHz 的 log-log 平均 ASD 实线。
6. 绘制 1/6 倍频程宽度的局部功率平均虚线；频点不足时至少使用相邻 5 个 FFT bin。
7. 打印并标记 1 Hz 和 1 kHz 的最近频点值与平滑估计值。
8. 对每个 run 分别计算与主图标记相同的 1 Hz、1 kHz 局部功率估计，输出分布图、逐次 CSV 和统计摘要。

结果保存在：

```text
results/<task_id>/<task_id>_average_input_noise_asd.png
results/<task_id>/<task_id>_target_asd_distributions.png
results/<task_id>/<task_id>_target_asd_distribution.csv
results/<task_id>/<task_id>_noise_summary.json
```

分布图中的每个样本代表一份完整 TDMS 记录。1 Hz 和 1 kHz 都沿用主频谱图红色虚线的定义：先在目标附近的局部频带内平均 PSD，再开平方换算为 `nV/√Hz`。默认频率网格下，1 Hz 至少使用相邻 5 个 FFT bin；1 kHz 使用完整的 1/6 倍频程频带。JSON 同时保存均值、中位数、样本标准差、变异系数、四分位数、2.5%–97.5% 分位区间和极值。

不需要交互显示时去掉 `--show`。每次补充采集并完成第二步后，重新执行第三步即可更新平均结果。

## DMM7510 Offset 两步测试

正式 offset 测试使用两个脚本。交互式 Notebook 只用于换片后快速确认接线和数量级；正式采集时不要同时运行 Notebook、KickStart、InstrumentStudio 或其他访问 DMM7510 的 VISA 程序。

### 第一步：采集 DCV TDMS

DMM7510 使用后面板 USB Type-B Device 端口连接电脑，DUT 输出接到选定的测量端子。默认要求前端子，并配置 100 mV 固定量程、AUTO 高输入阻抗、10 NPLC、Auto Zero 和工频同步开启，autorange、REL/null 与 DMM 内置平均关闭。DMM7510 的 SCPI 端子命令只支持查询；需要用仪器面板的 TERMINALS 控件选择 FRONT 或 REAR，脚本只回读并验证是否符合 `--terminals`。每轮先等待 2 秒、丢弃 3 次稳定读数，然后保存 100 次独立读数：

```powershell
python .\capture_dmm7510_offset.py `
  --task-id RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V
```

完整默认参数等价于：

```powershell
python .\capture_dmm7510_offset.py `
  --task-id DUT_RevB_with_PMU `
  --runs 1 `
  --readings 100 `
  --terminals FRONT `
  --range 0.1 `
  --input-impedance AUTO `
  --nplc 10 `
  --settling-delay 2 `
  --discard-readings 3 `
  --gain 1001
```

未传入 `--resource` 时，脚本要求系统中恰好存在一台 USB DMM7510；也可以显式指定：

```powershell
python .\capture_dmm7510_offset.py `
  --task-id DUT_RevB_with_PMU `
  --resource USB0::0x05E6::0x7510::04476049::INSTR
```

脚本使用独占 VISA 锁，不执行 `*RST`，也不启用 REL/null。TDMS 保存到：

```text
data/<task_id>/<task_id>_dcv_0001.tdms
```

同一目录中的 NI-SCOPE 文件仍为 `<task_id>_0001.tdms`，DMM 文件通过 `_dcv_` 明确区分，两个分析流程不会互相读取。每份 DMM TDMS 包含 `float64` 的 `DCV` 和 `ElapsedTime` 两个通道。再次使用相同 task-id 运行时会扫描已有最终文件和 `.partial.tdms`，从最大 DMM 编号继续，不覆盖旧数据。例如再补充两轮、每轮 100 次：

```powershell
python .\capture_dmm7510_offset.py `
  --task-id DUT_RevB_with_PMU `
  --runs 2 `
  --readings 100
```

### 第二步：统计和绘图

```powershell
python .\analyze_dmm7510_offset.py `
  --task-id DUT_RevB_with_PMU `
  --show
```

不需要打开交互窗口时去掉 `--show`。脚本只读取该 task-id 下的 `_dcv_NNNN.tdms`，并验证所有轮次使用相同的仪器、端子、量程、输入阻抗、NPLC、Auto Zero 状态和闭环增益。结果保存为：

```text
results/<task_id>/<task_id>_dcv_offset.png
results/<task_id>/<task_id>_dcv_readings.csv
results/<task_id>/<task_id>_dcv_offset_summary.json
```

输入等效 offset 按 `mean(output DCV) / closed-loop gain` 计算。图中依次显示放大后 DCV 随时间的散点、输入等效 offset 的累计均值和描述性 95% t 区间、以及全部输入等效读数的分布。CSV 保留每个 run 的每次原始读数；JSON 同时保存总体统计、逐轮统计和多轮均值的变化。

标准误和 95% 区间用于描述本次重复读数的短期收敛性，默认假设读数相互独立；它们不包含 DMM 校准误差、热电势、闭环增益误差、DUT 温漂或相关的低频漂移。正式测量仍应先让 DMM7510 和 DUT 充分预热。

## 数据量和统计含义

本目录的 `results/` 图表、CSV 和 JSON 摘要进入 Git；`data/` 原始采集、`spectra/` 逐次频谱、
NPZ/MAT/FIG 和临时文件保持本地。频谱分析脚本仍随代码提交，可在取得原始数据后重新生成中间频谱。

默认每个 TDMS 约 8.8 MB，100 次约 880 MB。每个 22 秒文件在默认 Welch 参数下贡献约 7 段，100 个文件约为 700 段平均。

脚本平均的是 PSD，而不是直接平均 ASD。这样可以正确累计噪声功率：

```text
average ASD = sqrt(mean(input PSD)) × 1e9 nV/√Hz
```

虚线是局部频带内 PSD 的功率平均估计，不会从原始频谱中删除 50 Hz、电源谐波、斩波纹波或其他窄带峰。报告结果仍然包含 DUT、反馈网络、夹具和 PXI-5922 的共同贡献；没有进行采集链基线扣除，也没有对约 15 kHz 的闭环带宽做反卷积。

## 查看帮助

```powershell
python .\capture_dut_revb_pmu_noise.py --help
python .\analyze_dut_revb_pmu_noise.py --help
python .\plot_dut_revb_pmu_noise.py --help
python .\run_dut_revb_pmu_noise_pipeline.py --help
python .\capture_dmm7510_offset.py --help
python .\analyze_dmm7510_offset.py --help
```

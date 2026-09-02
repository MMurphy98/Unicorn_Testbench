# DUT RevB（with PMU）噪声采集与分析

本目录提供三个可以独立执行的 Python 脚本，以及一个持续编排这三个步骤的执行器。Notebook 仅保留为设备连接和单次采集模板，批量正式测试不依赖 Jupyter。

## 文件

- `capture_dut_revb_pmu_noise.py`：通过 NI-SCOPE 连续执行多次采集，每次写入一个经过回读验证的 `float64` TDMS。
- `analyze_dut_revb_pmu_noise.py`：逐个读取 TDMS，计算 Welch PSD，每个 TDMS 保存一个压缩的 NPZ 频谱文件。
- `plot_dut_revb_pmu_noise.py`：读取全部 NPZ，先平均 PSD，再转换为输入等效 ASD，并绘制平均曲线和平滑估计虚线。
- `run_dut_revb_pmu_noise_pipeline.py`：启动采集，并在采集过程中持续分析新增 TDMS、定期刷新平均频谱图。
- `dut_revb_pmu_noise_capture.ipynb`：换片后的单次快速验证模板；TDMS 输出到 `data/demo/`，采集后内联显示时域波形和单次噪声谱。
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

推荐使用现有虚拟环境：

```powershell
& C:\Users\jinge\Envs\ni-scope-2023q4\Scripts\Activate.ps1
cd C:\Users\jinge\Projects\Unicorn_Testbench\Unicorn_CSA_RevB-COB
```

依赖包括 `niscope`、`numpy`、`scipy`、`matplotlib` 和固定版本 `nptdms==1.11.0`。可以确认当前解释器和依赖位置：

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show niscope nptdms numpy scipy matplotlib
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

结果保存在：

```text
results/<task_id>/<task_id>_average_input_noise_asd.png
results/<task_id>/<task_id>_noise_summary.json
```

不需要交互显示时去掉 `--show`。每次补充采集并完成第二步后，重新执行第三步即可更新平均结果。

## 数据量和统计含义

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
```

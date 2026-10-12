# Windows 现场采集

此目录是现场电脑的入口。保留的原始采集脚本负责仪器配置、读回校验及 TDMS 写入；新入口负责 task 路径、运行日志和代码快照。默认只采集，后处理在 `../postprocess/` 运行。

现场电脑应复制完整仓库，包括根目录 `scripts/` 和 `Unicorn_CSA_RevB-COB/`。温漂控制器、独立 DMM worker 和握手校验仍使用根目录原代码，不要只复制此 `field/` 文件夹。原环境为 Windows 64 位、CPython 3.11.9；现场仍需安装并配置 NI-SCOPE、NI-VISA 驱动。原脚本的仪器资源及采集默认值沿用此前配置，可以在命令行覆盖。

在仓库根目录运行 PowerShell：

```powershell
py -3.11 -m venv .venv-field
.venv-field\Scripts\python.exe -m pip install -r Unicorn_CSA_RevB-COB\field\requirements.txt
```

热流仪 + DMM 三温度流程需要原来的每阶段分析和绘图依赖，以生成 DMM 完成握手：

```powershell
.venv-field\Scripts\python.exe -m pip install -r Unicorn_CSA_RevB-COB\field\requirements-offset-drift.txt
```

## 噪声采集

为新实验使用新的 task ID。例子中的 `NEW` 请替换成实际日期、批次或条件。开始 NI-SCOPE 采集前关闭 InstrumentStudio，原采集脚本会检查。

```powershell
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\capture_noise.py --task-id Noise_RevB_Chip_1_NEW --chip 1 --runs 100 --resource PXI1Slot2 --channel 0 --dry-run
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\capture_noise.py --task-id Noise_RevB_Chip_1_NEW --chip 1 --runs 100 --resource PXI1Slot2 --channel 0
```

输出直接进入 `tasks/Noise_RevB_Chip_1_NEW/data/`，不会再套一层 task ID。条件相同的重复采集会按原算法接着编号，不覆盖已完成的 TDMS；采集次数和超时可以调整。入口会先核对已有 task 保存的资源、通道、采样、量程、阻抗、增益等采集条件，变化时拒绝复用 task ID。迁移的历史 task 若没有现场入口保存的采集配置，也应使用新 task ID 续测；`--dry-run` 同样会报告此检查结果。

`run_noise_pipeline.py` 的采集参数相同，默认也只采集。若现场已安装后处理依赖，可以使用 `--postprocess` 在采集成功后处理一次；原来边采边更新图的 `run_dut_revb_pmu_noise_pipeline.py` 仍保留。

```powershell
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\run_noise_pipeline.py --task-id Noise_RevB_Chip_1_NEW --chip 1 --runs 100
# 可选：由独立的分析 Python 完成后处理
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\run_noise_pipeline.py --task-id Noise_RevB_Chip_1_NEW --chip 1 --runs 100 --postprocess --postprocess-python C:\Envs\analysis\Scripts\python.exe
```

## 三温度 offset drift

此入口沿用原来的 −40、27、125 °C 流程、首次到温后 300 秒等待、独立 DMM worker 和 STOP 清理逻辑。每个温漂 task 只运行一次，已有原始数据时会拒绝复用 task ID。

```powershell
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\run_offset_drift.py --task-id Offset_Chip_1_Gain1001_NEW --chip 1 --host 192.168.1.50 --readings 1000 --gain 1001 --dmm-range 0.1 --terminals FRONT --dry-run
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\run_offset_drift.py --task-id Offset_Chip_1_Gain1001_NEW --chip 1 --host 192.168.1.50 --readings 1000 --gain 1001 --dmm-range 0.1 --terminals FRONT
```

可用 `--dmm-resource "USB0::...::INSTR"` 指定现场 DMM，用 `--dmm-python` 指定独立 worker 的 Python。`--readings-per-stage 1000 1000 1000` 可分别指定三温度点数。其他现有控制参数可以用 `--help` 查看。

完整握手、原始输出和代码快照存于 `task/provenance/acquisition_.../legacy_run/`。结束后，已采集的数据（包括失败或中止的证据）复制到 `task/data/stage_01/` 等目录，阶段和总结果进入 `task/results/`，通讯及 worker 日志进入 `task/logs/`。`task.json` 保存 `legacy_run_path`，后处理可以核对整个流程；失败时 `acquisition_status` 为 `failed`，不会标记完整。执行中可用 Ctrl+C，或在入口打印的路径创建 `STOP` 文件，原控制器会执行停止和清理。

## 单独 DCV offset 采集

```powershell
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\capture_offset.py --task-id Offset_Chip_1_room_NEW --chip 1 --readings 1000 --gain 1001 --range 0.1 --dry-run
.venv-field\Scripts\python.exe Unicorn_CSA_RevB-COB\field\capture_offset.py --task-id Offset_Chip_1_room_NEW --chip 1 --readings 1000 --gain 1001 --range 0.1
```

这是室温单点记录，`measurement_type=dcv_offset`，与三温度 `offset_drift` task 分开。原 DMM 分析脚本支持 `--task-dir`，可用安装了后处理依赖的 Python 分析：

```powershell
C:\Envs\analysis\Scripts\python.exe Unicorn_CSA_RevB-COB\analyze_dmm7510_offset.py --task-id Offset_Chip_1_room_NEW --task-dir Unicorn_CSA_RevB-COB\tasks\Offset_Chip_1_room_NEW
```

## 复制到后处理电脑

复制完整 `tasks/<task-id>/`，包括 `data/`、`task.json` 和 `provenance/`，再按 `../postprocess/README.md` 安装分析依赖。后处理不需要 NI-SCOPE、PyVISA 或现场驱动。例如：

```bash
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --task-id Noise_RevB_Chip_1_NEW
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --task-id Offset_Chip_1_Gain1001_NEW
```

`--tasks-root` 可以指定外部数据盘或同步目录。所有入口的 `--help` 与 `--dry-run` 在 Mac 上也可运行，不创建文件、不导入硬件库、不访问仪器。运行日志和 provenance 保留失败原因；只有进程成功结束才将采集标记为完成。采集结束时，`task.json` 的 `raw_file_sha256` 保存完整 TDMS 原始字节的 SHA-256，包含失败批次中已经完成的记录，排除 `.partial.tdms`；续测保留既有哈希，文件大小和修改时间未变化时复用哈希。已知原始文件发生变化会报错并保留原哈希，后处理也会据此检查原始数据。task 中的 `.acquisition.lock` 防止新入口同时采集同一个 task；异常断电后，先确认旧进程已退出，再移走此锁文件。

## 本机离线验证

```bash
python -m unittest discover -s Unicorn_CSA_RevB-COB/field -p 'test_*.py'
```

测试覆盖命令转发、新路径、失败数据发布和 provenance，不连接任何仪器。现场实际仪器连接仍需在 Windows 电脑验证。

# Chip 2 三温度 offset drift — 2026-09-18

测试执行：项目负责人本人（依据本人于2026-10-12确认）；早期委托安排不作为本组测试的执行人依据。

Task ID：`Offset_Chip_2_Gain1001_20260918`。−40/27/125℃；Gain1001、固定6SCFM，每点首次到温后等待300秒。

首个计划读数超量程，0个有效电压读数，27℃与125℃未启动。此任务保留失败证据，没有有效offset或温漂斜率。

[原始运行报告](provenance/legacy_run/README.md) · [完成/失败记录](provenance/legacy_run/summary.json)

本地原始数据：`data/` · [处理结果](results/) · [运行日志](logs/) · [任务元数据/原始哈希](task.json)。

原始数据及逐次频谱不随Git提交，重放前需复制完整任务目录。

从仓库根目录执行：

```bash
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --task-id Offset_Chip_2_Gain1001_20260918
```

[现场入口](../../field/README.md) · [后处理说明](../../postprocess/README.md)。

# Chip 1 噪声 — 4b1111 / pm6V

测试执行：项目负责人本人（依据本人于2026-10-12确认）；早期委托安排不作为本组测试的执行人依据。

Task ID：`RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V`。100次，50kSa/s、22秒、每份1,100,000点、Gain1001。

[平均噪声图](results/RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V_average_input_noise_asd.png) · [逐次分布](results/RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V_target_asd_distributions.png)

[数值摘要](results/RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V_noise_summary.json) · [逐次ASD CSV](results/RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V_target_asd_distribution.csv)

本地原始TDMS：`data/` · 本地逐次频谱：`spectra/` · [任务元数据/原始哈希](task.json)。

原始数据及逐次频谱不随Git提交，重放前需复制完整任务目录。

从仓库根目录执行：

```bash
python Unicorn_CSA_RevB-COB/postprocess/process_tasks.py --task-id RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V
```

[现场入口](../../field/README.md) · [后处理说明](../../postprocess/README.md)。

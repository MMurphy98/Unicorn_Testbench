# RevA 历史噪声

四个原目录保持同级、保持原名，包括原来的 `Shiled` 拼写，方便对应历史记录：

| 条件 | 目录 | 本地 TDMS 数量 |
|---|---|---:|
| 有屏蔽罩 | `Unicorn_CSA_RevA-COB_wiShiled_20260828/` | 20 |
| 无屏蔽罩，默认电流 | `Unicorn_CSA_RevA-COB_woShiled_20260828/` | 20 |
| 无屏蔽罩，1.2 倍电流 | `Unicorn_CSA_RevA-COB_woShiled_1p2_20260828/` | 20 |
| 无屏蔽罩，Gain101 | `Unicorn_CSA_RevA-COB_woShiled_Gain101_20260829/` | 10 |

本层另保存 `Instrument Capture 2026-08-28.tdms`、Gain101 工作区 MAT 和 Gain1001/Gain101 FIG。TDMS、MAT、FIG 保持原字节；原 MATLAB 源码、Live Script 及其源码快照已移除。

本目录现只保留历史原始数据与已有结果。三个 20 次采集条件的 `analysis_results/` 保存全记录噪声结果，`analysis_results/welch_8s_50pct/` 保存 Welch 结果；屏蔽和电流比较图表仍位于对应条件结果目录。

Gain101 工作区保留旧探索方法的 120 个不重叠 periodogram 段，与正式 8 秒、50% 重叠的 Welch 方法不同。比较历史结果时需保持方法和参数一致。

Gain101 的工作区 MAT 原来不在工作树中；迁移时从本地 Git LFS 缓存检查采样率、PSD 尺寸和频率网格后恢复到本层。其来源和校验记录见迁移清单与验证报告，不需要联网下载。

删除代码前的数值验证记录保存在 `../verification_20261012.json`。当时通过临时数组桥接核对核心数值，macOS 原生 TDMS 读取因缺少 `mexTDMS` 未完成验证；该记录是历史证据，不是现行运行入口。

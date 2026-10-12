# Chip 1 / Chip 3 DMM读数合并CSV

[下载统一CSV](chip1_chip3_dmm_readings_20260918.csv)：6000条读数、12列，单行表头。Chip 1和Chip 3各3000点，−40℃、27℃、125℃各1000点。采集日期为2026-09-18。

CSV为UTF-8带BOM编码、逗号分隔、小数点为句点。字段名含单位，数值单元格不混入单位文字。一个读数一行，按芯片、温度阶段、读数序号排列，可直接用Excel、Origin或Python导入。

唯一键为source_run_id + stage_index + reading_index。该CSV可独立用于绘图，不需要TDMS或其他来源文件。

## 字段与绘图

| 字段 | 含义 |
| --- | --- |
| `chip_id` | 芯片编号：1或3。 |
| `stage_index` | 该轮温度阶段：1=−40℃、2=27℃、3=125℃。 |
| `target_temperature_c` | 名义目标温度，单位℃；不是逐点实测产品温度。 |
| `reading_index` | 每个阶段内的有效读数序号，1～1000。 |
| `elapsed_s` | 原始TDMS的DMM采集相对时间，单位秒；每段独立起算，第一点约0.33秒。 |
| `acquisition_time_utc` | 原始采样时间戳，ISO 8601、UTC、微秒精度；北京时间为UTC+8。 |
| `output_voltage_v` | DMM原始输出电压，单位V，从TDMS完整精度读取。 |
| `equivalent_input_offset_v` | 输入等效offset，单位V：output_voltage_v / 1001。 |
| `equivalent_input_offset_uv` | 输入等效offset，单位µV：equivalent_input_offset_v × 1000000，可直接绘图。 |
| `gain_v_per_v` | 实际增益元数据，所有行均为1001 V/V。 |
| `flow_setpoint_scfm` | 流量设定元数据，所有行均为6 SCFM；不是瞬时实测流量。 |
| `source_run_id` | 来源运行记录编号，用于区分Chip 1与Chip 3的独立测试。 |

绘制温度–offset曲线时，按chip_id、target_temperature_c分组，计算equivalent_input_offset_uv的均值和样本标准差（ddof=1）。绘制原始波形时，先选定一组芯片和目标温度，以elapsed_s或reading_index为横轴。输入等效列已经除过增益，不要再次除以1001。

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("chip1_chip3_dmm_readings_20260918.csv", encoding="utf-8-sig", float_precision="round_trip")
for chip, rows in df.groupby("chip_id"):
    stats = rows.groupby("target_temperature_c")["equivalent_input_offset_uv"].agg(["mean", "std", "count"])
    plt.errorbar(stats.index, stats["mean"], yerr=stats["std"], marker="o", label=f"Chip {chip}")
plt.xlabel("Nominal temperature (deg C)")
plt.ylabel("Input-referred offset (uV)")
plt.legend()
plt.tight_layout()
plt.show()
```

## 整理规则与核验

六段TDMS的全部6000个有效读数均保留。未做平均、平滑、异常点删除、温度筛选、插值或重采样；各段采集前按协议丢弃的3个读数不属于原始TDMS的1000点有效数据。

目标温度是分组标签。两轮均存在产品温度振荡及段内漂移，本CSV没有将低频温度记录插值成与DMM读数同步的实测温度。误差棒代表读数波动，不是均值置信区间。

已通过13类核验：6000行、6组、各1000点，无缺失或重复；30个来源文件SHA-256一致；CSV的原始电压、相对时间和输入等效值与TDMS及计算结果逐点回读完全一致。原始电压最大差值为0 V。

时间戳与TDMS采集起点加相对时间、两份原始逐点CSV及完成标志一致。六组均值和样本标准差与原报告一致；使用pandas的round_trip解析再次确认全部数值一致。

| Chip | 目标温度(℃) | 点数 | 输入均值(µV) | 样本标准差(µV) |
| --- | ---: | ---: | ---: | ---: |
| 1 | -40 | 1000 | +0.485804794 | 0.052543093 |
| 1 | 27 | 1000 | -0.286457399 | 0.114693086 |
| 1 | 125 | 1000 | -1.633651391 | 0.394586215 |
| 3 | -40 | 1000 | -0.144558602 | 0.220972225 |
| 3 | 27 | 1000 | -1.439493637 | 0.175106956 |
| 3 | 125 | 1000 | -2.324926613 | 0.233334437 |

CSV SHA-256：`998f6d4b55aa7ab33e4d9e9ca8a7a157094657b1611d718257768c6367bd82b3`。

[逐项核验及原始TDMS来源](verification_report.json)。

原始报告：[Chip 1](../../../tasks/Offset_Chip_1_Gain1001_20260918/README.md)、[Chip 3](../../../tasks/Offset_Chip_3_Gain1001_20260918/README.md)。原始运行证据保存在各任务的 `provenance/legacy_run/`。

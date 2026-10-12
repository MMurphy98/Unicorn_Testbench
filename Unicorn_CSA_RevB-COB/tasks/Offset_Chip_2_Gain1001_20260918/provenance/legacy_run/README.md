# Chip 2 三温度 offset：首点超量程中止

2026-09-18 21:02:29–21:10:21（Asia/Shanghai），Chip 2、Gain=1001测试在−40℃首点采集时中止。**有效电压读数为0，三温度测试未完成。**

## 中止原因

DMM配置读回通过：前端子、固定100 mV、10 NPLC、AUTO输入阻抗、Auto Zero及50 Hz同步开启；自动量程、内部平均、REL关闭。
等待2秒后，3个丢弃读数均返回超量程/无效值；第一个计划保存的读数为`9.9e37 V`，触发无效/超量程保护。该值不作为实际电压或输入等效offset使用。

```text
RuntimeError: Reading 1 is invalid or overrange: np.float64(9.9e+37) V on the 0.1 V range.
```

目前只确认固定100 mV量程下无法取得有效读数，实际输出电压及现场原因尚未确定。未据此推测供电、trim或芯片故障。

## 已执行与最终状态

- 启动前受控停止27℃常温运行，再进入−40℃产品控温；流量设定6 SCFM。
- 首次进入−40℃±1℃耗时162.141秒，随后固定等待300.094秒。等待期间产品温度-41.5～-38.4℃，越界93/301个样本；流程不等于稳定性通过。
- DMM失败标志已保存；主进程和DMM进程退出码均为1。没有进入27℃和125℃，没有自动改量程或续测。
- 程序于21:10:21确认热流仪停止；21:11:03独立只读复查仍为停止、R107=60（6 SCFM），当时产品温度-12.1℃。
- 独立复查DMM仍为DCV、前端子、固定100 mV、10 NPLC、AUTO输入阻抗；复查没有发起新的电压采样。
- 共保留474条温度记录、8580次热流仪通信（失败0次），17项中止处理及证据核验通过。

没有有效电压数据，因此未生成有效TDMS、逐点结果CSV、offset均值或温漂斜率；`partial_readings.csv`只有表头。原计划的3000点及46项完整测试验收没有达成。

## 保留文件

- [总运行记录](summary.json)、[失败标志](dmm/stage_01/dmm_done.json)、[DMM完整日志](dmm/stage_01/worker.log)、[采集请求](dmm/stage_01/dmm_request.json)。
- [部分读数文件（0点）](dmm/stage_01/partial_readings.csv)、[温度CSV](temperature.csv)、[温度曲线](temperature_curve.png)、[Modbus通信](wire.jsonl)、[事件日志](events.jsonl)。
- [停机及DMM配置复查](postflight.json)、[进程退出结果](process_result.json)、[中止核验](abort_verification.json)、[执行环境](execution_context.json)、[代码快照](code_snapshot)。

本目录已准备的`verify_saved_data.py`及`write_report.py`用于三点全部完成后的核验与报告，本次中止后未运行它们；本记录由`record_abort.py`生成。

## 后续处理

先确认Chip 2的现场接线、输入短接/offset测试状态、供电与输出电压。若要单独扩大量程定位输出电压，应作为另一次诊断记录；不能将诊断读数混入本次固定100 mV测试。
重新开始正式三温度测试时使用新的运行目录，保留本次中止证据。

# OPA189 历史噪声

`data/processed/formal_test/` 保存已提交的四条件频谱 MAT、两份 CSV 与两张 PNG；`results/` 保存原正式输出。本机缺少完整原始时域波形，归档预留路径为 `data/raw/formal_test/`，不要创建空的 `formal_test` 文件夹冒充完整数据。

本目录现只保留历史处理后基准和结果，原 MATLAB 重放与 Welch 分析入口及其源码快照已移除。PNG 和 CSV 可直接查看；删除代码前的四条件频谱重放验证保存在 `../verification_20261012.json`。重新分析原始波形或更改频谱参数仍需要补齐原始数据并提供相应处理代码。

处理后 MAT 的原始 SHA-256 为 `906e903236bb4b1def94b291522ae9a45c33120b9b843d75d5735c0bfa9c1910`，迁移保持字节不变。其历史“原始波形已省略”元数据中的旧说明路径保留为档案文字，当前归档要求如下。

完整原始归档应包含四个条件目录 `pm3v_no_shield`、`pm3v_with_shield`、`pm18v_no_shield`、`pm18v_with_shield`，每条件 `run_01` 至 `run_10` 各一份 InstrumentStudio Waveform Data CSV，并随附 Measurements CSV/Panel Configuration JSON。原采集配置为 CH0、50 kS/s、977436 点。

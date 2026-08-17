# Generated results

此目录用于本地生成的图表、日志和中间结果，除本说明外均被 `.gitignore` 忽略。需要进入版本控制的关键
指标和结论应整理到 `docs/test-reports/`；确需提交的小型最终产物应在 PR 中说明原因。

OPA189 正式入口生成：

- `opa189_four_condition_analysis.mat`
- `opa189_four_condition_summary.csv`
- `opa189_four_condition_run_summary.csv`
- `opa189_four_condition_0p1_to_100hz.png`
- `opa189_with_shield_voltage_comparison_0p1_to_100hz.png`

没有本地原始波形时，同一入口会从 `data/processed/opa189/formal_test/` 复写上述产物；这些文件仍然
属于本地生成结果，不进入 Git。仓库中随任务提交的参考 CSV、PNG 和频谱 MAT 位于 `data/processed/`。

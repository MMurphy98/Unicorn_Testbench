# Processed data

此目录保存可以进入 Git 的小型处理结果。它们用于在没有大型原始波形时复现正式图表，并不替代
`data/raw/` 中的完整测量数据。

## T-20260814-01 OPA189

`opa189/formal_test/opa189_four_condition_analysis.mat` 来自四种条件各十次原始波形的正式 Welch
分析，保存每次及每条件的 PSD/ASD、汇总表和分析元数据，不包含时域电压采样。MAT 文件 SHA-256：

```text
906E903236BB4B1DEF94B291522AE9A45C33120B9B843D75D5735C0BFA9C1910
```

同目录的两份 CSV 是条件和逐次汇总，两张 PNG 是本次提交时的参考输出。运行
`runOpa189NoiseAnalysis()` 时，如果本地没有 `data/raw/opa189/formal_test/`，入口会读取该 MAT 并
重新生成 `results/opa189/` 下的五项产物。此路径只验证处理后数据到图表的可复现性；若要更改
去趋势、Welch 段长、窗函数或重叠比例，必须下载原始波形并重新运行完整分析。

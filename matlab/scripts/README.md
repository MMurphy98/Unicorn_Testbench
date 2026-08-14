# Scripts

在此目录放置任务级分析入口。脚本应能从明确的数据链接/本地数据路径开始，调用 `matlab/src/` 中的函数，
并将生成结果写入仓库根目录的 `results/`。

`runOpa189NoiseAnalysis.m` 默认读取 `data/raw/opa189/formal_test/`，也可显式传入本机正式数据目录和
输出目录，便于在原始数据不进入 Git 的情况下复现分析。

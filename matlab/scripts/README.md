# Scripts

在此目录放置任务级分析入口。脚本应能从明确的数据链接/本地数据路径开始，调用 `matlab/src/` 中的函数，
并将生成结果写入仓库根目录的 `results/`。

`runOpa189NoiseAnalysis.m` 优先读取 `data/raw/opa189/formal_test/` 并执行完整 Welch 分析；默认
原始目录不存在时，自动读取 `data/processed/opa189/formal_test/` 的已提交频谱结果并重新生成正式
CSV 和图片。也可显式传入本机正式数据目录和输出目录。离线复图与原始波形复算是两种不同能力，
入口会在命令窗口明确打印当前使用的路径。

# Scripts

在此目录放置任务级分析入口。脚本应能从明确的数据链接/本地数据路径开始，调用 `matlab/src/` 中的函数，
并将生成结果写入仓库根目录的 `results/`。

`runOpa189NoiseAnalysis.m` 优先读取 `data/raw/opa189/formal_test/` 并执行完整 Welch 分析；默认
原始目录不存在时，自动读取 `data/processed/opa189/formal_test/` 的已提交频谱结果并重新生成正式
CSV 和图片。也可显式传入本机正式数据目录和输出目录。离线复图与原始波形复算是两种不同能力，
入口会在命令窗口明确打印当前使用的路径。
`runDutNoiseAnalysis.m` 默认处理仓库同级 `Chip_Benchmark/data/DUT_noise/` 下 COB 1--3 的三档
`Ib2 = Ib3 = 1/2/4 uA` 数据，每条件严格要求 `run_01` 至 `run_10`。每份取前 900,000 点，以
50 kS/s、900,000 点周期 Hann 窗计算单边 PSD；十份 PSD 在功率域平均后开方，再除以 1001，输出
输入等效 ASD。完整数据写入 `results/DUT_noise/`，可提交的小型复图数据写入 `data/processed/`。

`dut.replayProcessedCampaign(processedDir)` 只读取小型 `dut_noise_plot_data.mat` 并重新生成按 COB、按
偏置电流组织的两张 PNG，不依赖原始波形。

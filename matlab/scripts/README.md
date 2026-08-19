# Scripts

在此目录放置任务级分析入口。脚本应能从明确的数据链接/本地数据路径开始，调用 `matlab/src/` 中的函数，
并将生成结果写入仓库根目录的 `results/`。

`runOpa189NoiseAnalysis.m` 优先读取 `data/raw/opa189/formal_test/` 并执行完整 Welch 分析；默认
原始目录不存在时，自动读取 `data/processed/opa189/formal_test/` 的已提交频谱结果并重新生成正式
CSV 和图片。也可显式传入本机正式数据目录和输出目录。离线复图与原始波形复算是两种不同能力，
入口会在命令窗口明确打印当前使用的路径。

`runPxi5922NoiseAnalysis.m` 默认读取 2026-08-19 Unicorn COB RevA 的十份 AC 耦合 PXI-5922 波形，每份取前
900,000 点，以 50 kS/s 和 900,000 点周期 Hann 窗计算单边 PSD。十份 PSD 先平均，再开方得到最终
ASD；不生成逐次频谱图，只将最终双对数 ASD 图的 PNG 和 MATLAB FIG、CSV 及完整 MAT 数据写入
`results/PXI-5922/`。
这组结果对应 Unicorn COB RevA DUT、1001 倍电压增益、PXI-5922 采集和 AC 耦合。脚本输出的是
1001 倍增益后的输出端 ASD，不自动换算为输入等效 ASD。

`runPxi5922DcNoiseAnalysis.m` 对 `run_02` 中的十份 DC 耦合波形执行完全相同的处理，并将同名的
CSV、MAT、PNG 和 MATLAB FIG 写入独立的 `results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_02/`。
图标题和 MAT 元数据均记录为 DC coupling；结果同样是 1001 倍增益后的输出端 ASD。

`runPxi5922FloatingInputNoiseAnalysis.m` 对 `run_03` 中十份 PXI-5922 floating-input 波形执行相同
分析，并将结果写入 `results/PXI-5922/2026-08-19_Unicorn_COB_RevA_run_03/`。该组设置为 CH0、
DC 耦合、1 MOhm 输入、1 倍 probe、10 mV/div，不连接 DUT 或 1001 倍放大链路；输出 ASD 用于描述
PXI-5922 在 floating-input 条件下的综合噪声底，不进行增益换算。

`plotPxi5922AcDcComparison.m` 只加载 `run_01` 和 `run_02` 已保存的 `average_noise_asd.mat`，不读取
原始 CSV、不重新计算频谱。入口校验两组频率轴和采集参数后，将两组输出端 ASD 除以 1001，并从
V/sqrt(Hz) 换算为 nV/sqrt(Hz)，再将 AC/DC 输入等效噪声绘制在同一双对数坐标系中并添加 legend；
PNG 和 MATLAB FIG 写入
`results/PXI-5922/2026-08-19_Unicorn_COB_RevA_ac_dc_comparison/`。

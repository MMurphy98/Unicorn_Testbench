# Source

在此目录放置可复用 MATLAB 函数和算法。建议一个公开函数对应一个 `.m` 文件，并为输入、输出、单位和
边界条件编写帮助文本。

通用函数：

- `noiseSpectrum.m`：以噪声时域波形、采样率和 Welch/FFT 点数为输入，返回单边 PSD 和频率轴；
  可选绘制 PSD 与 ASD。

`+opa189/` 包含 T-20260814-01 的完整实现：

- `analyzeWaveform.m`：原始时域波形的 Welch PSD 与输入等效 ASD。
- `processFormalComparison.m`：四条件各十次 PSD 平均、指标汇总和绘图。
- `defaultConfig.m`：采样率、增益、窗长、重叠率和分析频段。
- `private/`：InstrumentStudio CSV 导入与正式图形导出。

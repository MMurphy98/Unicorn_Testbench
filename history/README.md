# 历史测试

这里集中保存历史 RevA、PXI-5922 和 OPA189 数据与已有结果。MATLAB 源码、Live Script、专用验证脚本及其源码快照已按要求移除，MAT/FIG 等历史数据和 JSON 记录保留。

- [RevA](RevA/README.md)：四组 TDMS 目录、全记录及 Welch 历史结果、屏蔽/电流比较和 Gain101 结果。
- [PXI-5922](PXI-5922/README.md)：AC、DC 和 floating-input 三种条件，以及已保存的结果。
- [OPA189](OPA189/README.md)：四条件处理后基准、正式图表与原始波形归档要求。

`migration_20261012.json` 记录搬迁时的原路径、新路径、字节数及 SHA-256；`verification_20261012.json` 保存删除代码前的数值验证证据。这些 JSON 和 `provenance/root_layout_20261012/` 中的旧文档属于历史记录，可能提及已移除的源码或旧路径，当前保留内容以各组 README 为准。

原始波形与大型派生产物仍是本地文件；目录重排不意味着它们已进入 Git。OPA189 已提交的处理后基准仍可查看，但完整原始波形缺失。本目录现在提供历史数据和结果归档，没有历史 MATLAB 重算入口。

最新芯片的现场采集和离线处理继续使用 [RevB Python 主线](../Unicorn_CSA_RevB-COB/README.md)，现场和后处理入口不受本次删除影响。

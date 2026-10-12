# FPGA 历史附属文件

- `generated_sources/pll_altpll.v`：原 `db/` 中的生成 Verilog，原字节保留；当前 `.qip` 不直接引用此文件。
- `source_backups/Unicorn_CAS_DE2_115.v.bak`：旧顶层源码备份，原字节保留。
- `programmer/Unicorn_CSA_DE2_115.cdf`：历史 Programmer 链配置，包含原 Windows 机器的绝对路径及无日期 `.sof` 名称。

当前可编译工程仍使用根目录 `.qpf`、`.qsf`、`src/` 和 `ip/`。归档文件供历史查阅，现场固件选择见
[FPGA 说明](../README.md)。移动记录和哈希见 [迁移清单](../migration_20261012.json)。

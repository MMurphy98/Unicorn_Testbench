# Quartus 本地编译输出

未改动的 `.qsf` 仍将新编译输出写入本目录。自动生成的文件不提交 Git。

原来的三份带日期 `.sof` 已原样归入 [firmware](../firmware/index.json)，历史编译报告在
[reports/legacy_build_20260819](../reports/legacy_build_20260819/README.md)。迁移路径与 SHA-256 见
[迁移清单](../migration_20261012.json)。原始源码和固件内容未改变。

现场烧录使用明确指定的历史固件，不根据本目录的无日期输出名自动选择版本。

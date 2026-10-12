# 个人维护与交付

仓库由用户本人维护。当前保留的测试结果均由用户本人完成；早期委托安排不代表已取得可用于当前基准的测试交付。
旧协作规则及文件由用户另行备份，仓库中的旧快照已删除。

## 记录与结果

- [测试安排](../测试安排.md) 维护当前待办、优先级、状态及待补事项。
- [测试日志](../测试日志.md) 按日期记录本人实际执行的测试、结论、异常及整理工作。
- 详细条件、数值和限制保存在 `docs/test-reports/` 与对应任务结果目录，安排和日志引用这些证据。
- 完成采集、数据完整、实验指标通过是不同状态。失败测试保留原因和证据，不能写成有效测量结果。

任务编号可以继续用于串联历史记录；新代码整理、维护或分析工作不要求先发布委托任务。

## 分支与 main

个人维护可以使用工作分支，也可以直接维护 main。Pull Request 用于需要集中查看差异或讨论的工作，
是可选方式，不要求维护者指定本人审核或取得本人 approval。

本次全面整理先在当前工作分支形成可审查、可复现的基准；发布 main 是之后单独执行的步骤。
发布前保存原 main 的提交位置，刷新远端状态，核对待提交内容和数据归档，并记录验证结果。
使用保留历史的合并或快进方式；不因目录整理重写 Git 历史。

仓库内 hook 和 CI 不配置远端分支保护。发布 main 前需要单独核对 GitHub ruleset/branch protection，
确保它不再要求旧委托审批或已移除的 policy 检查。本轮文件整理不修改远端设置。

## 普通检查

安装本地 hooks 和 Git LFS 支持：

```powershell
git lfs install
git config core.hooksPath .githooks
```

`pre-commit` 对所有分支执行 `git diff --cached --check`，检查空白错误和冲突标记。
四个标准 Git LFS hooks 继续处理对象下载、检出及推送。

`Offline checks` 在 push、可选 PR 或手动触发时执行 Python 语法、现行文档链接检查及三组离线回归测试。
它使用模拟仪器或生成的数据，不连接现场设备，不要求下载全部 TDMS。

在安装后处理依赖的 Python 环境中，从仓库根目录执行：

```bash
python -m pip install -r Unicorn_CSA_RevB-COB/postprocess/requirements-notebook.txt 'PyVISA==1.16.2' 'npTDMS==1.11.0'
python -m unittest discover -s scripts -p 'test_*.py' -v
python -m unittest discover -s Unicorn_CSA_RevB-COB/field -p 'test_*.py' -v
python -m unittest discover -s Unicorn_CSA_RevB-COB/postprocess -p 'test_*.py' -v
```

旧 DMM 模拟测试还需要 Python 接口包 PyVISA，但不需要 NI-VISA 驱动或仪器。
测试依赖对齐现场采集代码：worker 在模拟模式也检查 `npTDMS==1.11.0`，因此回归测试需要显式固定此版本。
MATLAB 代码和测试已移除。现场控制改动在 Windows 设备环境验证；
报告实际执行范围，不把离线回归写成现场验证。

## 数据与历史实现

正式任务记录来源、单位、处理参数、代码版本及原始文件 SHA-256。
TDMS、逐次 NPZ、完整分辨率频谱和机器缓存留在独立数据存储；Git 保存结果摘要、图表、代码和来源清单。
已有用于回归的参考文件按原规则保留。

复制到另一台电脑时，按现场或后处理入口说明复制完整任务数据；只有 Git 检出不等于取得全部原始数据。
保留的历史源码、固件和报告不因归类而改写测量结论或数值。

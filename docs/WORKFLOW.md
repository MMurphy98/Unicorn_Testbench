# 协作与交付规则

## 角色

- 仓库负责人 `@MMurphy98`：发布任务、维护验收标准、审核 PR、决定是否合并到 `main`。
- 执行人：建立任务分支、每日推送、维护测试代码与按日期记录的测试结论、根据审核意见修改。

执行人不得自行批准或合并自己的 PR。`main` 只接受经仓库负责人批准的 PR。

## 标准流程

1. 负责人在 `docs/TODO.md` 发布任务并分配唯一编号 `T-YYYYMMDD-NN`。
2. 执行人同步 `main`，建立 `task/T-YYYYMMDD-NN-short-name` 分支。
3. 分析函数写入 `matlab/src/`，可重复执行入口写入 `matlab/scripts/`，自动化测试写入 `matlab/tests/`。
4. 执行人每日推送分支。当天有测试活动时，新增或更新
   `docs/test-reports/YYYY/MM/YYYY-MM-DD-T-YYYYMMDD-NN.md`。
5. 达到验收标准后，执行人按 PR 模板发起 PR，并请求 `@MMurphy98` 审核。
6. 自动检查通过且负责人批准后，仅由负责人合并。合并策略建议使用 Squash merge。

## 分支与提交

- 禁止直接在 `main` 提交或推送。
- 每个任务使用独立分支，不在同一 PR 混入无关修改。
- 分支命名：`task/T-YYYYMMDD-NN-short-name`；修复分支可用
  `fix/T-YYYYMMDD-NN-short-name`。
- 提交信息建议：`T-YYYYMMDD-NN: 动词开头的简短说明`。
- 每日至少在有实际进展时推送一次；未完成代码也应保持可运行或明确标注限制。

## PR 必填内容

每个进入 `main` 的 PR 必须说明：

1. 测试内容：对象、范围、条件、环境和验收标准。
2. 测试结果：通过状态、关键指标、异常和结论文件路径。
3. 测试代码：仓库相对路径和可复现命令。
4. 测试原始数据链接：稳定的 HTTPS 地址和访问权限；无原始数据时写明原因。

PR 标题使用 `[T-YYYYMMDD-NN] 简要说明`。模板章节不能为空，检查清单必须全部勾选。

## 测试结论记录

- 一个任务同一天使用一个文件；同日多次测试追加到同一文件并标注时间或运行编号。
- 结论必须绑定 Git commit、MATLAB 版本、测试代码路径、输入数据链接和运行命令。
- 失败结果同样记录，不覆盖或删除历史失败原因。
- 原始数据和生成结果默认不入库；仓库只提交可复现代码、小型配置和必要摘要。

## GitHub 强制设置

推送到 GitHub 后，由仓库负责人在 `Settings > Branches > Branch protection rules` 为 `main`
启用以下设置：

- Require a pull request before merging。
- Require approvals：`1`。
- Require review from Code Owners。
- Dismiss stale pull request approvals when new commits are pushed。
- Require status checks to pass：选择 `Validate PR title and description`。
- Require conversation resolution before merging。
- Do not allow bypassing the above settings，并限制可推送人员为仓库负责人。
- 禁止 force push 和删除 `main`。

`.github/CODEOWNERS` 已将所有路径指定给 `@MMurphy98`。GitHub Free 的私有仓库可能不支持完整的
分支保护能力；若相关选项不可用，需要调整仓库可见性或 GitHub 套餐。

## 本地保护

仓库使用版本化 hook 阻止直接在 `main` / `master` 提交。克隆后执行：

```powershell
git config core.hooksPath .githooks
```

本地 hook 可以被绕过，因此 GitHub 分支保护才是最终强制边界。

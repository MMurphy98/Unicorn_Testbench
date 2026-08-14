# 协作与交付规则

## 角色

- 仓库负责人 `@MMurphy98`：发布任务、维护验收标准、审核 PR、决定是否合并到 `main`。
- 执行人：建立任务分支、每日推送、维护测试代码和按日期记录的测试结论、根据审核意见修改。

执行人不得自行批准自己的 PR。所有交付必须取得仓库负责人的 CODEOWNER approval。

## 两类提交

### 任务发布：不需要 PR

根目录 `测试安排.md` 是唯一任务源。仓库负责人可以在 `main` 直接修改并提交该文件，
用于发布任务、调整优先级、补充验收标准或更新任务状态。

一次任务发布提交只能修改这一个文件：

```powershell
git switch main
git pull --ff-only
# 编辑根目录 测试安排.md
git add "测试安排.md"
git commit -m "task: publish T-YYYYMMDD-NN"
git push origin main
```

本地 hook 会检查暂存区；如果同时修改其他文件，提交会被拒绝。

### 测试交付：必须 PR

以下内容不得直接提交到 `main`：

- `matlab/src/` 中的分析函数和算法。
- `matlab/scripts/` 中的任务分析入口。
- `matlab/tests/` 中的自动化测试。
- `docs/test-reports/` 中按日期记录的测试结论。
- 配置、工作流、说明文档以及任务安排文件之外的所有内容。

标准交付流程：

1. 从 `main` 创建 `task/T-YYYYMMDD-NN-short-name` 分支。
2. 每日有实际进展时推送代码；当天有测试活动时更新按日期命名的测试结论。
3. 运行相关 MATLAB 测试，记录准确的命令、环境和结果。
4. 使用 PR 模板提交交付，并请求 `@MMurphy98` 审核。
5. 自动检查通过且负责人批准后，方可合并到 `main`。

## 分支与提交

- 一个任务使用一个分支，不在同一 PR 混入无关修改。
- 分支命名：`task/T-YYYYMMDD-NN-short-name`；修复分支可用
  `fix/T-YYYYMMDD-NN-short-name`。
- 交付提交信息：`T-YYYYMMDD-NN: 动词开头的简短说明`。
- 任务发布提交信息：`task: publish T-YYYYMMDD-NN`。
- 推荐使用 Squash merge 保持 `main` 历史简洁。

## PR 必填内容

每个交付 PR 必须说明：

1. 测试内容：对象、范围、条件、环境和验收标准。
2. 测试结果：通过状态、关键指标、异常和结论文件路径。
3. 测试代码：仓库相对路径和可复现命令。
4. 测试原始数据链接：稳定的 HTTPS 地址和访问权限；无原始数据时写明原因。

PR 标题使用 `[T-YYYYMMDD-NN] 简要说明`。模板章节不能为空，检查清单必须全部勾选。

## 测试结论记录

- 文件命名：`docs/test-reports/YYYY/MM/YYYY-MM-DD-T-YYYYMMDD-NN.md`。
- 一个任务同一天使用一个文件；同日多次运行增加独立运行记录。
- 结论绑定 Git commit、MATLAB 版本、测试代码路径、输入数据链接和运行命令。
- 失败结果同样记录，不覆盖或删除历史失败原因。
- 原始数据和生成结果默认不入库；仓库提交可复现代码、小型配置和必要摘要。
- 缺少的信息统一写为 `<TBD>`，不根据上下文猜测。

## GitHub 保护规则

`main` 启用以下规则：

- 交付变更必须先发起 Pull Request。
- 至少 1 个 approval，并强制 CODEOWNER review。
- 新提交会使旧 approval 失效。
- PR 描述检查和会话解决后方可合并。
- 禁止 force push 和删除 `main`。
- 仓库管理员 `@MMurphy98` 保留绕过权限，只用于直接更新任务安排文件。

GitHub 的分支保护无法将管理员绕过权限限制到某一个文件。因此仓库使用三层约束：

1. 本地 `.githooks/pre-commit` 仅放行单独修改任务安排文件。
2. `main` push 审计 Action 检查无关联 PR 的推送是否只修改任务安排文件。
3. CODEOWNERS 和 PR 保护确保其他成员的交付必须由 `@MMurphy98` 批准。

审计 Action 能发现违规的管理员直推，但 GitHub 执行 Action 时提交已经发生；它不能替代负责人对
管理员绕过权限的正确使用。

## 本地保护

克隆仓库后执行：

```powershell
git config core.hooksPath .githooks
```

本地 hook 可以被绕过，GitHub 分支保护和审计记录是远端补充边界。

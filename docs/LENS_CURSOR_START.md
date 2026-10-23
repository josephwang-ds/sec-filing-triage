# Lens × Cursor：从这里开始

日期：2026-10-23（Asia/Shanghai）。这是本轮有效任务入口；旧 `CURSOR_TASKS.md` 的批次和状态不能作为当前基线。

## 分工与本轮目标

- Joseph：产品方向与实际使用反馈。
- ChatGPT / Codex：规划、范围与架构取舍、代码审查、最终验收和上线协调。
- Cursor：按本文和关联文档完成实现、测试、可复现演示，提交可审查的分支。
- 同一时间只有 Cursor 修改本轮功能源码；Codex 不在另一份 checkout 同时实现同一功能。
- 本轮先完成 **A0 + A1**：刷新可靠性和新闻事件的最小端到端实现。不要一次实现整张路线图，也不要只交方案不写代码。

先读：
1. `docs/LENS_EVENTS_PLAN.md`：产品与工程约束、频率、阶段范围。
2. `docs/LENS_EVENTS_ACCEPTANCE.md`：验收矩阵与故障演练。
3. 当前实际源码、相关测试、`.github/workflows/*.yml`。源码和线上验证优先于旧部署文档。

## 工作区与基线

- GitHub：`josephwang-ds/sec-filing-triage`。
- Joseph 的既有 Mac checkout：`/Users/josephwang/dev/sec-filing-triage`；先验证目录和 origin。不要使用 `ai-demo-platform` 或旧 `ai-quant-signal-platform`。
- 规划核对时远端 main：`b81ccc1ec551a2d0a9eca91da2400634e1a4726b`（刷新回执）；最近功能提交：`03d4a53db68f58cc45db1db8fbed43c68383b980`。
- 该功能版本的 CI：776 tests passed，另有 locked-environment 和 leakage-audit 通过；这不是新代码免测的依据。
- 当前已上线：正式财报同比、SIC 样本比较、SPY/QQQ 历史比较、带引用财报 AI 问答。
- 站点：`https://lens.josephjwang.com`；现有 Vercel 项目：`company-lens-josephjwang`。不要新建替代站点或切换域名。

启动动作：

```bash
pwd
git remote -v
git status --short
git branch --show-current
git log -5 --oneline
git fetch origin
```

先比较本地与 origin/main。不得执行 reset --hard、clean、丢弃修改或覆盖旧未推送提交。旧 checkout 曾有独立的周三调度提交；如仍存在，要单独识别，不能误当成本轮已批准配置。

干净 checkout 从最新 origin/main 新建 `feat/lens-events-a1`；已有同名分支则检查后复用。若本地有未提交工作或分叉，保留原 checkout，在独立 worktree 从最新 origin/main 开工，并报告路径。不要自动 stash 用户工作或移动原文件夹。

若任务文档只在 origin/main：先用 `git show origin/main:docs/LENS_CURSOR_START.md` 读取，无须覆盖本地同名文件。运行相关命令时不要输出环境变量值、凭据、完整 .env 或认证 URL。

## 立即开始的工作顺序

1. 建立当前源码地图，列出真实刷新入口、缓存位置、公开数据边界、AI evidence 构建位置。
2. A0：完成 `docs/LENS_EVENTS_STATUS.md` 的基线/基础设施表和一个明确的存储、调度选择；只核对可用性和配置名称，不读取秘密值。没有凭据的部分列出精确阻塞项，继续完成不依赖凭据的工作。
3. A1：实现独立 news/SEC 调度策略、持久检查点与增量补拉、last-good 发布、新闻只刷新数据不重新部署整站；在公司页完成真实新闻事件卡片与新鲜度状态。实现对应的版本化 AI 证据路径后，才启用新闻事件的 AI 入口。
4. A1 不要求解析所有公司的业绩附件，不接一致预期，不做交易执行；这些属于 A2/B。
5. 按验收矩阵测试。先跑受影响测试；修改稳定后再跑仓库必需全量检查，避免每改文案重跑昂贵模型测试。
6. 自查 diff 和密钥/生成物边界，提交功能分支，推送并创建 draft PR（若可用）；更新状态文档。不要自动合并 main、启用新生产定时器或部署正式站点；由 Codex 审查协调，避免两个执行者同时发布。

第 6 点是本轮协作交付顺序，不要求再向 Joseph 逐项索要普通代码编辑许可。已有授权范围内自主完成；遇到账户登录/新增付费服务等真实阻塞时，只报告具体缺项。

## 给 Codex 的交接格式

在 `docs/LENS_EVENTS_STATUS.md` 记录，并在 Cursor 最后一条回复中提供：

- checkout 路径、分支、基线 SHA、最终 SHA、PR 链接；没有推送必须明确说明。
- A0/A1 已完成、未完成、外部配置阻塞；不得把 mocked 测试写成生产验证。
- 简短变更摘要、文件列表、准确测试命令与结果。
- 确定的频率表、实际使用的时区、持久存储、触发器和独立监控方案。
- 冷启动/空缓存/重复触发/断网/补拉演练结果；真实数据样例与桌面/移动端中英文截图。
- 生产是否仍为旧版；本轮新增但尚未启用的配置名称（不含值）。

若 GitHub 推送确实不可用，导出包含新增源码和测试的完整补丁，验证能应用于明确的基线 SHA；排除密钥、缓存、依赖和个人研究笔记。不要用“改了哪些文件”的摘要代替可审查的代码。

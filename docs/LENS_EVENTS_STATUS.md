# Lens Events — 协作状态与验收证据

最后更新：2026-10-23（Asia/Shanghai）。维护者：Cursor 实现、Codex 验收。

## 当前状态

- planning_ready: yes
- implementation_started: yes
- code_ready: yes（入口、持久检查点、指针发布、动态 Ask 证据、预算和监控适配已接通；本地测试通过）
- mock_integration: yes（内存 Blob 与假执行器；不是真实存储）
- staging_verified: no
- production_enabled: no
- reliability_verified: no
- 当前生产仍为已有财报/历史/AI 版本。本分支没有合并 main，没有部署 `lens.josephjwang.com`，没有启用新的生产 cron。
- 实现范围：A0 + A1。A2/B 未做。

## 基线与交付

| 项目 | 值 |
|---|---|
| checkout / worktree | `/Users/josephwang/dev/sec-filing-triage-feat-lens-events-a1` |
| 保留的原 checkout | `/Users/josephwang/dev/sec-filing-triage` 仍在 `main`，未提交工作未动。`/Users/josephwang/dev/ai-quant-signal-platform` 仍在 `claude/ai-quant-project-missing-lxcwzp`，未提交工作未动 |
| origin | `https://github.com/josephwang-ds/sec-filing-triage.git` |
| 分支 | `feat/lens-events-a1` |
| 基线 SHA | `950f9ada1f82e4394ae7bedf39107c1c8b526e30`（`origin/main`：docs: plan Lens event research and Cursor implementation handoff） |
| 最终 SHA | 见本文件提交后的 PR；实现提交在该基线之上 |
| 未纳入的本地提交 | `23b01c1`「Refresh on Wednesday too…」只存在于 `/Users/josephwang/dev/sec-filing-triage` 的本地 `main`，不在 `origin/main`，本轮不当作已批准调度 |
| PR | draft，链接见 Cursor 交接 |
| 生产变更 | 无 |

## A0 基础设施选择

选定一套后端，不并行做第二套。

| 能力 | 观察证据 | 选择 / 缺口 |
|---|---|---|
| Vercel 项目 | GitHub secret 名称存在：`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`。项目名仍是 `company-lens-josephjwang`。未读取值，未查询套餐账单 | 不升级套餐。页面与 Ask 仍走现有 Vercel 函数。Hobby cron 不承担高频任务 |
| 持久存储 | 仓库里没有已配置的对象存储或数据库。Actions cache 只恢复 SEC/价格缓存 | 目标是 Vercel Blob 私有对象：不可变版本 + `x-if-match` 序号栅栏。配置名 `BLOB_READ_WRITE_TOKEN`。GitHub secrets 中没有该名称。本地与测试使用文件检查点，不把它当成生产库 |
| 主任务执行器 | `.github/workflows/refresh.yml` 仍是周六 `20 7 * * 6`（07:20 UTC）全链路并部署 | 新任务在 `.github/workflows/events-refresh.yml`，只有 `workflow_dispatch`，不构建页面、不部署。生产 cron 未改 |
| 独立监控 / 补跑 | `.github/workflows/events-monitor.yml` 也只有手动触发。`EVENTS_RERUN_TOKEN` 不在 secrets 里 | 独立唤醒未配置。监控可以告警并打印恢复入口，不会自称已经自动修好 |
| 新闻来源 | `FINNHUB_API_KEY` 不在 GitHub secrets，本机环境也未设置。未发真实请求 | 代码接了 Finnhub company-news。没有 key 时状态是 `disabled`，不是「没有新闻」 |
| SEC 身份 | secret 名称 `EDGAR_USER_AGENT` 存在（2026-10-20）。未读取值，未打 SEC | 索引适配器只拉 submissions 的 recent 列表，不下载正文。本轮没有做真实索引演练 |
| 月请求估算 | `monthly_request_estimate(ordinary_companies=174)`，2026-10，每个到期点 1 次请求、不含重试 | 新闻 27,708；SEC 索引 15,008；健康检查 2,975。这不是账单。高频组 20 家。未读任何发票 |

存储与调度结论：GitHub Actions 跑短任务；水位与已发布版本以 Vercel Blob 为持久层；Vercel 只读已发布的公开投影和同版本 AI 证据。Blob token 缺失，所以生产持久层未接通。文件检查点只用于测试、本地演练和一次 runner 内的任务。

## 频率、时区、触发器

内部时间是 UTC。调度用 `America/New_York`（含夏令时）。页面同时显示纽约和上海，日期精度为「只有日期」时不换算成午夜。

| 数据集 | 高频组 | 其他 | 本轮是否在生产跑 |
|---|---|---|---|
| 新闻 | 工作日 04:00–20:00 每 30 分钟；非活跃或休市每 2 小时；周末每 4 小时；已确认事件前后 2 小时可 15 分钟，到期恢复 | 普通组每天 08:00 与 18:00。配额不足时降到这档并标明 | 否 |
| SEC 索引 | 活跃窗口每 2 小时；其余每 6 小时；已确认发布后最多 6 小时、每 30 分钟。估计日期不加速 | 每天两次 | 否 |
| 行情 | 该交易日收盘后 2 小时，含 13:00 提前收盘。非交易日不因为「又过了一天」报过期 | 同一规则 | 仍在周六全链路 |
| 正式财报 facts | 每天 06:30 纽约，另加新 10-Q/10-K | 同一规则 | 仍在周六全链路 |
| 未来日期 | 每天 06:00；已确认且 48 小时内改为每 6 小时 | 同一规则 | 未接数据源。页面明确写没有已确认未来日期 |
| 健康 | 每 15 分钟，读任务时间和覆盖水位 | 同一规则 | 手动 workflow，未定时 |

高频组（服务配置，不是浏览器自选）：AAPL、MSFT、NVDA、AMZN、GOOGL、META、TSLA、AVGO、JPM、V、UNH、XOM、LLY、JNJ、MA、COST、HD、PG、BAC、WMT。自选名单不会加入抓取目标。

冷启动：新闻 7 天，SEC 索引 90 天。恢复时从成功水位回退至少 24 小时，按来源窗口拆开。补不回的区间记 `coverage_gap`。失败不推进成功水位。

尚未启用、本轮新增的配置名（不含值）：`BLOB_READ_WRITE_TOKEN`、`EVENTS_RERUN_TOKEN`、`EVENTS_MONITOR_WEBHOOK`、`EVENTS_BLOB_MANIFEST_ETAG`。已有但本轮新闻路径用不到或未设置的名称：`FINNHUB_API_KEY`（GitHub 未配置）、`EDGAR_USER_AGENT`（名称存在，未用于本轮实拉）。

## 实施清单

- [x] A0 基线、选型和配置缺口
- [x] A1 分内容调度与时区策略
- [x] A1 持久状态 / 水位 / 幂等 / 原子发布
- [x] A1 增量补拉 / 失败降级 / 冷启动
- [x] A1 新闻事件卡片与独立数据读取
- [x] A1 事件 AI 同版本证据链路
- [x] A1 健康监控与补跑适配（未配置独立唤醒）
- [x] A1 中英文、移动端、原功能回归（本地）
- [x] A1 测试与 draft PR
- [ ] 真实 Finnhub / SEC / Blob 演练
- [ ] 生产定时器与 48 小时观测

## 2026-10-23 验收修复

Codex 复核 `2abce6c` 时，单测通过但入口没有形成闭环。这一轮改的是入口，不是把断言放宽。

| 项 | 实现 | mock 集成 | 真实 staging | 生产 | 48 小时 |
|---|---|---|---|---|---|
| 持久检查点恢复 | yes | yes：两个临时目录共用一个内存 Blob，第二轮从旧水位继续；读失败不覆盖旧检查点。新闻和 SEC 都在检查点里 | no | no | no |
| 指针原子发布 | yes | yes：stale etag 返回 412，读路径仍是 new；部分发布保留其他公司。官方 Blob put 使用 `x-api-version: 12`、默认不覆盖、`x-if-match` 条件替换。没有对本账号的真实 store 调用 | no | no | no |
| 动态 Ask 证据 | yes | yes：不重建函数，发布后 Ask 读到新版本，旧版本不混入。缺版本或读失败是 409 | no | no | no |
| 频率、重试、预算 | yes | yes：未到期跳过、跨 runner 预算累计、429 不提前重试、窗口中途超时不推进水位。生产入口使用 `time.sleep` | no | no | no |
| 监控与补跑 | yes | yes：空检查点不是健康；未配置不报已补跑；配置齐备时调用外部执行器并受冷却限制。GitHub workflow 不是独立唤醒 | no | no | no |

缺的配置名：`BLOB_READ_WRITE_TOKEN`、`FINNHUB_API_KEY`、`EVENTS_RERUN_URL`、`EVENTS_RERUN_TOKEN`。缺配置只说明真实演练还没做，不说明代码没接上。

真实演练（仍未执行）：配置上述名称后，手动 `workflow_dispatch` `events-refresh.yml`，确认 Blob 里出现 `lens-events/checkpoint.json` 和 `lens-events/public/manifest.json`，再用另一个空工作目录跑第二次，核对水位不是冷启动。然后打开公司页和 Ask，确认新 `event_version` 不需要重新部署。最后单独 dispatch `events-monitor.yml`，在刷新停摆后看健康状态变差。不要启用 schedule。

## 验收证据

环境说明：下面原表是第一轮的 mock/local 测试。持久恢复、原子发布、动态 Ask 和监控补跑以本节上面的「验收修复」为准；那些项目不能只凭第一轮单测写成通过。没有生产数据删除演练，没有真实模型请求，没有真实 Finnhub、SEC 或 Blob 调用。

命令：

```bash
ruff check src tests scripts
PYTHONPATH=src python -m pytest -q
```

结果：ruff 通过。pytest 全部通过（README 记录 804 tests；`tests/test_docs.py` 核对收集数）。解释器：`/Users/josephwang/dev/sec-filing-triage/.venv/bin/python`（3.12.14）。Node 可用，Ask / events 函数测试已执行。

| ID | 环境 / 测试 | 结果 | 说明 |
|---|---|---|---|
| A01 | 启动时记录两个 checkout | 通过 | 脏工作区保留。功能分支从 `origin/main` 的 worktree 开工。周三提交单独标出 |
| A02 | `tests/test_events_a1.py` 策略与 `policy.py` | 通过 | news/SEC/facts/prices/calendar/health 同一模块。UI 与健康检查读它 |
| A03 | 夏令时、周末、休市、提前收盘 | 通过 | 2026-03-08 切换；上海周一不等于纽约工作日；2025-11-28 13:00 收盘；周六有周五 bar 时行情不报过期 |
| A04 | 活跃窗口、确认事件、配额 | 通过 | 15 分钟和 30 分钟提升会到期。估计日期不加速。配额降到普通组时刻 |
| A05 | 20 家与自选 | 通过 | 自选 `ZZZZ` 不进入抓取列表 |
| A06 | 新 store 实例读取同一目录 | 通过 | 不要求 Mac 常开。页面读已发布版本 |
| A07 | 删掉旁边的 cache 目录 | 通过 | 检查点仍在。workflow 不用 Actions cache 当事件库 |
| A08 | 无历史时的 7 天窗口 | 通过 | `initialization` 为真。历史回填不挡这次发布 |
| A09 | 停在 7 天前的水位 | 通过 | 补拉起点早于「只查近 3 天」 |
| A10 | 来源最早只能看到 10 天，水位在 30 天前 | 通过 | `provider_lookback` 缺口，状态 `partial` |
| A11 | AAPL 成功、MSFT 失败 | 通过 | MSFT 旧版本和水位保留 |
| A12 | 429 Retry-After、401 不重试 | 通过 | 失败记录不含测试密钥 |
| A13 | 重复触发；旧 fence | 通过 | 不复制事件；旧 fence / 旧 lease 不能发布 |
| A14 | `crash_after=version` | 通过 | 候选文件在，current 仍是空。下一次运行可发布 |
| A15 | 同 URL 修订；相似标题不同公司 | 通过 | 修订保留两版。不同公司不合并 |
| A16 | 8 条新闻；另一次 `max_items=5` | 通过 | 默认不被 UI 的 5 条截断。截断记 `item_budget` 且不推进水位 |
| A17 | 第二次返回空列表 | 通过 | 检查时间前进，来源发布时间不变，状态 `no_new_events` |
| A18 | 只有 `date` | 通过 | `time_precision=date`，值是 `YYYY-MM-DD` |
| A19 | 标题里的 `<script>`、`javascript:` URL | 通过 | 页面转义。非 http(s) 链接不进 HTML。Ask 拒绝客户端证据 |
| A20 | `RefreshReport.redeployed is False`；workflow 无 deploy | 通过 | 卡片脚本读 `/api/events`。预览页不是生产站 |
| A21 | 无 feed 的公司页 | 通过 | 文案是不可用，不是「没有重要事件」。财报区块仍在事件区块之前 |
| A22 | `tests/test_events_api.py` | 通过 | 请求旧版本只拿到旧标题。缺失版本 409，不改用新版本 |
| A23 | 客户端 `evidence` / `source_url` | 通过 | 400 `client_evidence_rejected`。未知 event id 422 |
| A24 | `validate_grounded_explanation` | 通过 | 「will rise 40%」被拒绝。自动校验不能证明语义全部正确，测试文案写明了这一点 |
| A25 | 无模型 key 的事件提问 | 通过 | 400 `model_not_available`。卡片不依赖模型。刷新路径不调用模型 |
| A26 | 预览页桌面 / 390px、中英 | 通过 | 截图在 `docs/lens-events-preview/`。原始英文标题单独标注。语言按钮和「Show the rest」是可聚焦控件。浏览器打开了英文页并读到这些控件；中文由同一 `applyLanguage` 经 `?lang=zh` 截图确认 |
| A27 | 全量 pytest | 通过 | 原有财报、历史、Ask 范围测试仍在套件内并通过 |
| A28 | 健康报告 HTTP 200 且错过超过 4 个窗口 | 通过 | `ok` 为 false，`overall` 为 critical。公开结果无 traceback / api_key |
| A29 | `monitor_action` | 通过 | 无 `EVENTS_RERUN_TOKEN` 时 `action=alert` 且 `auto_repair` 为 false。有配置名时只请求补跑，仍不宣称已经修好 |
| A30 | events 函数 POST | 通过 | 405。源码不引用 Finnhub。未认证 GET 不抓取 |

预览（fixture，不是 Finnhub 实拉）：

- AAPL 有条目：`docs/lens-events-preview/aapl-available.html`，`aapl-desktop-en.png`，`aapl-desktop-zh.png`，`aapl-mobile-en.png`，`aapl-mobile-zh.png`
- JPM 成功但零条：`jpm-empty.html`，`jpm-mobile-en.png`，`jpm-desktop-zh.png`
- NVDA 保留上次条目并标 stale：`nvda-stale.html`，`nvda-desktop-en.png`，`nvda-mobile-zh.png`

这些预览页会请求 `/api/events`。静态预览服务器没有该接口，所以页面底部会出现「更新的事件源没有载入」。这是读取失败时的提示，不是生产 Blob 演练。

## 运行观测

未上线。没有 48 小时间隔、延迟分布或真实补跑记录。不要把上表的目标频率当成已达到的指标。

## 未完成（交给 Codex）

- `FINNHUB_API_KEY` 未出现在 GitHub Actions secrets。真实 AAPL/JPM/NVDA 新闻没有拉取。
- `BLOB_READ_WRITE_TOKEN` 未配置。Blob 的 HTTP 客户端按 `@vercel/blob` API version 12（`x-api-version`、`x-if-match`）编写，并用假传输测了 412，没有对真实 store 写过对象。
- `EVENTS_RERUN_TOKEN` 未配置。独立唤醒未配置。
- `events-refresh.yml` / `events-monitor.yml` 没有 schedule。合并本 PR 也不会打开新定时器。周六全链路刷新和部署保持原样。
- 未部署生产，未改 `lens.josephjwang.com`。
- A2 未做：业绩公告与正式财报并列、未来事件确认状态、浏览器自选。
- 普通组策略已实现，没有排程。
- 行情、Company Facts、整站重建仍在周六 workflow。事件任务不调用它们。
- 自动引用校验不能证明模型句子在语义上全部正确。

## Codex 审查

- 待审查。
- 建议先看：`src/company_lens/events/`、`ops/vercel/ask/index.js` 的 `event_version` 分支、`ops/vercel/events/index.js`、两个新 workflow、`docs/lens-events-preview/`。
- 生产发布记录：无。

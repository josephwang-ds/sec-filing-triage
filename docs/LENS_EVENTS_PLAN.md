# Lens：事件研究与分频刷新实施计划

版本：2026-10-23。状态：规划已确定，功能待实现。任务入口：`LENS_CURSOR_START.md`。

## 1. 产品目标与边界

服务于两个场景：Joseph 日常研究自选公司；招聘方/客户查看可验证的数据产品与 AI 工程能力。
核心价值：减少遗漏、过时信息和误读，把“出现新事实 → 与已有证据比较 → 下一个验证节点”连接起来。
不承诺交易速度优势或收益，不把新闻情绪当买卖信号，不接券商交易或用户持仓自动执行。

主要旅程：自选公司 → 自上次查看以来的新变化 → 来源和证据 → 未来事件 → 私人研究记录。
公开公司页保留现有简洁视觉；方法和工程说明放二级页面。个人自选和笔记不写入公开仓库或公共快照。

## 2. 已核对的现状（不是待重新实现的功能）

- 现有前端由 Python 生成静态页面；Vercel 承载页面与 Node `/api/ask`。
- `.github/workflows/refresh.yml` 是周六 07:20 UTC 的全链条任务，另支持手动 dispatch。
- `.github/workflows/freshness.yml` 每周检查一次，阈值 30 天；不适合作为新闻更新监控。
- `scripts/refresh_headlines.py` 默认 lookback=3 天、retention=14 天、每家公司最多 5 条，读取 FINNHUB_API_KEY；全链条才调用。
- 周更 + 固定 3 天 lookback 存在覆盖空档；不可只增加 cron 而不修增量水位。
- `scripts/run_scheduled_refresh.sh` 把新闻、SEC、财务、行情、研究和整站部署串在一起；热数据须解耦。
- Actions 缓存可以丢失，现有丢缓存后全量爬取路径可能需要几十分钟；不能作为每次冷启动的必要动作。
- 旧 DEPLOYMENT.md 的“每工作日”与当前 cron 不一致，实施时一并校正。
- 最新正式 10-Q/10-K 不一定代表最新业绩公告；应并列展示公告与正式报告的实际期间，不能按站点抓取时间认定财报是新的。

## 3. 默认刷新政策（目标间隔，不是已实现的 SLA）

内部时间存 UTC；调度规则用 America/New_York，UI 支持 Asia/Shanghai/当地显示。使用时区库和交易日历处理 DST、节假日、提前收市；不得把纽约时间写成固定北京时间。
“活跃窗口”初始定义为纽约工作日 04:00–20:00，覆盖盘前盘后；休市日采取非活跃规则，已确认事件可临时提升。
首期高频组最多 20 家已验证支持的公司；普通公司明确标记为普通覆盖，不能宣称全站都按高频组刷新。

| 任务 | 高频组活跃窗口 | 非活跃/周末 | 特殊规则 |
|---|---|---|---|
| 公司新闻/官方新闻稿 | 每 30 分钟 | 非活跃每 2 小时；周末每 4 小时 | 已确认业绩/重大活动前后 2 小时可升至 15 分钟；配额不足先降级并显示 |
| SEC 新披露索引 | 每 2 小时 | 每 6 小时 | 已确认财报发布窗口及新业绩公告后升至 30 分钟、最多持续 6 小时；未知日期不无限加速 |
| 新文件与附件解析 | 发现新 accession 后排队 | 同左 | 单份只解析一次；修订按新版本处理，失败独立重试 |
| Company Facts/正式财报 | 新 10-Q/10-K 触发 | 每日一次对账 | XBRL 尚未更新时延后补查，不能拿旧 facts 冒充新报告 |
| 未来事件日期 | 每日一次 | 每日一次 | 距已确认事件不足 48 小时每 6 小时检查变更；估算日期不自动升级为确认 |
| 日线行情/历史图表 | 每个交易日收盘后刷新 | 非交易日不制造缺失告警 | 预计收盘后 2 小时首刷，未就绪则次日对账；按最新已完成交易日检查 |
| 全量重算/一致性检查 | 每日夜间一次（有变化才发布） | 周末一次深度对账 | 不阻塞新闻；每周深度维护可保留 |
| 独立健康监控 | 每 15 分钟 | 每 15 分钟 | 检查任务是否真的完成、输出是否可读，而非只看 HTTP 200 |

普通组新闻每日 2 次、SEC 每日 2 次起步；后续按观测的成本/延迟扩大覆盖。
高频组是服务配置，不等于用户的私人自选列表；浏览器添加自选不会自动触发任意 ticker 的付费抓取。

## 4. 调度、冷启动与恢复：必须落地的设计

### 4.1 A0：先确定一个真实可用的运行组合

先核实当前托管套餐、已有持久存储和任务触发能力，只记录非敏感元数据及配置是否存在。
保持 Python 核心与现有 Vercel 页面/Ask，不重写 Next.js，不新增常驻 VPS。
推荐选择：现有 GitHub Actions 执行分离后的 Python 数据任务，持久状态存已配置的对象存储/数据库，Vercel 只服务版本化结果和 AI。Actions 仅缓存依赖/可重建原始文件。
若现有存储没有可用项，默认评估 Vercel Blob 的小型版本化对象方案，核对额度、公开/私有策略、Python 写入方式和并发保证后选择；不要假装本地 JSON 或 Actions artifact 是持久数据库。
若选用的对象存储不支持 CAS，必须实行全局发布单写者、不可变版本对象及序号栅栏；短期租约不足以阻止过期进程覆盖新结果。不同 job 不写同一个可变大 JSON。
将最终选型、成本估算和配置缺口写入 `LENS_EVENTS_STATUS.md`，有明确证据时采用等效方案，不做多套生产后端。

GitHub schedule 允许延迟/漏触发，不承诺 30 分钟必达。Vercel Hobby cron 不能承担高频任务。
需要一个与主调度器独立的已配置托管触发器/心跳监控：过期时发起受保护的补跑（若权限已具备），否则明确告警与恢复入口。
若无独立触发器或所需授权，完成应用适配与演练并如实标记“独立唤醒未配置”；不得宣称已实现无人值守自恢复。不得临时购买新套餐或请求用户在聊天中粘贴 key。
禁用/失效的工作流不能靠同一个 cron 唤醒自己，也不能通过不断制造无意义提交代替监控。

### 4.2 进程不需要常驻

外部触发器启动短任务；每次从持久检查点恢复。应用进程内的 setInterval 和 Mac 常开均不属于生产调度。
页面访问不触发全站抓取、AI 费用或部署。Serverless 冷启动仅加载最小配置与当前 manifest，先返回可用数据，不等待历史全量重建。
首次没有数据：仅初始化当前支持公司的有限窗口（新闻 7 天、披露索引 90 天，受源限制），有覆盖说明；历史回填单独排队。
从停机恢复：按每 ticker/source 的最后成功覆盖水位补拉，新闻重叠至少 24 小时，按 provider 上限拆窗口；无法补回的区间标 coverage_gap，不静默跳过。
90 天初始化并不等于全历史。半年/一年旧事件继续使用可用历史基线，无法提供时说清楚。

### 4.3 一致性、重试和成本边界

- 每任务/ticker 独立记录 attempt、lease/fence、成功水位、失败原因和下一计划执行时间；一个 issuer 失败不阻塞其他 issuer。
- 抓取/持久化不沿用 UI 每公司 3/5 条限制；扫描窗口内全部可取结果按分页保存，预算截断必须记录 pending/coverage_gap。
- 稳定事件 ID 与幂等键；重复触发不产生重复事件，不重复支付模型调用，不重建相同内容。
- 同源限流；对网络/429/5xx 使用带 jitter 的有界退避，尊重 Retry-After。401/403 配置/权限错误不无限重试。
- 设置单任务时间预算、批次数和日请求预算；未完成部分持久排队到下一次，不能杀死已发布的好版本。
- 候选结果先校验 schema、数据有限性、来源、时间和 coverage，再原子发布；失败保留 last-good，仍更新独立的失败状态。
- 取消或超时后可回收租约；迟到旧任务的 fence 不能覆盖新结果。
- 新闻数据内容变化不重新部署前端；无变化的成功检查只更新 checked_at，不伪造 source_published_at。
- LLM 摘要可选且按唯一内容缓存；基础卡片不依赖模型可用性。不能每轮对全部历史新闻重跑模型。
- 记录按来源的请求数、失败率、延迟、每轮耗时及预估月成本；达到预算时降频并清楚标记。

### 4.4 新鲜度口径

分别存储和展示：source_published_at、event_at、first_seen_at、last_successful_check_at、last_attempt_at、content_updated_at、coverage_through、published_snapshot_at。
来源没有时区/只有日期时保留精度标记，不能填午夜作为精确事件时刻。
成功收到零条新消息可以更新检查时间，但不改变旧新闻发布时间。失败不能推进成功覆盖水位。
健康状态至少有 current/no_new_events/stale/partial/unavailable/disabled；未知不是“没有消息”。
各来源独立告警：新闻连续超过 2 个应执行窗口未成功 → degraded，超过 4 个 → critical；SEC 同理。
按到期窗口计算，周末/休市/降频配置要生效。行情用交易日滞后；未来事件用日检查，不能共用一个“30 天以内正常”标签。
事件发生后没有新公告，不代表任务失效；判断检查成功时间与内容日期必须分开。

## 5. 数据合同与公开边界

### Event（最小字段）

- id/schema_version/ticker/cik/type：news、earnings_release、filing、guidance、financing、deal、regulatory、management、product、scheduled_event 等。
- title/source_excerpt/summary：摘要不足时只显示标题，标注“仅标题”；不得由标题虚构数值或事件细节。
- source_url/publisher/source_kind：official_ir、sec、news_provider；输入内容始终是不可信数据。
- source_published_at/event_at/timezone/time_precision/first_seen_at/updated_at。
- status：reported/confirmed/estimated/postponed/cancelled/completed；未来日期来源独立记录 confirmed_by 与 last_verified_at。
- source_event_id/accession/related_event_ids/duplicate_group_id；修订历史可追溯。
- significance_reason：为何列为值得关注（可核验事实），不是买卖建议或单一利好/利空分数。
- evidence_refs：原始出处、可引用段落、提取方法/版本；仅供应商元数据时不能伪装为读过全文。

### RefreshState / Manifest

按 dataset+ticker/source 存 state、成功覆盖窗口、上次尝试、错误类别、重试/下次到期时间、版本、哈希、fencing sequence。
manifest 指向不可变的已通过校验的数据版本；不同来源的 as_of 必须保留，不宣称所有数据是同一时刻。
公共接口只提供已审核的公开事件、简短允许转载的摘要和原文链接；不公开原始缓存、credentials、内部日志、个人自选或研究笔记。
公开展示新闻前确认供应商授权范围，不复制整篇报道；不是购买了 API 就默认可公开再分发。

## 6. 页面与 AI 的端到端一致性

公司页在财报变化之后、历史表现之前新增“事件与接下来关注”，默认 3 条，展开更多。
并排或分段展示“最近发生”“接下来关注”；没有可靠未来日期时给出诚实空状态。
卡片显示事件/发布时间、来源、更新时间、确认/预计标签；中文摘要与原始英文标题区分。
新闻/事件 JSON 独立更新，页面保留静态基线；读取失败仍可浏览已有财报、历史图表和 AI 原有功能。
英文/中文完整覆盖；移动端 390px 不横向溢出；原始引用不擅自翻译成新事实。

AI 新增事件证据前必须实现：
1. 页面明确显示 manifest/version，提问携带已见版本 ID；服务端只从可信存储按已验证 ticker+version 获取证据，不接受客户端自造证据或任意 URL。
2. 页面与 AI 使用相同事件版本；现有正式财报/SPY 快照作为独立带日期证据。版本过期无法读取时提示刷新，不静默回答另一版。
3. 新证据进入 citation 与 number allowlist，保留已实现的中文金额/百分点表示、来源边界、问答预算与限流。
4. 未来事件只说明日期和确认程度，不预测收益；新闻与随后股价变化不推断因果。
5. 尚未完成版本一致性时可展示来源卡片，但禁用“让 AI 解读此事件”，不能让按钮落回不含事件的旧 evidence。

## 7. 批次与文件落点

### A0 — 基线与可运行架构（Cursor 先做，紧接 A1）

核对平台能力、选定一个持久存储与调度方案、明确普通组/高频组边界；记录风险和配置缺项；修正冲突文档。
输出 `LENS_EVENTS_STATUS.md` 与可测试的策略/存储接口。无外部 key 仍可写实现与故障 fixture，不得假称线上正常。

### A1 — 可靠刷新 + 新闻事件最小闭环（本轮实现范围）

- 拆任务与配置化 due 策略；实现独立状态、增量补拉、幂等、last-good、预算与恢复测试。
- 接入已有新闻 provider，来源去重与准确空状态；首期以 AAPL/JPM/NVDA 作真实演示，无数据则如实展示。
- 公共事件读取接口和公司页区块；数据更新不靠整站 redeploy。
- 事件 AI 证据版本链路、中文/英文入口与引用验证；保留旧问答行为。
- 独立健康接口与监控/补跑适配，至少完成安全的 staging 故障演练；未配置环节单列。
- PR 提供任务级指标与配置说明。A1 完成先交 Codex 验收，不擅自扩展到 A2。

建议新增模块可按项目风格调整：`src/company_lens/events/`（contracts、normalization、store、refresh_policy）、独立 refresh CLI、`ops/vercel/events/`、健康接口、`web/events.py`。
优先复用：`news.py`、`refresh.py`、`web/ask.py`、`web/page.py`、`financial_results.py`、`scripts/build_vercel_output.py` 和现有 tests。
不要复制一套与既有财报/历史计算相矛盾的实现；不要将 hot path 拉进训练/回测/全量预测日志流程。

### A2 — 最新业绩公告、未来事件、基础自选

- 优先 SEC Item 2.02 与相关 Exhibit 99.x、公司官方 IR 新闻稿；解析原文出处和期间，unsupported 时保留链接，不捏造数字。
- 同时显示“最新业绩公告”与“最新正式季报/年报”，显示各自发布日期、期间和 GAAP/non-GAAP；两者有冲突保留差异与版本。
- 财报日、电话会、投资者日等未来事件：官方确认优先，第三方估计独立标签；日期调整保留变更记录。
- 自选初版仅浏览器本地存储，支持删除/导入导出；无账号与跨端同步承诺。
- “上次查看以来”按 first_seen_at/修订版本而非仅发布时间计算，避免漏掉迟到新闻；不记录公开服务器上的个人持仓。

### B — 历史事件、指引/市场预期对比

事件时间线与同窗口公司/基准行情：严格区分首次公开时间、发生时间、SEC 接收时间；处理盘前盘后、无精确时刻、节假日和不足样本。
市场一致预期需要真实有授权的数据源，保存公告前版本与截点；匹配财年季度、GAAP/non-GAAP、币种和稀释 EPS 口径。
不能把后修订预期、未来数据带回历史比较，也不从随后涨跌认定消息因果。

### C — 私人研究记录与作品集案例

记录关注理由、可证伪假设、下一验证节点、当时证据；支持事后复盘而不改写历史判断。
招聘展示用独立示例：用户问题→数据与方法→界面→评估结果→限制。使用量/节省时间/准确率没有测量前不编造。

## 8. 本轮完成定义

A1“代码完成”、A1“预览可验证”、A1“生产已启用”是三种不同状态。
通过 `LENS_EVENTS_ACCEPTANCE.md` 的对应测试，PR 可重现，来源和时间正确，原功能回归通过，才交付代码验收。
生产验收还需：真实持久存储与触发器已配置、连续至少 48 小时观测及一次独立补跑演练，无关键覆盖空档；48 小时不是一次会议中可以虚报完成的步骤。
若外部配置缺失，交可运行代码与精确缺项；不等待配置而停止全部可独立完成的工作。

## 9. 官方参考（2026-10-23 核对）

- SEC 更新与访问：https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Finnhub 公司新闻/事件接口：https://finnhub.io/docs/api ，https://github.com/Finnhub-Stock-API/finnhub-python
- GitHub schedule 的延迟/漏触发/default branch/长期不活动限制：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Actions cache 不是持久数据源：https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- Vercel Hobby cron 频率限制：https://vercel.com/docs/cron-jobs/usage-and-pricing

实施时核对当前账号实际能力；文档列出的能力不等于本项目已经开通。不要改变来源许可或服务安全限制来满足刷新频率。

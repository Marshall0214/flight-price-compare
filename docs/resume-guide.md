# 简历与面试准备：机票比价 Agent

这份文档不是给招聘方看的，是给你自己用的——写简历时直接抄 bullet，面试前过一遍话术和预案。**下面第 1 节的数字已经是真实跑分（见 `eval/results.md`），不是编造的**；如果你之后改了代码或场景重新跑过评测，记得同步更新这里。

## 1. 简历 Bullet

按“问题 - 方案 - 技术 - 结果”结构，指标已经是真实跑分：

**中文版（任选 1-2 条，不建议三条全上，简历要留白）**

> 设计并实现基于 LangGraph 的机票比价 Agent：将自然语言出行需求解析为结构化搜索条件，缺失关键信息时主动追问而非猜测；通过多节点工作流编排工具调用、约束放宽重试与追问循环，价格计算、币种/行李标准化、去重、重新验价均由确定性代码完成，避免 LLM 生成关键数字。

> 调研 LangGraph 官方客服机器人教程与 CRAG（Corrective RAG）等参考设计后，为 Agent 设计了明确的自主权边界：查询无结果时，按规则自主放宽用户没有明确表态过的日期弹性重试；但对用户明确表达的硬约束（如"不要红眼航班"）不会自主放弃，只生成追问、等用户下一轮同意才放宽，拒绝后不重复追问；同时让 LLM 从自然语言判断用户对价格/舒适度的倾向，映射为确定性代码执行的排序权重策略——LLM 全程只做语义判断和文案生成，不参与任何数值计算或排序。

> 构建包含 29 个固定场景的 Agent 评测集（部分场景措辞参考了 ATIS 航班对话数据集），覆盖参数缺失、模糊日期、错误机场代码、无结果、中途改需求、往返查询、多币种换算、约束放宽重试、偏好画像排序等情况，断言不止查状态码，还校验实际选中的航班/失败原因是否正确；实测参数提取正确率 100%、工具调用成功率 100%、端到端任务完成率 100%，平均响应时间约 4.5s，平均 Token 成本约 1030 tokens/请求（模型：deepseek-flash，测量于 2026-09-14，详见 `eval/results.md`）。评测集扩充过程中共发现并修复了 5 处真实 bug（往返查询未真正搜索回程、红眼航班未被真正过滤只做了轻微降权、模糊日期被误判为缺失信息导致无谓追问、红眼确认被拒绝后陷入死循环追问、"一周弹性"被误判为"玩一周"的行程天数），详见下方面试话术。

> 将航班搜索工具按 MCP tool schema 风格设计并封装最小 MCP Server，验证同一套工具函数可分别被内部 Agent 图与外部 MCP 客户端调用；使用 FastAPI 提供 `/query` HTTP 接口，pytest（43 用例）覆盖核心确定性逻辑与 Agent 决策边界。

**英文版（对应第一、二条，供海外岗位或英文简历使用）**

> Designed and built a flight-price-comparison agent on LangGraph: parses natural-language travel requests into structured search parameters, asking clarifying questions instead of guessing when required fields are missing; orchestrates tool calls, constraint-relaxation retries, and a clarification loop across a multi-node workflow, while delegating price calculation, currency/baggage normalization, deduplication, and fare re-verification to deterministic code rather than the LLM.

> After researching LangGraph's official customer-support-bot tutorial and the CRAG (Corrective RAG) pattern, designed an explicit autonomy boundary for the agent: on an empty search, it rule-based-ly retries by widening a date-flexibility window the user never explicitly stated, but never silently drops a hard constraint the user did state (e.g. "no red-eyes") — it asks first, and won't re-ask after a decline; a `priority_profile` inferred from the user's stated price/comfort trade-off then selects which of three deterministic weighting presets the ranker uses. Built a 29-scenario evaluation harness (partly inspired by the ATIS flight-dialogue dataset) whose assertions check the actual chosen flight or error reason, not just the status code, measuring 100% parameter-extraction accuracy, 100% tool-call success rate, and 100% end-to-end task completion (deepseek-flash, ~4.5s avg latency, ~1030 tokens/request) — the process surfaced and fixed 5 real bugs, including a round-trip search that silently never queried the return leg, a red-eye "avoid" preference that was only soft-downweighted instead of hard-filtered, fuzzy dates misclassified as missing required fields, an infinite re-ask loop when a user declined the red-eye confirmation, and an LLM misparse confusing "a week of date flexibility" with "a week-long trip."

## 2. 面试展开话术

面试官大概率会顺着 bullet 往下问“具体怎么做的”，提前想好怎么在 1-2 分钟内讲清楚：

- **为什么用 Agent/LLM，而不是纯规则解析？** 自然语言的表达方式很发散（“9月找便宜的”、“别让我半夜到”），穷举规则成本高；但一旦解析出结构化字段之后的所有计算，就没有理由再交给 LLM——这正是这个项目想体现的边界划分。
- **为什么用 LangGraph 而不是一个大 Prompt 或简单 while 循环？** 因为流程本身有条件分支（缺参数追问 / 无结果报错 / 硬约束确认）和循环（追问后回到解析），用图能显式表达状态转移，比一个巨大的 System Prompt 更可维护、也更容易加节点（比如后续接入真实 API 时只需要替换 `search_flights` 节点内部实现）。
- **为什么价格计算、排序、去重不让 LLM 做？** 这些是必须 100% 正确的计算，LLM 存在幻觉风险，用普通代码保证确定性和可测试性（pytest 可以覆盖，LLM 生成的数字没法这样测）。
- **这个项目一开始并不算真正的 Agent，是怎么变成的？（很值得主动讲的一段）** 项目中期我自己提出过这个质疑：最初的版本里 LLM 从来不自主决定"要不要调用工具、什么时候重试"，那一步完全是代码用条件边写死的，LLM 只在固定节点上做结构化抽取和生成文案，更准确地说是"LLM 辅助的确定性工作流"。为了搞清楚该不该改、怎么改，我去调研了 [LangGraph 官方客服机器人教程](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/tutorials/customer-support/customer-support.ipynb)（一个瑞士航空订票助手，用 `interrupt()` 在改签/扣款这类不可逆操作前暂停确认）和 [CRAG](https://www.langchain.com/blog/agentic-rag-with-langgraph)（检索结果质量不够就改写查询重试）这两个参考实现，得出了一个开放式的结论——不是"必须塞功能证明是agent"，而是"哪个真的贴合就做，不贴合就明确说不做"：
  - **采纳**：查询无结果时，按规则自主放宽用户没表态过的日期弹性重试；对用户明确说过的硬约束（"不要红眼航班"）不自主放弃，只追问、等同意才放宽——这是真实存在的语义判断点，也没有违反"数值计算必须是确定性代码"的原则。
  - **不采纳**：客服机器人式的"操作前用户确认"。原教程需要确认是因为会执行不可逆操作（改签/扣款），本项目从头到尾只做搜索比价，没有任何操作需要确认，硬套这个模式就是自己说的"为了像agent而agent"。结论写进了 Roadmap："预定模块一旦立项，这里就是要补上确认环节的地方"。
  - **主动否决**：还想过一个"追问超过N轮就用默认值兜底继续搜索"的点子，但发现会直接违反项目从最开始就有的"必要字段不允许模型猜测"原则，没有为了凑"agentic程度"而做。
  这个过程比直接说"我用了LangGraph所以这是个agent"更有说服力——面试官问起来能具体讲清楚边界画在哪、为什么画在这、调研了什么参考实现。
- **调研 CRAG 之后，对"agent决策"这件事的理解有什么变化？** 一开始以为"让LLM自己判断该放宽哪个约束"才算真正的agent，但看了真实的CRAG实现才发现：业界的Corrective RAG里，"要不要重试"这个控制流决策本身通常也是规则/阈值判断（比如相关性打分低于某个阈值就重试），LLM真正被用在"评估内容质量""改写查询"这类需要语义理解的子任务上，不是控制流本身。这让我把设计边界调整为"规则决定要不要重试，LLM决定重试时怎么表达/怎么理解用户回复"，和这个项目一贯的"LLM只做语言理解与生成，代码管控制流和数值"的原则完全吻合——算是调研之后修正了自己一开始的错误理解，而不是硬凑一个和真实业界做法不一样的设计。
- **MCP 封装的意义是什么，为什么只做了最小版本？** 目的是验证“工具函数应该独立于调用方”这个设计原则——同一个 `search_flights`，内部 LangGraph 图调用它，外部 MCP 客户端也能调用它，不需要为每个调用方重写一遍。当前只做最小封装是因为优先级上先把核心 Agent 逻辑和真实评测做扎实，完整的 MCP 项目（多工具、完整测试文档）是明确写在 Roadmap 里的下一步，不是没想到。
- **评测集为什么是 29 个场景？够不够？** 经历了三轮扩充：最初 10 个，覆盖正常路径、参数缺失、模糊输入、异常输入、中途变更、业务规则组合这六类核心能力；扩到 20 个是因为样本量太小、断言又只查状态码；扩到 23 个是为了区分"机场代码合法但没数据"和"机场代码根本不认识"这两种不同的失败原因，并参考 [ATIS](https://github.com/topics/atis-dataset) 补了两条不同句式结构的场景；扩到 29 个是为了给新加的两个agentic能力（约束放宽重试、偏好画像排序）各配 2-3 个场景，包括正向路径和边界情况（用户明确拒绝放宽的路径）。关键场景都加上了 `expected_results`（校验实际选中的 flight_id 或 error_code），让评测真正测的是业务结果而不是"有没有崩溃"。样本量依然不足以支撑 P95 延迟或失败恢复率这类需要统计意义的指标，所以我明确没有报告这些数字。
- **评测过程中实际发现了什么问题？（很值得主动讲的一段）** 一共发现并修了 5 处真实 bug、记录了几处真实但不修的限制，都不是靠代码审查发现的，是靠评测/手动跑通发现的：
  1. **往返查询根本没有真正查回程**（扩充场景到 20 个时才发现）：`FlightSearchRequest` 里一直有 `trip_duration_days` 这个字段，Prompt 也会把它解析出来，但整条 pipeline 里没有任何地方真正用它去搜索回程航班——原来的"往返"场景之所以显示 PASS，只是因为去程那部分单独查也能成功，断言又只看状态码，掩盖了"回程根本没查"这个事实。修复方式是在 `search_flights_node` 里：如果 `trip_duration_days` 有值，就用"出发日期 + 行程天数"算出返程日期，把目的地和出发地反过来再查一次，`rank_and_tier_node` 再按去程/回程同档位配对，算出往返合计总价。
  2. **红眼航班没有被真正过滤**：最初 `avoid_red_eye` 只在"最舒适"档里做轻微降权，没有把红眼航班从候选集里剔除，导致一趟很便宜的红眼航班仍可能被判定为"最便宜/综合最优"，和用户明确说的"不要红眼航班"直接矛盾。修复方式是把过滤挪到 `search_flights` 节点，作为硬约束直接剔除。
  3. **模糊日期解析被误判为缺信息**："9月上旬找便宜机票"一度被误判为"缺日期"去追问，而不是理解成一个日期区间。修复方式是在 Prompt 里教模型把"上旬/中旬/下旬"转换成"锚点日期 + 弹性天数"。
  4. **红眼确认被拒绝后陷入死循环**（加了约束放宽功能后新发现，也是最能体现"agent决策边界"设计的一个坑）：用户拒绝接受红眼航班后，`avoid_red_eye` 正确保持不变，但系统下一轮重新搜索时又一次判定"红眼是唯一阻碍"，于是又生成了同一句追问——变成了反复问同一个问题的死循环，而不是老实报告失败。根因是路由逻辑只看"当前搜索条件下红眼挡不挡路"，没有记住"这个问题已经问过、被拒绝过"。修复：新增 `redeye_confirmation_declined` 字段，由代码根据"问过 + 用户回复后 avoid_red_eye 有没有变成false"推断，`route_after_search` 检查到已拒绝过就直接判定为真正的无结果。**这个bug很有代表性：给agent加自主决策能力时，很容易漏想"这个决策要不要有记忆"，不然看起来像自主重试，实际是无限循环。**
  5. **"一周弹性"被误判为"玩一周"**：LLM 把"大概一周弹性都可以"解析成了 `trip_duration_days=7`（行程天数）而不是 `date_flexibility_days=7`（日期弹性），把单程查询误判成往返查询，因为回程日期没数据而报错。修复：在 Prompt 里补充了两个概念的对比说明和例句。
  6. **没有修、只记录为已知限制**：状态合并没法显式"清空"一个已知字段（先说往返、后说"不用回程了"，`trip_duration_days` 清不掉）；"左右"这类模糊限定词的弹性天数解读不完全稳定（每次1-3天不等，但每次选出的都是当次窗口内价格最低的，排序逻辑本身没问题）。两个都诚实地写进了已知限制，没有为了让测试通过而硬修或者删场景。
- **29 个场景全部 100% 通过，会不会显得像是刷出来的？** 这份评测集是我自己设计的，不是盲测/对抗集，我不会说它能代表生产环境的所有情况；但断言不只是"状态码对不对"，还包括"具体选中的航班/错误原因对不对"，比单纯看状态码严格得多。而且这不是一次性凑出来的 100%——从最初 10 场景的 60%/80%，到扩到 20 场景后暴露出往返查询的真实 bug，到扩到 23 场景后发现"左右"弹性天数不稳定其实是断言太脆弱、代码没错，再到扩到 29 场景后发现红眼确认死循环和"一周弹性"误判两个新bug，是经过四轮真实的"发现问题、定位问题、该修代码时修代码/该改断言时改断言"才到 100% 的，我可以具体讲出每一个坑是什么、怎么发现的、最后是怎么处理的。

## 3. 常见追问预案

| 可能的追问 | 回答要点 |
|---|---|
| 这个项目只用了一天，含金量够吗？ | 一天完成的是“核心闭环 + 真实评测”，前置知识（LangGraph、MCP、Eval 概念）之前已经学过，这个项目是把知识串成一个可运行、可验证的系统，而不是从零学起；Roadmap 里列的真实 API 接入、完整 MCP 项目、更大规模评测是明确的下一步，说明我知道当前边界在哪。 |
| 只用 mock 数据，怎么证明能接入真实场景？ | 工具层已经按“任何调用方都能用”的 schema 设计（MCP-style），接入真实 API 只需要替换 `search_flights` 内部实现，不需要改动 LangGraph 图结构或上层接口，这是当初设计数据模型和工具接口时就考虑到的。 |
| 如果 LLM 幻觉导致解析错误怎么办？ | 用 Pydantic 做结构化输出校验，校验失败触发重试；同时评测集里专门测参数提取正确率，这个指标就是用来量化这个风险的，不是假设它不存在。 |
| Token 成本有没有优化？ | 当前版本的重点是先把功能和评测做对；`eval/results.md` 里的平均 Token 成本就是用于后续优化的基线，比如后续可以尝试更小的模型做 `parse_input`、更大的模型只用在需要生成自然语言解释的节点。 |
| 和网上很多“调用 API 查机票”的 Demo 有什么区别？ | 区别在于把“LLM 该做什么、不该做什么”的边界讲清楚了：所有涉及金额、排序、去重的逻辑都不经过 LLM；同时有真实评测集和确定性逻辑的单元测试，不是一个只能演示 happy path 的脚本。 |
| 为什么不做前端？ | 优先级先放在 Agent 核心能力和评测的真实性上，做完之后补了一个本地 Streamlit 对话演示页（`demo/streamlit_app.py`）方便现场演示和录 GIF，但不做在线部署——它本身就是 `/query` 的一个客户端，不涉及任何后端逻辑改动，服务端仍然是无状态设计。 |
| 评测场景和机场代码是自己瞎编的吗？ | 不是。机场代码参考了公开的 IATA 代码库（如 `github.com/mwgg/Airports` 这类项目），城市→机场的映射是真实的；部分评测场景的问法风格参考了 ATIS（一个学术界常用的航班对话 NLU 数据集，26 个意图、83 种槽位类型）里"how much is the cheapest flight"、"I'd like to fly from X to Y"这类经典句式，改写成中文、适配到自己的 mock 数据和路线上，不是直接照搬原数据集的句子（原数据集问的是波士顿到旧金山，跟这个项目的 mock 数据对不上）。 |
| 为什么没有做"预定前用户确认"这个环节？别的agent demo都有。 | 调研过 LangGraph 官方客服机器人教程里的这个模式，结论是它解决的是"改签/扣款这类不可逆操作前要不要暂停"的问题；这个项目从头到尾只做搜索比价，不涉及任何写入/预定/扣款动作，没有东西需要确认。硬套这个模式是"看起来更agentic但没有实际意义"，所以没做，写进了 Roadmap：一旦做预定模块，这里就是要补的地方。 |
| Agent 的自主权边界具体怎么画的？会不会太保守/太激进？ | 原则是"能不能自主做，取决于用户有没有明确表态过"：用户没提过的默认值（比如没说弹性天数）可以被自主放宽去重试；用户明确表达过的约束（比如"不要红眼"）不能被自主推翻，只能问一句。这条边界和"必要字段不允许模型猜测"是同一个道理的两个方面——都是"模型不该替用户做主"。会不会太保守可以商榷，但这是一个经过实际调研（CRAG、客服机器人教程）和自我否决（拒绝了N轮兜底默认值的点子）之后画出来的边界，不是拍脑袋定的。 |
| 加了这两个"agentic"功能之后，评测通过率反而先掉下去了，这不就说明设计有问题吗？ | 恰恰相反：掉下去说明评测真的在起作用，不是摆设。两次先失败后修复（红眼确认死循环、"一周弹性"误判），都是加了新能力之后才暴露出来的真实边界情况，如果我因为怕评测变红就不去加这些更贴近真实agent行为的功能，或者加了之后发现失败就悄悄放宽断言，那才是有问题。一个愿意先让通过率变差、再认真定位修复的过程，比一路100%到底更可信。 |

## 4. 指标口径与复现方法

第 1 节里的数字来自 2026-09-14 用 `deepseek-flash` 跑的一次 `python -m eval.run_eval`，完整记录见 `eval/results.md`（29 个场景逐条通过情况也在里面）。如果换了模型、改了 prompt 或加了新场景，**必须重新跑一遍再更新这里**，不能沿用旧数字。

| 指标 | 含义 | 计算方式 |
|---|---|---|
| 参数提取正确率 | 29 个场景中，合并后的 `request` 字段是否符合场景预期 | `run_eval.py` 逐场景用 `field_matches` 校验 `expected_fields` |
| 工具调用成功率 | 在“预期会走到 `search_flights`”的场景里（即预期状态不是 `clarification`），实际状态也确实是 `results`/`error`（而不是卡住或异常）的比例 | 分母是 expected_status != clarification 的场景数，不是全部 29 个 |
| 端到端任务完成率 | 状态匹配预期 **且** 字段匹配预期 **且**（若场景定义了 `expected_results`）实际选中的航班/档位/错误原因也匹配预期的场景占比 | `status_ok and fields_ok and results_ok`——`results_ok` 是校验真实业务结果（比如 `results.cheapest.outbound.flight_id`、`error.error_code`，或 `relaxation_notes` 非空）的部分，不只是状态码 |
| 平均响应时间 / 平均 Token 成本 | 每次 `run_agent()` 调用的耗时与 LLM `usage.total_tokens` | 29 次取平均 |

如果之后场景数或分母定义又调整了（比如加了新场景类型），记得同步改这张表，不要让文档和 `eval/run_eval.py` 的实际实现脱节。

如果某次重新评测出现不通过的场景，**先搞清楚是代码错了还是断言写得太脆弱，再决定改哪一边**——不要为了让指标好看就删掉不利场景、也不要看到失败就下意识去改代码。这次经历了四轮"发现问题、定位问题、该修代码时修代码/该改断言时改断言"才到 100%（10 场景时的 60%/80%，扩到 20 场景后暴露的往返真实 bug，扩到 23 场景后发现"左右"弹性天数不稳定其实是断言太脆弱、代码本身没错，扩到 29 场景加上约束放宽/偏好画像功能后又暴露出红眼确认死循环和"一周弹性"误判两个新 bug，见上一节），这个过程本身就是最有说服力的部分，比一次性 100% 更值得写进面试话术。

## 5. 使用提醒

- 简历和面试里出现的任何数字，必须能在 `eval/results.md` 里找到对应的真实记录，讲不出数字是怎么测出来的，比没有数字更糟糕。
- 如果面试官要求现场跑一遍，确保 README「快速开始」的命令在你自己的机器上确实能跑通，这是这份文档存在的另一个前提。

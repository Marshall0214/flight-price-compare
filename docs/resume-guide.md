# 简历与面试准备：机票比价 Agent

这份文档不是给招聘方看的，是给你自己用的——写简历时直接抄 bullet，面试前过一遍话术和预案。**下面第 1 节的数字已经是真实跑分（见 `eval/results.md`），不是编造的**；如果你之后改了代码或场景重新跑过评测，记得同步更新这里。

## 1. 简历 Bullet

按“问题 - 方案 - 技术 - 结果”结构，指标已经是真实跑分：

**中文版（任选 1-2 条，不建议三条全上，简历要留白）**

> 设计并实现基于 LangGraph 的机票比价 Agent：将自然语言出行需求解析为结构化搜索条件，缺失关键信息时主动追问而非猜测；通过 10 节点工作流编排工具调用、错误处理与追问循环，价格计算、币种/行李标准化、去重、重新验价均由确定性代码完成，避免 LLM 生成关键数字。

> 构建包含 20 个固定场景的 Agent 评测集，覆盖参数缺失、模糊日期、错误机场代码、无结果、中途改需求、往返查询、多币种换算等情况，断言不止查状态码，还校验实际选中的航班是否正确；实测参数提取正确率 100%、工具调用成功率 100%、端到端任务完成率 100%，平均响应时间约 4.5s，平均 Token 成本约 770 tokens/请求（模型：deepseek-flash，测量于 2026-09-14，详见 `eval/results.md`）。评测集扩充过程中发现并修复了三处真实问题，其中一处是往返查询解析出了行程天数却从未真正用它搜索过回程航班（见下方面试话术）。

> 将航班搜索工具按 MCP tool schema 风格设计并封装最小 MCP Server，验证同一套工具函数可分别被内部 Agent 图与外部 MCP 客户端调用；使用 FastAPI 提供 `/query` HTTP 接口，pytest 覆盖核心确定性逻辑。

**英文版（对应第一条，供海外岗位或英文简历使用）**

> Designed and built a flight-price-comparison agent on LangGraph: parses natural-language travel requests into structured search parameters, asking clarifying questions instead of guessing when required fields are missing; orchestrates tool calls, error handling, and a clarification loop across a 10-node workflow, while delegating price calculation, currency/baggage normalization, deduplication, and fare re-verification to deterministic code rather than the LLM. Built a 20-scenario evaluation harness whose assertions check the actual chosen flight, not just the status code, measuring 100% parameter-extraction accuracy, 100% tool-call success rate, and 100% end-to-end task completion (deepseek-flash, ~4.5s avg latency, ~770 tokens/request) — the process surfaced and fixed a real bug where round-trip requests parsed a trip duration but never actually searched for a return flight.

## 2. 面试展开话术

面试官大概率会顺着 bullet 往下问“具体怎么做的”，提前想好怎么在 1-2 分钟内讲清楚：

- **为什么用 Agent/LLM，而不是纯规则解析？** 自然语言的表达方式很发散（“9月找便宜的”、“别让我半夜到”），穷举规则成本高；但一旦解析出结构化字段之后的所有计算，就没有理由再交给 LLM——这正是这个项目想体现的边界划分。
- **为什么用 LangGraph 而不是一个大 Prompt 或简单 while 循环？** 因为流程本身有条件分支（缺参数追问 / 无结果报错）和循环（追问后回到解析），用图能显式表达状态转移，比一个巨大的 System Prompt 更可维护、也更容易加节点（比如后续接入真实 API 时只需要替换 `search_flights` 节点内部实现）。
- **为什么价格计算、排序、去重不让 LLM 做？** 这些是必须 100% 正确的计算，LLM 存在幻觉风险，用普通代码保证确定性和可测试性（pytest 可以覆盖，LLM 生成的数字没法这样测）。
- **MCP 封装的意义是什么，为什么只做了最小版本？** 目的是验证“工具函数应该独立于调用方”这个设计原则——同一个 `search_flights`，内部 LangGraph 图调用它，外部 MCP 客户端也能调用它，不需要为每个调用方重写一遍。当前只做最小封装是因为优先级上先把核心 Agent 逻辑和真实评测做扎实，完整的 MCP 项目（多工具、完整测试文档）是明确写在 Roadmap 里的下一步，不是没想到。
- **评测集为什么是 20 个场景？够不够？** 最初只写了 10 个，覆盖正常路径、参数缺失、模糊输入、异常输入、中途变更、业务规则组合这六类核心能力；后来意识到两个问题又扩到 20 个：一是样本量太小、"100%"没有说服力，二是当时的断言只检查状态码，没有真正校验"选出来的航班对不对"。扩充后新增了往返、多币种（JPY/USD）、机场代码直查、行李边界值、多字段一次性追问等场景，并且给关键场景加上了 `expected_results`（校验实际选中的 flight_id），让评测真正测的是业务结果而不是"有没有崩溃"。样本量依然不足以支撑 P95 延迟或失败恢复率这类需要统计意义的指标，所以我明确没有报告这些数字。
- **评测过程中实际发现了什么问题？（很值得主动讲的一段）** 一共发现并修了三处真实问题，都不是靠代码审查发现的，是靠评测/手动跑通发现的：
  1. **往返查询根本没有真正查回程**（最值得讲的一个，扩充场景到 20 个时才发现）：`FlightSearchRequest` 里一直有 `trip_duration_days` 这个字段，Prompt 也会把它解析出来，但整条 pipeline 里没有任何地方真正用它去搜索回程航班——原来的"往返"场景之所以显示 PASS，只是因为去程那部分单独查也能成功，断言又只看状态码，掩盖了"回程根本没查"这个事实。加了 `expected_results` 校验回程 flight_id 之后立刻暴露出来。修复方式是在 `search_flights_node` 里：如果 `trip_duration_days` 有值，就用"出发日期 + 行程天数"算出返程日期，把目的地和出发地反过来再查一次，`rank_and_tier_node` 再按去程/回程同档位配对，算出往返合计总价。这个 bug 说明了一件事：只测状态码、不测实际业务结果的评测集，会把"看起来对"和"真的对"混为一谈。
  2. **红眼航班没有被真正过滤**：最初 `avoid_red_eye` 只在"最舒适"档里做轻微降权，没有把红眼航班从候选集里剔除，导致一趟很便宜的红眼航班仍可能被判定为"最便宜/综合最优"，和用户明确说的"不要红眼航班"直接矛盾。修复方式是把过滤挪到 `search_flights` 节点，作为硬约束直接剔除，而不是留给排序去弱化。
  3. **模糊日期解析被误判为缺信息**："9月上旬找便宜机票"这种场景一度被系统误判为"缺日期"从而去追问，而不是理解成一个具体的日期区间。原因是 `parse_input` 的 Prompt 没有教模型怎么把"上旬/中旬/下旬"这类模糊表达转换成"锚点日期 + 弹性天数"，补上这条规则后就正常解析了。
  4. 扩充场景时还额外发现一个**没有代码修复、只能记录为已知限制**的问题：状态合并没法显式"清空"一个已知字段（先说往返、后说"不用回程了"，`trip_duration_days` 清不掉）。这个我没有强行修，因为要正确解决需要引入"显式清空"的哨兵值机制，超出一天冲刺的范围，所以诚实地写进了 `docs/requirements.md` 的已知限制里，评测场景也换成了别的、当前确实支持的能力，而不是硬凑一个会失败的场景。
- **20 个场景全部 100% 通过，会不会显得像是刷出来的？** 这份评测集是我自己设计的，不是盲测/对抗集，我不会说它能代表生产环境的所有情况；但断言不只是"状态码对不对"，还包括"具体选中的航班对不对"，比单纯看状态码严格得多。而且这不是一次性凑出来的 100%——从最初 10 场景的 60%/80%，到扩到 20 场景后又暴露出往返查询的真实 bug，是经过两轮真实的"发现问题、修复、重新验证"才到 100% 的，我可以具体讲出每一个坑是什么、怎么发现的、怎么修的。

## 3. 常见追问预案

| 可能的追问 | 回答要点 |
|---|---|
| 这个项目只用了一天，含金量够吗？ | 一天完成的是“核心闭环 + 真实评测”，前置知识（LangGraph、MCP、Eval 概念）之前已经学过，这个项目是把知识串成一个可运行、可验证的系统，而不是从零学起；Roadmap 里列的真实 API 接入、完整 MCP 项目、更大规模评测是明确的下一步，说明我知道当前边界在哪。 |
| 只用 mock 数据，怎么证明能接入真实场景？ | 工具层已经按“任何调用方都能用”的 schema 设计（MCP-style），接入真实 API 只需要替换 `search_flights` 内部实现，不需要改动 LangGraph 图结构或上层接口，这是当初设计数据模型和工具接口时就考虑到的。 |
| 如果 LLM 幻觉导致解析错误怎么办？ | 用 Pydantic 做结构化输出校验，校验失败触发重试；同时评测集里专门测参数提取正确率，这个指标就是用来量化这个风险的，不是假设它不存在。 |
| Token 成本有没有优化？ | 当前版本的重点是先把功能和评测做对；`eval/results.md` 里的平均 Token 成本就是用于后续优化的基线，比如后续可以尝试更小的模型做 `parse_input`、更大的模型只用在需要生成自然语言解释的节点。 |
| 和网上很多“调用 API 查机票”的 Demo 有什么区别？ | 区别在于把“LLM 该做什么、不该做什么”的边界讲清楚了：所有涉及金额、排序、去重的逻辑都不经过 LLM；同时有真实评测集和确定性逻辑的单元测试，不是一个只能演示 happy path 的脚本。 |
| 为什么不做前端？ | 一天时间优先级放在 Agent 核心能力和评测的真实性上；FastAPI 自带的 Swagger UI 已经能满足现场演示需求，前端属于锦上添花，列在 Roadmap 里。 |

## 4. 指标口径与复现方法

第 1 节里的数字来自 2026-09-14 用 `deepseek-flash` 跑的一次 `python -m eval.run_eval`，完整记录见 `eval/results.md`（20 个场景逐条通过情况也在里面）。如果换了模型、改了 prompt 或加了新场景，**必须重新跑一遍再更新这里**，不能沿用旧数字。

| 指标 | 含义 | 计算方式 |
|---|---|---|
| 参数提取正确率 | 20 个场景中，合并后的 `request` 字段是否符合场景预期 | `run_eval.py` 逐场景用 `field_matches` 校验 `expected_fields` |
| 工具调用成功率 | 在“预期会走到 `search_flights`”的场景里（即预期状态不是 `clarification`），实际状态也确实是 `results`/`error`（而不是卡住或异常）的比例 | 分母是 expected_status != clarification 的场景数，不是全部 20 个 |
| 端到端任务完成率 | 状态匹配预期 **且** 字段匹配预期 **且**（若场景定义了 `expected_results`）实际选中的航班/档位也匹配预期的场景占比 | `status_ok and fields_ok and results_ok`——`results_ok` 是校验真实业务结果（比如 `cheapest.outbound.flight_id`）的部分，不只是状态码 |
| 平均响应时间 / 平均 Token 成本 | 每次 `run_agent()` 调用的耗时与 LLM `usage.total_tokens` | 20 次取平均 |

如果之后场景数或分母定义又调整了（比如加了新场景类型），记得同步改这张表，不要让文档和 `eval/run_eval.py` 的实际实现脱节。

如果某次重新评测出现不通过的场景，**如实记录，不要为了让指标好看而删掉不利场景或悄悄放宽断言**——这次经历了两轮"发现真实 bug、修复、重新验证"才到 100%（10 场景时的 60%/80%，以及扩到 20 场景加上业务结果校验后暴露的往返 bug，见上一节），这个过程本身就是最有说服力的部分，比一次性 100% 更值得写进面试话术。

## 5. 使用提醒

- 简历和面试里出现的任何数字，必须能在 `eval/results.md` 里找到对应的真实记录，讲不出数字是怎么测出来的，比没有数字更糟糕。
- 如果面试官要求现场跑一遍，确保 README「快速开始」的命令在你自己的机器上确实能跑通，这是这份文档存在的另一个前提。

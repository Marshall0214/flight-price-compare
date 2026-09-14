| 指标 | 数值 | 测量时间 | 模型 |
|---|---|---|---|
| 参数提取正确率 | 100.0% | 2026-09-14T16:35:56 | deepseek-flash |
| 工具调用成功率 | 100.0% | 2026-09-14T16:35:56 | deepseek-flash |
| 端到端任务完成率 | 100.0% | 2026-09-14T16:35:56 | deepseek-flash |
| 平均响应时间 | 3749ms | 2026-09-14T16:35:56 | deepseek-flash |
| 平均 Token 成本 | 602 tokens/请求 | 2026-09-14T16:35:56 | deepseek-flash |

| # | 场景 | 预期状态 | 实际状态 | 通过 |
|---|---|---|---|---|
| 1 | 正常单程查询（信息完整） | results | results | PASS |
| 2 | 正常往返查询（信息完整） | results | results | PASS |
| 3 | 缺出发地 | clarification | clarification | PASS |
| 4 | 缺目的地 | clarification | clarification | PASS |
| 5 | 缺日期 | clarification | clarification | PASS |
| 6 | 模糊/弹性日期 | results | results | PASS |
| 7 | 错误机场代码 | error | error | PASS |
| 8 | 无符合条件结果 | error | error | PASS |
| 9 | 用户中途修改条件 | error | error | PASS |
| 10 | 特殊偏好组合（避免红眼 + 20kg行李） | results | results | PASS |

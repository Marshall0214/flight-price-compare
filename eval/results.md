| 指标 | 数值 | 测量时间 | 模型 |
|---|---|---|---|
| 参数提取正确率 | 100.0% | 2026-09-14T16:52:07 | deepseek-flash |
| 工具调用成功率 | 100.0% | 2026-09-14T16:52:07 | deepseek-flash |
| 端到端任务完成率 | 100.0% | 2026-09-14T16:52:07 | deepseek-flash |
| 平均响应时间 | 4540ms | 2026-09-14T16:52:07 | deepseek-flash |
| 平均 Token 成本 | 770 tokens/请求 | 2026-09-14T16:52:07 | deepseek-flash |

| # | 场景 | 预期状态 | 实际状态 | 通过 |
|---|---|---|---|---|
| 1 | 正常单程查询（信息完整） | results | results | PASS |
| 2 | 正常往返查询（信息完整，真正搜索回程） | results | results | PASS |
| 3 | 缺出发地 | clarification | clarification | PASS |
| 4 | 缺目的地 | clarification | clarification | PASS |
| 5 | 缺日期 | clarification | clarification | PASS |
| 6 | 模糊/弹性日期（上旬） | results | results | PASS |
| 7 | 错误机场代码 | error | error | PASS |
| 8 | 无符合条件结果（新加坡完全没有航班数据） | error | error | PASS |
| 9 | 用户中途修改目的地（改后确实有航班） | results | results | PASS |
| 10 | 特殊偏好组合（避免红眼 + 20kg行李） | results | results | PASS |
| 11 | 直接用机场代码而非城市名查询 | results | results | PASS |
| 12 | 行李21公斤，验证按20kg一档向上取整 | results | results | PASS |
| 13 | 不带行李（0kg） | results | results | PASS |
| 14 | 明确接受红眼航班，验证红眼可以赢得最便宜档 | results | results | PASS |
| 15 | 往返 + 避免红眼组合 | results | results | PASS |
| 16 | 往返查询但回程日期没有航班数据 | error | error | PASS |
| 17 | 新目的地：曼谷单程查询（验证USD换算） | results | results | PASS |
| 18 | 曼谷往返查询 | results | results | PASS |
| 19 | 模糊日期（下旬） | results | results | PASS |
| 20 | 一次性缺两个必要字段，用户一轮补全 | results | results | PASS |

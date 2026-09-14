"""跑固定的 10 场景评测集，输出 4 项真实指标到 eval/results.md。

用法:
    python -m eval.run_eval

需要先在 .env（或环境变量）里配置好 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，
否则会直接报错退出——不允许在没有真实调用的情况下编造指标。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph import run_agent  # noqa: E402
from src.tools.airport_codes import CITY_TO_AIRPORTS  # noqa: E402

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.md"


NON_EMPTY = "<non_empty>"  # expected_results 里用这个哨兵值表示"只要非空就行，不比较具体内容"


def field_matches(expected, actual) -> bool:
    if expected == NON_EMPTY:
        return bool(actual)
    if actual is None:
        return False
    if expected == actual:
        return True
    if isinstance(expected, str) and isinstance(actual, str):
        codes = CITY_TO_AIRPORTS.get(expected, [])
        return actual.upper() in codes or expected in actual
    return False


def _get_path(data: dict | None, dotted_path: str):
    """按 'cheapest.outbound.flight_id' 这样的路径从嵌套 dict 里取值，取不到返回 None。"""
    node = data or {}
    for key in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def run_scenario(scenario: dict) -> dict:
    known_fields: dict | None = None
    pending_confirmation: dict | None = None
    result: dict = {}
    elapsed_list: list[float] = []
    tokens_list: list[float] = []

    for turn in scenario["turns"]:
        result = run_agent(turn, known_fields, pending_confirmation)
        elapsed_list.append(result["metrics"].get("total_elapsed_s", 0.0))
        for call in result["metrics"].get("llm_calls", []):
            usage = call.get("usage") or {}
            tokens_list.append(usage.get("total_tokens", 0))
        known_fields = result.get("request")
        pending_confirmation = result.get("pending_confirmation")

    status_ok = result.get("status") == scenario["expected_status"]

    fields_ok = True
    for field, expected in scenario.get("expected_fields", {}).items():
        actual = (result.get("request") or {}).get(field)
        fields_ok = fields_ok and field_matches(expected, actual)

    # expected_results 校验的是真正的业务结果（比如哪趟航班赢得了 cheapest，
    # 或者失败原因具体是哪种 error_code），不只是状态码——这是让评测集不止
    # "跑通"而是"结果对"的关键。路径从完整的 result 出发，比如
    # "results.cheapest.outbound.flight_id" 或 "error.error_code"。
    results_ok = True
    for dotted_path, expected in scenario.get("expected_results", {}).items():
        actual = _get_path(result, dotted_path)
        results_ok = results_ok and field_matches(expected, actual)

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "expected_status": scenario["expected_status"],
        "actual_status": result.get("status"),
        "status_ok": status_ok,
        "fields_ok": fields_ok,
        "results_ok": results_ok,
        "task_completed": status_ok and fields_ok and results_ok,
        "avg_elapsed_s": statistics.mean(elapsed_list) if elapsed_list else 0.0,
        "avg_tokens": statistics.mean(tokens_list) if tokens_list else 0.0,
    }


def main() -> None:
    if not os.environ.get("LLM_API_KEY"):
        print("未检测到 LLM_API_KEY。请先 `cp .env.example .env` 并填入真实 key，再运行评测。")
        sys.exit(1)

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    rows = [run_scenario(s) for s in scenarios]

    param_extraction_rate = sum(r["fields_ok"] for r in rows) / len(rows)
    completion_rate = sum(r["task_completed"] for r in rows) / len(rows)

    # 工具调用成功率只在"预期会走到 search_flights"的场景里统计（expected_status != clarification）；
    # 缺参数触发追问的场景根本不会调用工具，不应该拉低这个指标的分母。
    needs_tool_call = [r for r in rows if r["expected_status"] != "clarification"]
    tool_call_rate = (
        sum(1 for r in needs_tool_call if r["actual_status"] in ("results", "error")) / len(needs_tool_call)
        if needs_tool_call
        else 0.0
    )
    avg_latency_ms = statistics.mean(r["avg_elapsed_s"] for r in rows) * 1000
    avg_tokens = statistics.mean(r["avg_tokens"] for r in rows)

    model = os.environ.get("LLM_MODEL", "unknown")
    measured_at = datetime.now().isoformat(timespec="seconds")

    summary_table = f"""| 指标 | 数值 | 测量时间 | 模型 |
|---|---|---|---|
| 参数提取正确率 | {param_extraction_rate * 100:.1f}% | {measured_at} | {model} |
| 工具调用成功率 | {tool_call_rate * 100:.1f}% | {measured_at} | {model} |
| 端到端任务完成率 | {completion_rate * 100:.1f}% | {measured_at} | {model} |
| 平均响应时间 | {avg_latency_ms:.0f}ms | {measured_at} | {model} |
| 平均 Token 成本 | {avg_tokens:.0f} tokens/请求 | {measured_at} | {model} |
"""

    detail_lines = ["", "| # | 场景 | 预期状态 | 实际状态 | 通过 |", "|---|---|---|---|---|"]
    for r in rows:
        passed = "PASS" if r["task_completed"] else "FAIL"
        detail_lines.append(
            f"| {r['id']} | {r['name']} | {r['expected_status']} | {r['actual_status']} | {passed} |"
        )

    RESULTS_PATH.write_text(summary_table + "\n".join(detail_lines) + "\n", encoding="utf-8")
    print(summary_table)
    print(f"详细结果已写入 {RESULTS_PATH}")


if __name__ == "__main__":
    main()

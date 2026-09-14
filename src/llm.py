"""LLM 调用的薄封装。

不锁定具体厂商：只要是 OpenAI-compatible 接口，改 .env 里的
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 即可切换（OpenAI 官方、
DeepSeek、Moonshot、智谱、通义千问等大多兼容这套接口）。
"""
from __future__ import annotations

import json
import os

from openai import OpenAI


def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("LLM_API_KEY", "not-set"),
        base_url=os.environ.get("LLM_BASE_URL") or None,
    )


def get_model() -> str:
    return os.environ.get("LLM_MODEL", "gpt-4o-mini")


def chat_json(system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
    """要求模型返回一个 JSON 对象。返回 (解析后的 dict, usage 信息 dict)。"""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    usage = response.usage.model_dump() if response.usage else {}
    return json.loads(content), usage


def chat_text(system_prompt: str, user_prompt: str) -> tuple[str, dict]:
    """要求模型返回一段自然语言文本。返回 (文本, usage 信息 dict)。"""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    usage = response.usage.model_dump() if response.usage else {}
    return response.choices[0].message.content or "", usage

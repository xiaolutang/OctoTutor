"""评估脚本共享工具函数"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import dotenv_values


def get_llm_config() -> dict[str, str]:
    """从 .env / 环境变量读取 LLM 配置"""
    env = dotenv_values(".env")

    def _conf(key: str, default: str = "") -> str:
        return env.get(key, "") or os.environ.get(key, default)

    return {
        "api_key": _conf("NEWAPI_API_KEY"),
        "base_url": _conf("NEWAPI_BASE_URL", "http://localhost:13000/v1"),
        "model": _conf("LLM_MODEL", "glm-5.1"),
        "dashscope_key": _conf("DASHSCOPE_API_KEY"),
    }


def get_llm_config_value(key: str, default: str = "") -> str:
    """读取单个 LLM 配置值"""
    return get_llm_config().get(key, default)


def strip_markdown_json(content: str) -> str:
    """从 LLM 输出中剥离 markdown 代码块包裹"""
    if "```json" in content:
        return content.split("```json")[1].split("```")[0].strip()
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content.strip()


def call_llm_json(prompt: str, llm_config: dict[str, str], max_tokens: int = 500) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 输出（用于 Judge 评分）"""
    import httpx

    try:
        resp = httpx.post(
            f"{llm_config['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {llm_config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": llm_config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(strip_markdown_json(content))
    except Exception as e:
        return {
            "score": 0,
            "assertions": [False, False, False],
            "reasoning": f"LLM error: {e}",
            "error": str(e),
        }

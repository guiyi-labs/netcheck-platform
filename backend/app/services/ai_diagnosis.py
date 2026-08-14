"""AI 辅助诊断：调用 OpenAI 兼容的 chat/completions 接口，为诊断结论生成增强建议。

- 未启用（NETCHECK_AI_DIAGNOSIS_ENABLED）或未配置 base_url/api_key 时 return None，
  调用方展示静态建议即可；
- 任何网络/解析异常都不抛出，而是返回 error 摘要；
- 与巡检主链路完全解耦（由用户显式触发）。
"""
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("netcheck.ai")


def enhance_diagnosis(diagnosis: dict) -> dict | None:
    """为单条诊断记录生成 AI 增强建议。

    参数 diagnosis 至少含：asset_name/ip/check_type/fault_type/level/evidence/suggestion/advice。
    """
    if not settings.ai_diagnosis_enabled or not settings.ai_base_url or not settings.ai_api_key:
        return None

    evidence = (diagnosis.get("evidence") or "").strip()
    suggestion = (diagnosis.get("suggestion") or "").strip()
    asset_name = diagnosis.get("asset_name") or f"资产 #{diagnosis.get('asset_id', '')}"
    ip = diagnosis.get("ip") or ""
    prompt = (
        "你是一名资深网络运维工程师。请基于以下巡检诊断结论，给出不超过 150 字的"
        "进一步排查建议（按可能性排序，说明原因并给出可执行命令）。只输出建议正文，不要标题。\n\n"
        f"资产：{asset_name}（{ip}）\n"
        f"检测类型：{diagnosis.get('check_type') or '-'}\n"
        f"故障类型：{diagnosis.get('fault_type') or '-'}\n"
        f"等级：{diagnosis.get('level') or '-'}\n"
        f"诊断依据：{evidence or '（无）'}\n"
        f"平台建议：{suggestion or '（无）'}"
    )
    payload = {
        "model": settings.ai_model or "default",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 400,
    }
    try:
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            timeout=settings.ai_timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"].strip()
        return {
            "status": "ok",
            "model": body.get("model") or settings.ai_model,
            "content": content,
        }
    except Exception as exc:
        logger.warning("AI 诊断增强失败: %s", exc)
        return {"status": "error", "message": str(exc)}
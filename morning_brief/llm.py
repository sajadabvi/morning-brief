"""Ollama client + the local council used for relevance/materiality filtering.

Council design (bounded context by construction):
- Every article is judged in its own tiny prompt (title + snippet only),
  never batched into one giant prompt, so context can never overflow no
  matter how many articles a day brings.
- Stage A (triage): the small model scores relevance/importance for every
  article - cheap, tuned for recall.
- Stage B (verdict): the large model re-judges only triage survivors -
  expensive, tuned for precision.
An article is "material" only if both models agree, i.e. a unanimous
two-model council vote.
"""

import json
import re
from typing import Any

import httpx

from .config import Config


def ollama_chat(cfg: Config, model: str, prompt: str, timeout: float | None = None) -> str:
    llm = cfg["llm"]
    resp = httpx.post(
        f"{llm['ollama_url']}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=timeout or llm["request_timeout"],
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _parse_json(text: str) -> dict[str, Any] | None:
    # Models sometimes wrap JSON in prose or code fences; extract first object.
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


JUDGE_PROMPT = """You are screening financial news for a portfolio digest about {subject}.

Article title: {title}
Article snippet: {snippet}

Judge this article:
1. related: is it actually about {subject} or something that materially affects it?
2. importance: 1-5, where 1 = noise/routine, 3 = notable, 5 = major market-moving news.

Answer with ONLY a JSON object, no other text:
{{"related": true/false, "importance": 1-5, "reason": "<10 words max>"}}"""


def judge_article(cfg: Config, model: str, subject: str, article: dict[str, Any]) -> dict[str, Any]:
    prompt = JUDGE_PROMPT.format(
        subject=subject,
        title=article["title"],
        snippet=article["snippet"] or "(no snippet)",
    )
    try:
        verdict = _parse_json(ollama_chat(cfg, model, prompt))
    except Exception as e:
        print(f"    judge error ({model}): {e}")
        verdict = None
    if not verdict:
        # Unparseable/failed judgment: keep the article rather than silently
        # dropping potentially material news; the other council member and
        # the writer stage still bound the final volume.
        return {"related": True, "importance": 3, "reason": "judge failed, kept"}
    return {
        "related": bool(verdict.get("related", False)),
        "importance": int(verdict.get("importance", 1)),
        "reason": str(verdict.get("reason", ""))[:80],
    }


def council_filter(cfg: Config, subject: str, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two-stage council vote. Returns only material articles, each annotated."""
    llm = cfg["llm"]
    min_imp = int(llm["triage_min_importance"])
    kept = []
    for a in articles:
        triage = judge_article(cfg, llm["triage_model"], subject, a)
        if not (triage["related"] and triage["importance"] >= min_imp):
            continue
        verdict = judge_article(cfg, llm["judge_model"], subject, a)
        if verdict["related"] and verdict["importance"] >= min_imp:
            kept.append({**a, "importance": verdict["importance"], "why": verdict["reason"]})
    kept.sort(key=lambda a: -a["importance"])
    return kept

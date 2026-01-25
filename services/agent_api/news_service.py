import re
import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
import feedparser

# -----------------------------
# Free sources (no registration)
# -----------------------------
RSS_SOURCES = [
    ("OpenAI", "https://openai.com/news/rss.xml", "Official"),
    ("DeepMind", "https://deepmind.google/blog/feed/basic", "Research"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "Open Source"),
    ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", "MLOps"),
    ("Microsoft Foundry", "https://devblogs.microsoft.com/foundry/feed/", "Enterprise"),
    # Anthropic RSS can be inconsistent; keep optional and non-fatal:
    ("Anthropic", "https://www.anthropic.com/news/rss.xml", "Official"),
]

HN_URL = "https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage=25"

AI_KEYWORDS = [
    "ai", "llm", "openai", "gpt", "claude", "anthropic", "gemini", "deepmind",
    "mistral", "hugging face", "transformer", "rag", "agentic", "multimodal",
    "inference", "alignment", "safety", "eval", "evals", "rlhf", "prompt",
    "foundation model", "model release"
]

# Calm / etheric guardrails: drop hype language
DROP_PATTERNS = [
    r"\bdoom\b", r"\bpanic\b", r"\bdestroy\b", r"\bapocalypse\b", r"\bterrifying\b",
    r"\breplaces all jobs\b", r"\bend of\b", r"\bsingularity\b"
]

MAX_ITEMS = 18
DAYS_BACK = 7

# In-memory cache (simple + low-cost)
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _hash_id(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]*>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_relevant(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in AI_KEYWORDS)


def _is_noisy(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in DROP_PATTERNS)


def _parse_feed_dt(entry: Any) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None)
        if val:
            try:
                return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
            except Exception:
                continue
    return None


async def _fetch_rss(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

    for source_name, url, tag in RSS_SOURCES:
        try:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            for e in (feed.entries or [])[:25]:
                title = _strip_html(getattr(e, "title", "") or "")
                link = (getattr(e, "link", "") or "").strip()
                summary = _strip_html(getattr(e, "summary", "") or "")

                if not title or not link:
                    continue

                blob = f"{title} {summary}"
                if not _is_relevant(blob) or _is_noisy(blob):
                    continue

                dt = _parse_feed_dt(e)
                if dt and dt < cutoff:
                    continue

                items.append({
                    "id": _hash_id(link),
                    "title": title[:180],
                    "url": link,
                    "summary": summary[:260],
                    "source": source_name,
                    "tag": tag,
                    "publishedAt": dt.astimezone().isoformat() if dt else None,
                })
        except Exception:
            # Calm failure: ignore per-source errors
            continue

    return items


async def _fetch_hn(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

    query = " OR ".join([
        "AI", "LLM", "OpenAI", "Anthropic", "Claude", "Gemini", "DeepMind",
        "Mistral", "Hugging Face", "RAG", "agentic", "alignment", "inference"
    ])

    try:
        url = HN_URL.format(q=httpx.QueryParams({"q": query})["q"])
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = (data.get("hits") or [])[:25]

        for h in hits:
            title = (h.get("title") or "").strip()
            link = (h.get("url") or "").strip()
            created = h.get("created_at")

            if not title or not link:
                continue
            if not _is_relevant(title) or _is_noisy(title):
                continue

            published_at = None
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                    published_at = dt.astimezone().isoformat()
                except Exception:
                    pass

            items.append({
                "id": _hash_id(link),
                "title": title[:180],
                "url": link,
                "summary": "",
                "source": "Hacker News",
                "tag": "Community Signal",
                "publishedAt": published_at,
            })
    except Exception:
        pass

    return items


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        u = (it.get("url") or "").strip().lower()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out


def _sort(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(it: Dict[str, Any]) -> str:
        return it.get("publishedAt") or ""
    return sorted(items, key=key, reverse=True)


async def get_latest_news() -> Dict[str, Any]:
    now = time.time()
    if _CACHE["payload"] is not None and (now - _CACHE["ts"] < CACHE_TTL_SECONDS):
        return _CACHE["payload"]

    async with httpx.AsyncClient(headers={"User-Agent": "llm-sre-site-ai-news/1.0"}) as client:
        rss_items = await _fetch_rss(client)
        hn_items = await _fetch_hn(client)

    combined = _dedupe(_sort(rss_items + hn_items))[:MAX_ITEMS]
    payload = {"updatedAt": _now_iso(), "items": combined}

    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return payload
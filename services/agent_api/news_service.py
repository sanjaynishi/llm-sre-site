"""
news_service.py

AI News (RSS + HN Algolia) with:
- keyword filtering (expanded for GPU / models / infra / partnerships)
- mild "no-hype" drop patterns
- dedupe + sort
- cache w/ TTL
- safe error reporting (never crashes endpoint)
- optional extra RSS sources via env: NEWS_EXTRA_RSS

Exports:
- handle_get_news_latest(event) -> dict (json_response)
- handle_get_debug_news(event) -> dict (json_response)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from core.response import json_response

# =====================
# Config (env)
# =====================

NEWS_ENABLED = os.environ.get("NEWS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
NEWS_MAX_ITEMS = int(os.environ.get("NEWS_MAX_ITEMS", "18"))
NEWS_DAYS_BACK = int(os.environ.get("NEWS_DAYS_BACK", "7"))
NEWS_CACHE_TTL_SEC = int(os.environ.get("NEWS_CACHE_TTL_SEC", str(6 * 60 * 60)))

# Optional: add feeds without redeploy
# Format:
#   NEWS_EXTRA_RSS="Name|https://feed.url|Tag,Name2|https://feed2|Tag2"
NEWS_EXTRA_RSS = os.environ.get("NEWS_EXTRA_RSS", "").strip()

RSS_SOURCES: List[Tuple[str, str, str]] = [
    ("OpenAI", "https://openai.com/news/rss.xml", "Official"),
    ("DeepMind", "https://deepmind.google/blog/feed/basic", "Research"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "Open Source"),
    ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", "MLOps"),
    ("Microsoft Foundry", "https://devblogs.microsoft.com/foundry/feed/", "Enterprise"),

    # GPU / Infra coverage
    ("NVIDIA Developer Blog", "https://developer.nvidia.com/blog/feed/", "GPU/Infra"),
    ("NVIDIA Newsroom", "https://nvidianews.nvidia.com/rss.xml", "GPU/Infra"),
]

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage=25"

# Broader scope: GPU, models, infra, partnerships (e.g., “AWS contract with OpenAI”)
AI_KEYWORDS = [
    # Core AI
    "ai", "llm", "openai", "gpt", "claude", "anthropic", "gemini", "deepmind",
    "mistral", "hugging face", "transformer", "rag", "agentic", "multimodal",
    "inference", "training", "serving", "alignment", "safety", "eval", "evals", "rlhf",

    # GPU / acceleration
    "gpu", "nvidia", "cuda", "tensor", "h100", "h200", "b200", "blackwell",
    "dgx", "gb200", "datacenter", "cluster",

    # Cloud / platforms / partnerships
    "aws", "bedrock", "azure", "gcp", "oracle", "coreweave",
    "partnership", "contract", "deal", "capacity",
]

# Calm guardrails: drop overly-hype phrasing
DROP_PATTERNS = [
    r"\bdoom\b",
    r"\bpanic\b",
    r"\bdestroy\b",
    r"\bapocalypse\b",
    r"\bterrifying\b",
    r"\breplaces all jobs\b",
    r"\bend of\b",
    r"\bsingularity\b",
]

_DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 aimlsre-news/1.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

_news_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}


# =====================
# Utilities
# =====================

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]*>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_relevant(text: str) -> bool:
    t = (text or "").lower()
    if not any(k in t for k in AI_KEYWORDS):
        return False
    if any(re.search(p, t) for p in DROP_PATTERNS):
        return False
    return True


def _http_get_text(url: str, timeout_sec: int = 10) -> str:
    req = urllib.request.Request(url, headers=_DEFAULT_HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        detail = (detail[:600] + "...") if len(detail) > 600 else detail
        raise RuntimeError(f"HTTP {e.code} GET {url} :: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error GET {url} :: {e}") from e


def _http_get_json(url: str, timeout_sec: int = 10) -> dict:
    return json.loads(_http_get_text(url, timeout_sec=timeout_sec))


def _parse_extra_rss_sources(env_val: str) -> List[Tuple[str, str, str]]:
    """
    NEWS_EXTRA_RSS="Name|URL|Tag,Name2|URL2|Tag2"
    Returns list of (name,url,tag). Ignores invalid entries.
    """
    out: List[Tuple[str, str, str]] = []
    if not env_val:
        return out
    for chunk in env_val.split(","):
        chunk = (chunk or "").strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) < 2:
            continue
        name = parts[0] or "Extra"
        url = parts[1]
        tag = parts[2] if len(parts) >= 3 and parts[2] else "Extra"
        if url.startswith("http://") or url.startswith("https://"):
            out.append((name, url, tag))
    return out


def _rss_sources_all() -> List[Tuple[str, str, str]]:
    # Default sources + optional extras via env var
    extra = _parse_extra_rss_sources(NEWS_EXTRA_RSS)
    return RSS_SOURCES + extra


def _parse_rss_date(pub: str) -> str | None:
    pub = (pub or "").strip()
    if not pub:
        return None

    fmts = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(pub, f)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().isoformat()
        except Exception:
            continue

    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return dt.astimezone().isoformat()
    except Exception:
        return None


def _parse_rss(xml_text: str, source_name: str, tag: str) -> List[dict]:
    items: List[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS_BACK)

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items

    for it in root.findall(".//item"):
        title = _strip_html((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        desc = _strip_html((it.findtext("description") or "").strip())

        if not title or not link:
            continue

        blob = f"{title} {desc}"
        if not _is_relevant(blob):
            continue

        published_at = None
        pub = (it.findtext("pubDate") or "").strip()
        if pub:
            iso = _parse_rss_date(pub)
            if iso:
                try:
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                    published_at = dt.astimezone().isoformat()
                except Exception:
                    published_at = iso

        items.append(
            {
                "id": link[-16:] if len(link) > 16 else link,
                "title": title[:180],
                "url": link,
                "summary": desc[:260],
                "source": source_name,
                "tag": tag,
                "publishedAt": published_at,
            }
        )

    return items


def _dedupe(items: List[dict]) -> List[dict]:
    seen = set()
    out: List[dict] = []
    for it in items:
        u = (it.get("url") or "").strip().lower()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out


def _sort(items: List[dict]) -> List[dict]:
    def _k(it: dict) -> str:
        return it.get("publishedAt") or ""
    return sorted(items, key=_k, reverse=True)


def _fetch_rss_items_with_errors() -> Tuple[List[dict], List[dict]]:
    out: List[dict] = []
    errors: List[dict] = []
    for source_name, url, tag in _rss_sources_all():
        try:
            xml_text = _http_get_text(url, timeout_sec=10)
            out.extend(_parse_rss(xml_text, source_name, tag))
        except Exception as e:
            errors.append({"source": source_name, "url": url, "error": str(e)[:400]})
    return out, errors


def _hn_query() -> str:
    # Broader than before; catches GPU/models/cloud partnership posts
    terms = [
        "AI", "LLM", "OpenAI", "Anthropic", "Claude", "Gemini", "DeepMind", "Mistral",
        "RAG", "agentic",
        "NVIDIA", "GPU", "H100", "H200", "Blackwell", "CUDA",
        "inference", "training", "datacenter", "cluster",
        "CoreWeave", "Bedrock", "AWS", "Azure", "GCP",
        "partnership", "contract", "deal",
    ]
    return " OR ".join(terms)


def _fetch_hn_items_with_errors() -> Tuple[List[dict], List[dict]]:
    out: List[dict] = []
    errors: List[dict] = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS_BACK)
    query = _hn_query()

    try:
        url = HN_ALGOLIA.format(q=urllib.parse.quote(query))
        data = _http_get_json(url, timeout_sec=10)
        hits = (data.get("hits") or [])[:25]

        for h in hits:
            title = (h.get("title") or "").strip()
            link = (h.get("url") or "").strip()
            created = h.get("created_at")

            if not title or not link:
                continue
            if not _is_relevant(title):
                continue

            published_at = None
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                    published_at = dt.astimezone().isoformat()
                except Exception:
                    pass

            out.append(
                {
                    "id": link[-16:] if len(link) > 16 else link,
                    "title": title[:180],
                    "url": link,
                    "summary": "",
                    "source": "Hacker News",
                    "tag": "Community Signal",
                    "publishedAt": published_at,
                }
            )

    except Exception as e:
        errors.append({"source": "Hacker News", "url": "hn.algolia.com", "error": str(e)[:400]})

    return out, errors


def get_news_latest_payload(force_refresh: bool = False) -> dict:
    """
    Returns payload dict:
      { updatedAt, items, errors }
    Uses in-memory cache per Lambda container.
    """
    if not NEWS_ENABLED:
        return {"updatedAt": _now_iso(), "items": [], "disabled": True}

    now = time.time()
    if (
        not force_refresh
        and _news_cache["payload"] is not None
        and (now - float(_news_cache["ts"])) < NEWS_CACHE_TTL_SEC
    ):
        return _news_cache["payload"]

    rss_items, rss_errors = _fetch_rss_items_with_errors()
    hn_items, hn_errors = _fetch_hn_items_with_errors()

    items = _dedupe(_sort(rss_items + hn_items))[:NEWS_MAX_ITEMS]
    payload = {
        "updatedAt": _now_iso(),
        "items": items,
        "errors": (rss_errors + hn_errors)[:20],
    }

    _news_cache["ts"] = now
    _news_cache["payload"] = payload
    return payload


def get_debug_news_payload() -> dict:
    rss_items, rss_errors = _fetch_rss_items_with_errors()
    hn_items, hn_errors = _fetch_hn_items_with_errors()

    return {
        "ok": True,
        "updatedAt": _now_iso(),
        "rss_count": len(rss_items),
        "hn_count": len(hn_items),
        "sources_total": len(_rss_sources_all()),
        "extra_rss_enabled": bool(NEWS_EXTRA_RSS),
        "errors": (rss_errors + hn_errors),
        "sample_titles": [x.get("title") for x in (rss_items + hn_items)[:5]],
    }


# =====================
# Handlers (return API GW proxy response)
# =====================

def handle_get_news_latest(event: dict) -> dict:
    return json_response(event, 200, get_news_latest_payload())


def handle_get_debug_news(event: dict) -> dict:
    return json_response(event, 200, get_debug_news_payload())
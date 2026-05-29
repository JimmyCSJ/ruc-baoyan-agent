"""Primary web retrieval via Web Access CDP proxy; legacy web_search is fallback only."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from graph.state import RetrievedDoc


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _cfg() -> Dict[str, Any]:
    return {
        "enabled": _env_bool("WEB_ACCESS_PRIMARY", True),
        "proxy_url": os.getenv("WEB_ACCESS_PROXY_URL", "http://localhost:3456").rstrip("/"),
        "timeout_s": float(os.getenv("WEB_ACCESS_TIMEOUT_S", "14")),
        "max_pages": int(os.getenv("WEB_ACCESS_MAX_PAGES", "3")),
    }


def _query_variants(query: str) -> List[Tuple[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    short = q[:32]
    items: List[Tuple[str, str]] = [
        ("web_access_general", q),
        ("web_access_official", f"{short} site:ruc.edu.cn"),
        ("web_access_zhihu", f"{short} site:zhihu.com"),
        ("web_access_wechat", f"{short} site:mp.weixin.qq.com"),
        ("web_access_xhs", f"{short} site:xiaohongshu.com"),
    ]
    return items


def web_access_healthcheck() -> Tuple[bool, str]:
    cfg = _cfg()
    if not cfg["enabled"]:
        return False, "web_access_disabled_by_env"
    try:
        import httpx
    except Exception:
        return False, "httpx_not_available"
    try:
        with httpx.Client(timeout=httpx.Timeout(cfg["timeout_s"])) as client:
            r = client.get(f"{cfg['proxy_url']}/targets")
            if r.status_code >= 400:
                return False, f"proxy_http_{r.status_code}"
            return True, "ok"
    except Exception as exc:
        return False, f"proxy_unreachable:{type(exc).__name__}"


def _discover_urls(query: str, max_urls: int) -> List[Tuple[str, str, str]]:
    """Return (tag, title, href). URL discovery can still use DDG; extraction is via CDP."""
    try:
        from duckduckgo_search import DDGS
    except Exception:
        return []
    out: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    proxy = os.getenv("WEB_SEARCH_PROXY") or None
    for tag, q in _query_variants(query):
        try:
            with DDGS(proxy=proxy) as ddgs:
                raw = list(ddgs.text(q, region="cn-zh", max_results=5, backend="auto") or [])
        except Exception:
            raw = []
        for item in raw:
            href = str(item.get("href") or "").strip()
            title = str(item.get("title") or "").strip() or "(无标题)"
            if not href.startswith("http"):
                continue
            if href in seen:
                continue
            seen.add(href)
            out.append((tag, title, href))
            if len(out) >= max_urls:
                return out
    return out


def _extract_text_via_cdp(url: str) -> Tuple[str, str]:
    """Navigate with /new then extract main text with /eval. Returns (text, detail_reason)."""
    cfg = _cfg()
    try:
        import httpx
    except Exception:
        return "", "httpx_not_available"
    js = (
        "(() => {"
        "const pick = (sel) => { const el = document.querySelector(sel); return el ? (el.innerText || '').trim() : ''; };"
        "const cands = [pick('main'), pick('article'), pick('#content'), pick('.content'), pick('body')].filter(Boolean);"
        "let text = cands.sort((a,b)=>b.length-a.length)[0] || '';"
        "text = text.replace(/\\s+/g, ' ').trim();"
        "return text.slice(0, 4500);"
        "})()"
    )
    target_id = ""
    try:
        with httpx.Client(timeout=httpx.Timeout(cfg["timeout_s"])) as client:
            r_new = client.get(f"{cfg['proxy_url']}/new", params={"url": url})
            r_new.raise_for_status()
            payload = r_new.json()
            target_id = str(payload.get("id") or payload.get("targetId") or payload.get("target") or "")
            if not target_id:
                return "", "proxy_new_missing_target_id"
            r_eval = client.post(f"{cfg['proxy_url']}/eval", params={"target": target_id}, content=js)
            r_eval.raise_for_status()
            text = r_eval.text.strip()
            # proxy implementations vary; try to unwrap simple JSON string wrappers.
            text = re.sub(r'^\s*"(.*)"\s*$', r"\1", text)
            text = text.replace("\\n", "\n")
            return text[:4500], "ok"
    except Exception as exc:
        return "", f"cdp_extract_error:{type(exc).__name__}"
    finally:
        if target_id:
            try:
                with httpx.Client(timeout=httpx.Timeout(4.0)) as client2:
                    client2.get(f"{cfg['proxy_url']}/close", params={"target": target_id})
            except Exception:
                pass


def search_web_via_web_access(query: str) -> Tuple[List[RetrievedDoc], Dict[str, Any]]:
    """Primary web retrieval path using Web Access CDP extraction."""
    ok, reason = web_access_healthcheck()
    if not ok:
        return [], {"used": False, "failure_reason": reason, "strategy": "web_access_primary"}

    cfg = _cfg()
    discovered = _discover_urls(query, max_urls=max(1, cfg["max_pages"]))
    if not discovered:
        return [], {"used": True, "failure_reason": "no_urls_discovered", "strategy": "web_access_primary"}

    docs: List[RetrievedDoc] = []
    fail_reasons: List[str] = []
    for tag, title, href in discovered[: cfg["max_pages"]]:
        body, why = _extract_text_via_cdp(href)
        if not body or len(body) < 40:
            fail_reasons.append(f"{href}|{why}")
            continue
        host = (urlparse(href).hostname or "").lower()
        source = tag
        if "zhihu.com" in host:
            source = "web_access_zhihu"
        elif "mp.weixin.qq.com" in host:
            source = "web_access_wechat"
        elif "xiaohongshu.com" in host:
            source = "web_access_xhs"
        elif "ruc.edu.cn" in host:
            source = "web_access_ruc"
        docs.append(
            {
                "source": source,
                "title": title,
                "content": f"{body}\n链接：{href}"[:4500],
                "confidence": 0.72,
                "source_group": "web",
                "kb_group": "web",
                "provenance": {"url": href, "retrieval_path": "web_access_cdp"},
                "match_score": 0.72,
            }
        )

    if docs:
        return docs, {
            "used": True,
            "failure_reason": "",
            "strategy": "web_access_primary",
            "discovered_urls": [u for _t, _ti, u in discovered],
        }
    return [], {
        "used": True,
        "failure_reason": "all_cdp_extract_failed" + (f": {fail_reasons[0]}" if fail_reasons else ""),
        "strategy": "web_access_primary",
        "discovered_urls": [u for _t, _ti, u in discovered],
    }


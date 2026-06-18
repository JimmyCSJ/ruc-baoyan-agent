"""联网检索 — 对齐 web-access 多通道思路：WebSearch(DDG) + WebFetch(HTTP) + Jina 正文.

参考: https://github.com/eze-is/web-access — Jina 将网页转为可读正文，适合知乎/微信/官网文章类页面。
CDP 浏览器需用户本机 Chrome + Proxy，见 README「与 web-access 协同」。
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from graph.state import RetrievedDoc

_MAX_DDGS_PER_CALL = 6
_MAX_TOTAL_DOCS = 18
_MAX_FETCH = int(os.getenv("WEB_SEARCH_MAX_FETCH", "3"))
_FETCH_ON = os.getenv("WEB_SEARCH_FETCH", "true").lower() == "true"
_USE_JINA = os.getenv("WEB_SEARCH_USE_JINA", "true").lower() == "true"
_SNIPPET_CONF = 0.48
_FETCH_CONF = 0.58
_JINA_CONF = 0.62

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)


def expand_query_variants(query: str) -> List[str]:
    """生成 2～5 条查询变体，提高 DDG 中文召回。"""
    q = (query or "").strip()
    if not q:
        return []
    out: List[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    add(q)
    if "中国人民大学" in q:
        add(q.replace("中国人民大学", "人大"))
    for sep in ("？", "?", "\n"):
        if sep in q:
            head = q.split(sep)[0].strip()
            if 10 <= len(head) <= 80:
                add(head)
            break
    if len(q) > 40:
        add(q[:38].rstrip() + "…")
    # 定向小红书/知乎：追加一条带 site 定向的变体
    if any(k in q for k in ("保研", "推免", "夏令营", "考研", "经验", "考核", "面试")):
        _short = _short_kw(q, 30)
        add(f"{_short} site:zhihu.com OR site:xiaohongshu.com")
    return out[:5]


def _short_kw(q: str, limit: int = 32) -> str:
    q = re.sub(r"\s+", " ", (q or "").strip())
    if len(q) <= limit:
        return q
    return q[:limit].rstrip()


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _fetch_allowed_host(hostname: str) -> bool:
    h = (hostname or "").lower()
    if not h or "xiaohongshu.com" in h:
        return False
    return any(
        x in h
        for x in (
            "zhihu.com",
            "mp.weixin.qq.com",
            "ruc.edu.cn",
            "baidu.com",
            "bing.com",
        )
    )


def _prefer_jina_first(hostname: str) -> bool:
    """与 web-access 一致：文章/文档类站点优先走 Jina 再兜底 HTTP。"""
    h = (hostname or "").lower()
    return any(x in h for x in ("zhihu.com", "mp.weixin.qq.com", "ruc.edu.cn"))


def fetch_via_jina(url: str, max_chars: int = 4500) -> str:
    """Jina Reader: https://r.jina.ai/<url>（见 web-access SKILL）。"""
    if not _USE_JINA or not url.startswith("http"):
        return ""
    try:
        import httpx
    except ImportError:
        return ""

    key = (os.getenv("JINA_API_KEY") or "").strip()
    headers: Dict[str, str] = {
        "Accept": "text/plain",
        "X-Return-Format": "text",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    jina_url = "https://r.jina.ai/" + url
    try:
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=15.0), headers=headers) as client:
            r = client.get(jina_url)
            r.raise_for_status()
            text = (r.text or "").strip()
            return text[:max_chars]
    except Exception:
        return ""


def fetch_page_excerpt(url: str, max_chars: int = 2400) -> str:
    if not url.startswith("http"):
        return ""
    try:
        import httpx
    except ImportError:
        return ""
    parsed = urlparse(url)
    if not _fetch_allowed_host(parsed.hostname or ""):
        return ""
    try:
        with httpx.Client(
            timeout=httpx.Timeout(12.0, connect=6.0),
            follow_redirects=True,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").lower()
            if "html" not in ct and "text/plain" not in ct:
                return ""
            return _strip_html(r.text)[:max_chars]
    except Exception:
        return ""


def _enrich_url(href: str, snippet: str) -> tuple[str, float]:
    """单 URL：Jina + HTTP 组合，返回 (正文, 建议 confidence)。"""
    parsed = urlparse(href)
    host = parsed.hostname or ""
    if not _fetch_allowed_host(host):
        return snippet, _SNIPPET_CONF

    jina_first = _prefer_jina_first(host)
    jina_text = ""
    http_text = ""

    if jina_first and _USE_JINA:
        jina_text = fetch_via_jina(href)
    http_text = fetch_page_excerpt(href)
    if not jina_first and _USE_JINA and len(http_text) < 200:
        jina_text = fetch_via_jina(href)

    chunks: List[str] = []
    conf = _FETCH_CONF

    if jina_text and len(jina_text) > 120:
        chunks.append("[Jina正文]\n" + jina_text)
        conf = _JINA_CONF
    if http_text and len(http_text) > 80:
        if not chunks or len(http_text) > len(jina_text) + 100:
            chunks.append("[HTTP摘录]\n" + http_text)
            if conf < _FETCH_CONF:
                conf = _FETCH_CONF

    if not chunks:
        return snippet, _SNIPPET_CONF

    body = (snippet + "\n\n" if snippet.strip() else "") + "\n\n".join(chunks)
    return body.strip(), conf


def _ddg_text(ddgs: object, q: str, max_results: int | None = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = _MAX_DDGS_PER_CALL
    for backend in ("auto", "html"):
        try:
            fn = getattr(ddgs, "text")
            raw = fn(q, region="cn-zh", max_results=max_results, backend=backend)
            if raw:
                return list(raw)
        except Exception:
            continue
    return []


def search_web_vertical(query: str, *, lite: bool = False) -> List[RetrievedDoc]:
    if not query or not query.strip():
        return []
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    variants = expand_query_variants(query)
    primary = variants[0] if variants else query
    short = _short_kw(primary)

    planned: List[Tuple[str, str]] = []
    if lite:
        planned.append(("web_general", primary))
        if any(k in query for k in ("人大", "人民大学", "中国人民大学", "RUC", "ruc")):
            planned.append(("web_ruc", f"{_short_kw(short, 28)} site:ruc.edu.cn"))
        else:
            planned.append(("web_general", f"{short} 保研"))
    else:
        for v in variants[:2]:
            planned.append(("web_general", v))
        planned.append(("web_general", f"{short} 保研"))
        planned.append(("web_zhihu", f"{_short_kw(short, 24)} site:zhihu.com"))
        planned.append(("web_wechat", f"{_short_kw(short, 24)} site:mp.weixin.qq.com"))
        planned.append(("web_xhs", f"{_short_kw(short, 20)} site:xiaohongshu.com"))
        if any(k in query for k in ("人大", "人民大学", "中国人民大学", "RUC", "ruc")):
            planned.append(("web_ruc", f"{_short_kw(short, 26)} site:ruc.edu.cn"))
            planned.append(("web_ruc", "中国人民大学 推免 site:ruc.edu.cn"))

    seen: set[str] = set()
    queue: List[Tuple[str, Dict[str, str]]] = []
    ddg_cap = 4 if lite else _MAX_DDGS_PER_CALL

    proxy = os.getenv("WEB_SEARCH_PROXY") or None
    ddgs_ok = False
    # Try with proxy first; if it fails, retry without proxy (direct connection)
    for attempt_proxy in (proxy, None):
        try:
            with DDGS(proxy=attempt_proxy) as ddgs:
                for tag, q in planned:
                    q = q.strip()
                    if not q:
                        continue
                    for item in _ddg_text(ddgs, q, ddg_cap):
                        href = (item.get("href") or "").strip()
                        title = (item.get("title") or "").strip()
                        dedupe = href or f"{title}|{q}"
                        if dedupe in seen:
                            continue
                        seen.add(dedupe)
                        queue.append((tag, item))
            ddgs_ok = True
            break
        except Exception as exc:
            import logging
            logging.warning("DDGS search failed (proxy=%s): %s", attempt_proxy, exc)
            if attempt_proxy is None:
                # Both attempts failed
                pass
    if not ddgs_ok and not queue:
        import logging
        logging.warning("DDGS search completely failed, skipping to Baidu fallback")

    docs: List[RetrievedDoc] = []
    fetch_left = 0 if lite else (_MAX_FETCH if _FETCH_ON else 0)

    for tag, item in queue:
        if len(docs) >= _MAX_TOTAL_DOCS:
            break
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "").strip()
        href = (item.get("href") or "").strip()
        if not title and not body and not href:
            continue

        content = body
        conf = _SNIPPET_CONF

        host = (urlparse(href).hostname or "").lower() if href else ""
        should_fetch = (
            fetch_left > 0
            and href.startswith("http")
            and _fetch_allowed_host(host)
            and (
                len(body) < 140
                or (_prefer_jina_first(host) and len(body) < 1200)
            )
        )
        if should_fetch:
            enriched, conf = _enrich_url(href, body)
            if enriched != body or "[Jina正文]" in enriched or "[HTTP摘录]" in enriched:
                fetch_left -= 1
                content = enriched
            else:
                content = body

        if href:
            content = (content + f"\n链接：{href}").strip() if content else f"链接：{href}"

        docs.append(
            {
                "source": tag,
                "title": title or "(无标题)",
                "content": content[:4500],
                "confidence": conf,
            }
        )

    return docs


# ---------------------------------------------------------------------------
# 百度备用通道 — DuckDuckGo 在国内常被墙，百度可直连且中文召回更好
# ---------------------------------------------------------------------------

_BAIDU_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _parse_baidu_html(html: str) -> List[Dict[str, str]]:
    """Extract title / snippet / href from Baidu result HTML."""
    results: List[Dict[str, str]] = []
    # Baidu results are in <div class="result c-container" ...>
    blocks = re.findall(
        r'<div[^>]*class="[^"]*result[^"]*c-container[^"]*"[^>]*>(.*?)'
        r'(?=<div[^>]*class="[^"]*result[^"]*c-container[^"]*"|<div[^>]*id="page")',
        html, re.DOTALL,
    )
    if not blocks:
        blocks = re.findall(
            r'<div[^>]*class="[^"]*c-container[^"]*"[^>]*>(.*?)'
            r'(?=<div[^>]*class="[^"]*c-container[^"]*"|$)',
            html, re.DOTALL,
        )
    for block in blocks:
        # Title: <h3>...<a href="...">title</a>...</h3>
        h3_m = re.search(r'<h3[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not h3_m:
            continue
        href = h3_m.group(1)
        title = re.sub(r'<[^>]+>', '', h3_m.group(2)).strip()
        # Snippet: collect text from various abstract/summary spans
        snippet_parts: List[str] = []
        for cls_pat in ['c-abstract', 'c-span-last', 'content-right_']:
            for m in re.finditer(rf'class="[^"]*{cls_pat}[^"]*"[^>]*>(.*?)</(?:span|div)>', block, re.DOTALL):
                txt = re.sub(r'<[^>]+>', ' ', m.group(1))
                txt = re.sub(r'\s+', ' ', txt).strip()
                if txt and len(txt) > 5:
                    snippet_parts.append(txt)
        snippet = " · ".join(snippet_parts)[:800]
        if href and title:
            results.append({"title": title, "body": snippet, "href": href})
    return results


def search_web_baidu(query: str, max_results: int = 8) -> List[RetrievedDoc]:
    """Search Baidu via HTTP scraping — no proxy / API key needed, excellent Chinese recall."""
    if not query or not query.strip():
        return []
    try:
        import httpx
    except ImportError:
        return []

    q = query.strip()[:200]
    all_results: List[Dict[str, str]] = []
    seen_hrefs: set[str] = set()

    # Also search RUC-specific variant
    variants = [q]
    if "中国人民大学" not in q and "人大" not in q:
        variants.append(f"中国人民大学 {q}")

    for search_q in variants:
        search_url = f"https://www.baidu.com/s?wd={search_q}&rn={min(max_results, 20)}"
        try:
            with httpx.Client(
                timeout=httpx.Timeout(15.0, connect=8.0),
                follow_redirects=True,
                headers={"User-Agent": _BAIDU_UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            ) as client:
                r = client.get(search_url)
                r.raise_for_status()
                parsed = _parse_baidu_html(r.text)
                for item in parsed:
                    href = item.get("href", "")
                    if href not in seen_hrefs:
                        seen_hrefs.add(href)
                        all_results.append(item)
        except Exception:
            continue
        if len(all_results) >= max_results:
            break

    docs: List[RetrievedDoc] = []
    for item in all_results[:max_results]:
        title = item.get("title", "(无标题)")
        body = item.get("body", "")
        href = item.get("href", "")
        content = body if body else ""
        if href:
            content = (content + f"\n链接：{href}").strip() if content else f"链接：{href}"
        docs.append({
            "source": "web_baidu",
            "title": title,
            "content": content[:4000],
            "confidence": 0.55,
            "source_group": "web",
            "kb_group": "web",
            "provenance": {"url": href, "retrieval_path": "baidu_http"},
        })
    return docs


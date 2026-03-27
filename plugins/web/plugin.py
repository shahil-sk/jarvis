"""Web plugin — fetch, summarize, extract, search, read pages via LLM.

All HTTP via stdlib urllib. HTML stripping via stdlib html.parser.
Summarization piped through the configured LLM.
"""

import json
import re
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from plugins.base import PluginBase
from core.config import get_llm_config

_MAX_CHARS = 8000   # max chars fed to LLM for summarization
_UA = "Mozilla/5.0 (compatible; Jarvis/1.0)"


# ── HTML → plain text ───────────────────────────────────────────

class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "head", "nav",
                 "footer", "aside", "form", "button", "svg", "img"}

    def __init__(self):
        super().__init__()
        self._skip  = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in ("p", "div", "li", "h1", "h2", "h3", "br", "tr"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r" {2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    ex = _TextExtractor()
    try:
        ex.feed(html)
    except Exception:
        pass
    return ex.text()


# ── HTTP fetch ─────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 12) -> tuple[str, str]:
    """Returns (raw_html_or_text, final_url). Follows redirects."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        charset = "utf-8"
        ct = r.headers.get("Content-Type", "")
        m  = re.search(r"charset=([\w-]+)", ct)
        if m:
            charset = m.group(1)
        body = r.read().decode(charset, errors="replace")
        return body, r.url


# ── LLM helper ─────────────────────────────────────────────────

def _llm(system: str, user: str, max_tokens: int = 512) -> str:
    cfg = get_llm_config()
    payload = json.dumps({
        "model"      : cfg.get("model", ""),
        "messages"   : [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens" : max_tokens,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {cfg.get('api_key','')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


# ── Plugin ─────────────────────────────────────────────────────

class Plugin(PluginBase):
    priority = 28  # between network(30) and notes(25)

    def matches(self, text: str) -> bool:
        return False  # fully intent-routed

    def run(self, text: str, memory) -> str:
        return "Use natural language — web plugin is intent-routed."

    # ──────────────────────────────────────────────────────

    def summarize(self, url: str, focus: str = "") -> str:
        """Fetch page and summarize via LLM. Optional focus narrows the summary."""
        try:
            html, final_url = _fetch(url)
            text = _html_to_text(html)[:_MAX_CHARS]
            if not text.strip():
                return f"Could not extract readable text from {url}"
            focus_line = f"Focus on: {focus}" if focus else "Give a concise summary."
            system = (
                "You summarize web pages. Be concise and factual. "
                "Bullet key points. Avoid filler."
            )
            prompt = f"URL: {final_url}\n{focus_line}\n\n---\n{text}"
            return _llm(system, prompt, max_tokens=400)
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}: {url}"
        except Exception as e:
            return f"Error fetching {url}: {e}"

    def read(self, url: str) -> str:
        """Return cleaned plain text of a page (no LLM)."""
        try:
            html, _ = _fetch(url)
            text = _html_to_text(html)
            return text[:3000] + ("\n...[truncated]" if len(text) > 3000 else "")
        except Exception as e:
            return f"Error: {e}"

    def ask(self, url: str, question: str) -> str:
        """Fetch page and answer a specific question about its content."""
        try:
            html, final_url = _fetch(url)
            text = _html_to_text(html)[:_MAX_CHARS]
            system = (
                "You answer questions based strictly on provided web page content. "
                "If the answer is not on the page, say so directly."
            )
            prompt = f"Page: {final_url}\nQuestion: {question}\n\n---\n{text}"
            return _llm(system, prompt, max_tokens=350)
        except Exception as e:
            return f"Error: {e}"

    def extract(self, url: str, what: str) -> str:
        """Extract specific data (emails, links, prices, phone numbers, etc)."""
        try:
            html, _ = _fetch(url)

            # Fast regex extractors — no LLM needed for structured data
            w = what.lower()
            if "email" in w or "mail" in w:
                emails = sorted(set(re.findall(
                    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", html
                )))
                return "\n".join(emails) if emails else "No emails found."

            if "link" in w or "url" in w or "href" in w:
                links = re.findall(r'href=["\']([^"\'>]+)["\']', html)
                links = sorted(set(
                    l for l in links
                    if l.startswith("http") and not l.endswith((".png",".jpg",".gif",".svg"))
                ))[:40]
                return "\n".join(links) if links else "No links found."

            if "phone" in w or "number" in w:
                phones = sorted(set(re.findall(
                    r"[\+]?[\(]?[0-9]{1,4}[\)]?[-\s\.]?[0-9]{3,5}[-\s\.]?[0-9]{4,6}", html
                )))[:20]
                return "\n".join(phones) if phones else "No phone numbers found."

            if "image" in w or "img" in w:
                imgs = re.findall(r'<img[^>]+src=["\']([^"\'>]+)["\']', html)
                imgs = [i for i in imgs if not i.startswith("data:")][:30]
                return "\n".join(imgs) if imgs else "No images found."

            # Generic extraction via LLM
            text   = _html_to_text(html)[:_MAX_CHARS]
            system = "Extract exactly what is asked from this web page. Be concise and structured."
            prompt = f"Extract: {what}\n\n---\n{text}"
            return _llm(system, prompt, max_tokens=400)

        except Exception as e:
            return f"Error: {e}"

    def compare(self, url1: str, url2: str, aspect: str = "") -> str:
        """Fetch two pages and compare them via LLM."""
        try:
            html1, _ = _fetch(url1)
            html2, _ = _fetch(url2)
            t1 = _html_to_text(html1)[:4000]
            t2 = _html_to_text(html2)[:4000]
            aspect_line = f"Compare specifically: {aspect}" if aspect else "Give a structured comparison."
            system = "You compare two web pages. Be factual and concise. Use a table if helpful."
            prompt = (
                f"{aspect_line}\n\n"
                f"--- Page 1: {url1} ---\n{t1}\n\n"
                f"--- Page 2: {url2} ---\n{t2}"
            )
            return _llm(system, prompt, max_tokens=500)
        except Exception as e:
            return f"Error: {e}"

    def search(self, query: str, engine: str = "ddg") -> str:
        """Search the web via DuckDuckGo HTML (no API key needed)."""
        try:
            q   = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={q}"
            html, _ = _fetch(url)
            # Extract result titles + URLs from DDG HTML
            titles  = re.findall(r'class="result__a"[^>]*>([^<]+)<', html)
            urls    = re.findall(r'class="result__url"[^>]*>([^<]+)<', html)
            snippets= re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)
            results = []
            for i in range(min(6, len(titles))):
                title   = titles[i].strip() if i < len(titles) else ""
                link    = urls[i].strip()   if i < len(urls)    else ""
                snippet = snippets[i].strip() if i < len(snippets) else ""
                results.append(f"{i+1}. {title}\n   {link}\n   {snippet}")
            return "\n\n".join(results) if results else "No results found."
        except Exception as e:
            return f"Search error: {e}"

    def news(self, topic: str) -> str:
        """Fetch and summarize top news for a topic via DuckDuckGo news."""
        try:
            q   = urllib.parse.quote_plus(topic + " news")
            url = f"https://html.duckduckgo.com/html/?q={q}&ia=news"
            html, _ = _fetch(url)
            titles   = re.findall(r'class="result__a"[^>]*>([^<]+)<', html)
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)
            if not titles:
                return f"No news found for '{topic}'."
            items = []
            for i in range(min(5, len(titles))):
                t = titles[i].strip()
                s = snippets[i].strip() if i < len(snippets) else ""
                items.append(f"• {t}\n  {s}")
            return f"News: {topic}\n\n" + "\n\n".join(items)
        except Exception as e:
            return f"Error: {e}"

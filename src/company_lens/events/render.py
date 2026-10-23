"""Company-page event section. Cards render without a model. AI stays off until a version exists."""

from __future__ import annotations

import html
import json

from company_lens.events.public import unavailable_feed

_COPY = {
    "eyebrow": ("EVENTS AND WHAT IS NEXT", "事件与接下来关注"),
    "title": ("What happened, and what to watch", "最近发生了什么，接下来看什么"),
    "intro": (
        "Recent items come from the published event feed. They are separate from the filed results above and from the price history below.",
        "最近的条目来自已发布的事件源，与上方的正式财报、下方的历史行情彼此独立。",
    ),
    "recent": ("Recent", "最近发生"),
    "upcoming": ("What to watch next", "接下来关注"),
    "upcoming_empty": (
        "No confirmed upcoming date is in this feed. An empty list is not a claim that nothing is scheduled.",
        "这个事件源里没有已确认的未来日期。空白并不表示没有日程。",
    ),
    "more": ("Show the rest", "展开其余条目"),
    "ask": ("Ask AI about this event", "让 AI 解读此事件"),
    "ask_off": (
        "AI stays off until this card and the server share one event version.",
        "在卡片与服务器使用同一事件版本之前，不启用 AI。",
    ),
    "source": ("Read source", "查看来源"),
    "original": ("Original English title", "原始英文标题"),
    "title_only": ("Title only", "仅标题"),
    "version": ("Feed version", "事件版本"),
    "checked": ("Last successful check", "上次成功检查"),
    "ny": ("New York", "纽约"),
    "sh": ("Shanghai", "上海"),
    "gap": ("Coverage gap", "覆盖缺口"),
    "init": (
        "First load covers a bounded recent window, not the full history.",
        "首次只覆盖一段有限的近期窗口，不是全部历史。",
    ),
    "unavailable": (
        "The published event feed is unavailable. That is not the same as there being no events. Financial results and history on this page stay readable.",
        "已发布的事件源目前不可用。这不等于没有事件。本页的财报和历史行情仍可阅读。",
    ),
    "last_good": (
        "Showing the last published feed from this page. A newer feed could not be loaded.",
        "正在显示本页上次发布的事件。更新的事件源没有载入。",
    ),
    "build": (
        "This copy was packaged with the site build. It is not a live intraday feed.",
        "这份内容随站点构建打包，不是盘中实时更新。",
    ),
    "storage_live": ("Live event feed", "实时事件源"),
}


def _pair(key: str) -> str:
    en, zh = _COPY[key]
    return (
        f' data-i18n-en="{html.escape(en, quote=True)}"'
        f' data-i18n-zh="{html.escape(zh, quote=True)}"'
    )


def _text(key: str) -> str:
    return f"{_pair(key)}>{html.escape(_COPY[key][0])}"


def render_events_section(feed: dict | None, *, ticker: str) -> str:
    payload = _safe_feed(feed or unavailable_feed(ticker))
    return (
        f'<section class="events-section" id="events" data-ticker="{html.escape(ticker.upper())}" '
        f'data-events-endpoint="/api/events" data-manifest-version="{html.escape(str(payload.get("manifest_version") or ""))}" '
        f'data-storage="{html.escape(str(payload.get("storage") or "unavailable"))}" aria-labelledby="events-title">'
        f"{_heading(payload)}{_notes(payload)}{_columns(payload)}"
        f'<script type="application/json" id="events-feed">{_json(payload)}</script>'
        "<script>" + _CLIENT + "</script></section>"
    )


def render_preview_page(feed: dict) -> str:
    """A standalone page for review. It uses the same section as the company page."""
    ticker = str(feed["ticker"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(ticker)} events</title>
<style>
:root{{--paper:#f5f4ec;--ink:#183c35;--muted:#657567;--line:#d8ddd3;--blue:#426b50;--navy:#183c35}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Arial,"PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:1100px;margin:auto;padding:24px 20px 80px}}
button,a{{font:inherit}}
{_CSS}
</style>
</head>
<body>
<header class="topbar"><strong>Company Lens</strong>
<button id="language-toggle" type="button" aria-pressed="false">中文</button></header>
<main>{render_events_section(feed, ticker=ticker)}</main>
<script>
let uiLanguage = "en";
function applyLanguage(language, persist) {{
  uiLanguage = language === "zh" ? "zh" : "en";
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n-en]").forEach((element) => {{
    element.textContent = uiLanguage === "zh" ? element.dataset.i18nZh : element.dataset.i18nEn;
  }});
  const toggle = document.getElementById("language-toggle");
  toggle.textContent = uiLanguage === "zh" ? "EN" : "中文";
  toggle.setAttribute("aria-pressed", String(uiLanguage === "zh"));
}}
document.getElementById("language-toggle").addEventListener("click", () => {{
  applyLanguage(uiLanguage === "zh" ? "en" : "zh", true);
}});
const initial = new URLSearchParams(location.search).get("lang") === "zh" ? "zh" : "en";
applyLanguage(initial, false);
</script>
</body></html>"""


def _safe_feed(feed: dict) -> dict:
    events = []
    for event in feed.get("events") or []:
        url = str(event.get("source_url") or "")
        if not url.startswith(("http://", "https://")):
            event = {**event, "source_url": None}
        events.append(event)
    return {**feed, "events": events}


def _heading(feed: dict) -> str:
    status = html.escape(str(feed.get("status") or "unavailable"))
    label = feed.get("status_label") or {"en": status, "zh": status}
    tier = feed.get("tier_label") or {"en": "", "zh": ""}
    version = html.escape(str(feed.get("manifest_version") or "none"))
    return (
        '<div class="section-heading"><div>'
        f'<p class="eyebrow"{_text("eyebrow")}</p>'
        f'<h2 id="events-title"{_text("title")}</h2></div>'
        '<div class="events-status">'
        f'<span class="context-status {status}" data-status="{status}" '
        f'data-i18n-en="{html.escape(str(label.get("en") or ""), quote=True)}" '
        f'data-i18n-zh="{html.escape(str(label.get("zh") or ""), quote=True)}">'
        f'{html.escape(str(label.get("en") or status))}</span>'
        f'<span class="coverage-tier" data-i18n-en="{html.escape(str(tier.get("en") or ""), quote=True)}" '
        f'data-i18n-zh="{html.escape(str(tier.get("zh") or ""), quote=True)}">'
        f'{html.escape(str(tier.get("en") or ""))}</span></div></div>'
        f'<p class="events-version"><span{_text("version")}</span> <code>{version}</code></p>'
    )


def _notes(feed: dict) -> str:
    parts = [f'<p class="section-intro"{_text("intro")}</p>']
    checked = feed.get("checked_at_display") or {}
    if checked:
        parts.append(
            '<p class="events-freshness">'
            f'<span{_text("checked")}</span> '
            f'<span>{html.escape(str(feed.get("checked_at") or ""))}</span> '
            f'<span><span{_text("ny")}</span> {html.escape(str(checked.get("new_york") or ""))}</span> '
            f'<span><span{_text("sh")}</span> {html.escape(str(checked.get("shanghai") or ""))}</span></p>'
        )
    if feed.get("initialization"):
        parts.append(f'<p class="events-note"{_text("init")}</p>')
    if feed.get("storage") == "build_snapshot":
        parts.append(f'<p class="events-note"{_text("build")}</p>')
    if feed.get("storage") == "unavailable" or not feed.get("events"):
        if feed.get("status") == "unavailable":
            parts.append(f'<p class="events-note"{_text("unavailable")}</p>')
        elif feed.get("status") == "no_new_events":
            parts.append(
                '<p class="events-note" data-i18n-en="The last check succeeded and returned no new items. Older items keep their original source time." '
                'data-i18n-zh="上次检查成功，没有新条目。旧条目仍使用原来的来源时间。">'
                "The last check succeeded and returned no new items. Older items keep their original source time.</p>"
            )
    for gap in feed.get("coverage_gaps") or []:
        parts.append(
            f'<p class="events-gap"{_pair("gap")}>{_COPY["gap"][0]} '
            f'{html.escape(str(gap.get("start") or ""))} → {html.escape(str(gap.get("end") or ""))} '
            f'({html.escape(str(gap.get("reason") or ""))})</p>'
        )
    return "".join(parts)


def _columns(feed: dict) -> str:
    events = list(feed.get("events") or [])
    visible, hidden = events[:3], events[3:]
    cards = "".join(_card(event) for event in visible)
    more = ""
    if hidden:
        more = (
            f'<details class="events-more"><summary{_text("more")}</summary>'
            f'{"".join(_card(event) for event in hidden)}</details>'
        )
    empty_recent = ""
    if not events and feed.get("status") not in {"unavailable"}:
        empty_recent = (
            '<p class="empty" data-i18n-en="No items in the covered window." '
            'data-i18n-zh="已覆盖的窗口里没有条目。">No items in the covered window.</p>'
        )
    return (
        '<div class="event-layout"><div>'
        f'<h3{_text("recent")}</h3><div class="event-list">{cards}</div>{empty_recent}{more}</div>'
        "<div>"
        f'<h3{_text("upcoming")}</h3>'
        f'<p class="empty"{_text("upcoming_empty")}</p></div></div>'
    )


def _card(event: dict) -> str:
    title = html.escape(str(event.get("title") or ""))
    publisher = html.escape(str(event.get("publisher") or ""))
    when = event.get("when") or {}
    when_text = html.escape(str(when.get("new_york") or when.get("en") or ""))
    version = html.escape(str(event.get("manifest_version") or ""), quote=True)
    event_id = html.escape(str(event.get("id") or ""), quote=True)
    badge = f'<span class="event-badge"{_text("title_only")}</span>' if event.get("title_only") else ""
    excerpt = event.get("excerpt")
    excerpt_html = f"<p>{html.escape(str(excerpt))}</p>" if excerpt else ""
    note = event.get("precision_note") or {}
    precision = ""
    if note:
        precision = (
            f'<p class="event-precision" data-i18n-en="{html.escape(str(note.get("en") or ""), quote=True)}" '
            f'data-i18n-zh="{html.escape(str(note.get("zh") or ""), quote=True)}">'
            f'{html.escape(str(note.get("en") or ""))}</p>'
        )
    reason = event.get("significance") or {}
    link = ""
    url = str(event.get("source_url") or "")
    if url.startswith(("http://", "https://")):
        link = (
            f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer"'
            f'{_text("source")}</a>'
        )
    if event.get("ask_enabled") and version:
        ask = (
            f'<button type="button" class="event-ask" data-event-id="{event_id}" '
            f'data-event-version="{version}"{_text("ask")}</button>'
        )
    else:
        ask = (
            f'<button type="button" class="event-ask" disabled{_text("ask_off")}</button>'
        )
    return (
        '<article class="event-card">'
        f'<p class="event-meta"><span>{publisher}</span><span>{when_text}</span>{badge}</p>'
        f'<p class="event-original"{_text("original")}</p>'
        f"<h3>{title}</h3>{excerpt_html}{precision}"
        f'<p class="event-reason" data-i18n-en="{html.escape(str(reason.get("en") or ""), quote=True)}" '
        f'data-i18n-zh="{html.escape(str(reason.get("zh") or ""), quote=True)}">'
        f'{html.escape(str(reason.get("en") or ""))}</p>'
        f'<div class="event-actions">{link}{ask}</div>'
        '<p class="event-ask-result" role="status"></p></article>'
    )


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")


_CSS = """
.events-section{padding:58px 0;border-top:1px solid var(--line);overflow-wrap:anywhere}
.events-section h2{margin:0;font-family:Georgia,serif;font-size:34px;font-weight:500}
.events-section h3{margin:0 0 8px;font-family:Georgia,serif;font-size:22px;font-weight:500}
.events-status,.event-actions,.event-meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.events-version,.events-freshness,.events-note,.events-gap{color:var(--muted);font-size:12px}
.event-layout{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,.8fr);gap:28px}
.event-card{min-width:0;max-width:100%;padding:16px 0;border-top:1px solid var(--line)}
.event-card h3{font:500 20px/1.35 Georgia,serif;overflow-wrap:anywhere}
.event-card p{overflow-wrap:anywhere}
.event-ask{padding:8px 12px;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.event-ask:disabled{cursor:not-allowed;opacity:.6}
.event-card a{color:var(--blue)}
.coverage-tier,.event-badge{padding:4px 8px;border:1px solid var(--line);border-radius:999px;font-size:11px}
#events{scroll-margin-top:150px}
@media(max-width:900px){.event-layout{grid-template-columns:minmax(0,1fr)}}
@media(max-width:390px){
.events-section{padding:32px 0}
.events-section h2{font-size:28px}
.event-card h3{font-size:18px}
.events-status,.events-freshness,.event-actions{flex-direction:column;align-items:flex-start}
.event-layout,.event-card,.event-meta{max-width:100%}
}
"""

def events_stylesheet() -> str:
    return _CSS


_CLIENT = r"""
(function () {
  const section = document.getElementById("events");
  if (!section) return;
  const endpoint = section.dataset.eventsEndpoint;
  const ticker = section.dataset.ticker;
  section.querySelectorAll(".event-ask").forEach((button) => {
    button.addEventListener("click", () => askEvent(button));
  });
  if (!endpoint || !ticker) return;
  const url = endpoint + "?ticker=" + encodeURIComponent(ticker);
    fetch(url, {headers: {Accept: "application/json"}})
    .then((response) => response.ok ? response.json() : Promise.reject(new Error("feed")))
    .then((feed) => {
      if (!feed || feed.ticker !== ticker) return;
      const current = section.dataset.manifestVersion || "";
      const next = feed.manifest_version || "";
      if (next && next !== current) {
        const node = document.getElementById("events-feed");
        if (node) node.textContent = JSON.stringify(feed);
        section.dataset.manifestVersion = next;
        const version = section.querySelector(".events-version code");
        if (version) version.textContent = next;
        const list = section.querySelector(".event-list");
        if (list) {
          const events = (feed.events || []).slice(0, 3);
          list.innerHTML = events.map(cardHtml).join("");
          list.querySelectorAll(".event-ask").forEach((button) => {
            button.addEventListener("click", () => askEvent(button));
          });
        }
        if (typeof applyLanguage === "function") applyLanguage(typeof uiLanguage === "string" ? uiLanguage : "en", false);
      }
    })
    .catch(() => {
      const note = document.createElement("p");
      note.className = "events-note";
      note.dataset.i18nEn = "Showing the last published feed from this page. A newer feed could not be loaded.";
      note.dataset.i18nZh = "正在显示本页上次发布的事件。更新的事件源没有载入。";
      note.textContent = note.dataset.i18nEn;
      section.appendChild(note);
    });

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
  }

  function cardHtml(event) {
    const title = escapeHtml(event.title);
    const publisher = escapeHtml(event.publisher);
    const when = escapeHtml((event.when && (event.when.new_york || event.when.en)) || "");
    const version = escapeHtml(event.manifest_version);
    const id = escapeHtml(event.id);
    const ask = event.ask_enabled && version
      ? '<button type="button" class="event-ask" data-event-id="' + id + '" data-event-version="' + version + '">Ask AI about this event</button>'
      : '<button type="button" class="event-ask" disabled>AI stays off until this card and the server share one event version.</button>';
    const href = String(event.source_url || "");
    const link = href.indexOf("https://") === 0 || href.indexOf("http://") === 0
      ? '<a href="' + escapeHtml(href) + '" rel="noopener noreferrer" target="_blank">Read source</a>'
      : "";
    return '<article class="event-card"><p class="event-meta"><span>' + publisher + "</span><span>" + when +
      '</span></p><h3>' + title + '</h3><div class="event-actions">' + link + ask +
      '</div><p class="event-ask-result" role="status"></p></article>';
  }

  function askEvent(button) {
    if (button.disabled || !button.dataset.eventVersion) return;
    const result = button.closest("article").querySelector(".event-ask-result");
    const language = document.documentElement.lang === "zh-CN" ? "Chinese" : "English";
    const question = language === "Chinese"
      ? "这条事件的证据写了什么？哪些内容证据没有给出？"
      : "What does this event's evidence say, and what does it not establish?";
    const model = document.getElementById("ask-model");
    result.textContent = language === "Chinese" ? "正在按当前版本询问…" : "Asking about this version…";
    fetch("/api/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json", Accept: "application/json"},
      body: JSON.stringify({
        ticker: ticker,
        provider: model && model.value ? model.value : "openai",
        language: language,
        depth: "beginner",
        question: question,
        event_version: button.dataset.eventVersion,
        event_id: button.dataset.eventId
      })
    }).then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || payload.error || "ask failed");
      const lines = (payload.answer || []).map((claim) => claim.text).filter(Boolean);
      result.textContent = lines.join(" ") || (language === "Chinese" ? "没有可显示的回答。" : "No answer text.");
    }).catch((error) => {
      result.textContent = error.message || "The event explanation is unavailable. The card stays.";
    });
  }
})();
"""

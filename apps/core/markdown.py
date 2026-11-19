"""Small, safe Markdown subset for descriptions and comments.

The whole text is HTML-escaped first; afterwards only a fixed set of tags is
produced, so user input can never inject markup or scripts.

Supported: headings (#, ##, ###), paragraphs with line breaks, **bold**,
*italic*, ~~strikethrough~~, `code`, fenced code blocks, lists (-, *, 1.),
task lists (- [ ] / - [x]), quotes (>), [links](https://…) and bare URLs.
"""

import re

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from apps.notifications.services import MENTION_PATTERN

FENCE = "```"
HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
UNORDERED = re.compile(r"^\s*[-*]\s+(.*)$")
ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
TASK = re.compile(r"^\[( |x|X)\]\s+(.*)$")
QUOTE = re.compile(r"^&gt;\s?(.*)$")
CODE_SPAN = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BARE_URL = re.compile(r"(?<![\"'=>])\bhttps?://[^\s<]+[^\s<.,;:!?)]")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<![\w*])[*_](?![*_\s])(.+?)(?<![\s*_])[*_](?![\w*])")
STRIKE = re.compile(r"~~(.+?)~~")
PLACEHOLDER = "\x00{}\x00"


def _anchor(url: str, text: str) -> str:
    return (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>'
    )


def _inline(text: str, mentions: bool) -> str:
    """Formats one escaped line; code spans and links are protected first."""
    protected = []

    def protect(html: str) -> str:
        protected.append(html)
        return PLACEHOLDER.format(len(protected) - 1)

    text = CODE_SPAN.sub(lambda m: protect(f"<code>{m.group(1)}</code>"), text)
    text = LINK.sub(lambda m: protect(_anchor(m.group(2), m.group(1))), text)
    text = BARE_URL.sub(lambda m: protect(_anchor(m.group(0), m.group(0))), text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = STRIKE.sub(r"<del>\1</del>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    if mentions:
        text = MENTION_PATTERN.sub(r'<span class="mention">@\1</span>', text)
    for index, html in enumerate(protected):
        text = text.replace(PLACEHOLDER.format(index), html)
    return text


def _list_item(content: str, mentions: bool) -> str:
    task = TASK.match(content)
    if task:
        checked = " checked" if task.group(1).lower() == "x" else ""
        return (
            f'<li class="task"><input type="checkbox" disabled{checked}> '
            f"{_inline(task.group(2), mentions)}</li>"
        )
    return f"<li>{_inline(content, mentions)}</li>"


def render_markdown(text: str, mentions: bool = False) -> SafeString:
    lines = escape(text or "").replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    list_tag = None
    list_items: list[str] = []
    quote: list[str] = []
    index = 0

    def flush() -> None:
        nonlocal paragraph, list_tag, list_items, quote
        if paragraph:
            joined = "<br>".join(_inline(line, mentions) for line in paragraph)
            blocks.append(f"<p>{joined}</p>")
            paragraph = []
        if list_tag:
            blocks.append(f"<{list_tag}>{''.join(list_items)}</{list_tag}>")
            list_tag, list_items = None, []
        if quote:
            joined = "<br>".join(_inline(line, mentions) for line in quote)
            blocks.append(f"<blockquote>{joined}</blockquote>")
            quote = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(FENCE):
            flush()
            code = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(FENCE):
                code.append(lines[index])
                index += 1
            blocks.append(f"<pre><code>{chr(10).join(code)}</code></pre>")
            index += 1
            continue
        heading = HEADING.match(stripped)
        unordered = UNORDERED.match(line)
        ordered = ORDERED.match(line)
        quoted = QUOTE.match(stripped)
        if not stripped:
            flush()
        elif heading:
            flush()
            level = len(heading.group(1)) + 2
            blocks.append(f"<h{level}>{_inline(heading.group(2), mentions)}</h{level}>")
        elif unordered or ordered:
            tag = "ul" if unordered else "ol"
            if list_tag != tag:
                flush()
                list_tag = tag
            list_items.append(_list_item((unordered or ordered).group(1), mentions))
        elif quoted:
            if not quote:
                flush()
            quote.append(quoted.group(1))
        else:
            if list_tag or quote:
                flush()
            paragraph.append(stripped)
        index += 1
    flush()
    return mark_safe("".join(blocks))

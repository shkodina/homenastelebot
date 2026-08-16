from __future__ import annotations

import logging
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

DEFAULT_URLS_PAGE = "http://nas.home/"
PARSE_ERROR = "Не удалось разобрать таблицу ссылок."
FETCH_ERROR = "Не удалось получить таблицу ссылок."
REQUEST_TIMEOUT_SEC = 10


class _Cell:
    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.href: str | None = None

    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[_Cell]] = []
        self._in_table = False
        self._in_thead = False
        self._in_row = False
        self._cell: _Cell | None = None
        self._row: list[_Cell] = []
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        if tag == "table" and not self._in_table:
            self._in_table = True
            return
        if not self._in_table:
            return
        if tag == "thead":
            self._in_thead = True
            return
        if tag == "tr":
            self._in_row = True
            self._row = []
            return
        if tag in {"td", "th"} and self._in_row:
            self._cell = _Cell()
            return
        if tag == "a" and self._cell is not None and self._cell.href is None:
            href = dict(attrs).get("href")
            if href:
                self._cell.href = href.strip()

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag == "thead":
            self._in_thead = False
            return
        if tag in {"td", "th"} and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
            return
        if tag == "tr" and self._in_row:
            self._in_row = False
            if not self._in_thead and self._row:
                self.rows.append(self._row)
            self._row = []
            return
        if tag == "table" and self._in_table:
            self._in_table = False
            self._done = True

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text_parts.append(data)


def parse_url_rows(html: str) -> list[list[_Cell]]:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return parser.rows


def _row_lines(cells: list[_Cell]) -> list[str]:
    texts = [cell.text() for cell in cells]
    service = texts[0] if len(texts) > 0 else ""
    description = texts[2] if len(texts) > 2 else (texts[1] if len(texts) > 1 else "")
    title = " — ".join(part for part in (service, description) if part)

    links: list[str] = []
    seen: set[str] = set()
    for cell in cells:
        href = (cell.href or "").strip()
        if not href or href in seen or href == "#":
            continue
        seen.add(href)
        links.append(href)
    if not title and not links:
        return []
    lines = [title] if title else []
    lines.extend(links)
    return lines


def format_urls_text(html: str) -> str:
    rows = parse_url_rows(html)
    blocks: list[str] = []
    for cells in rows:
        lines = _row_lines(cells)
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return PARSE_ERROR
    return "Сводная табличка URL\n\n" + "\n\n".join(blocks)


async def _fetch_html(page_url: str) -> str:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(page_url) as response:
            response.raise_for_status()
            return await response.text()


async def nas_urls_text(page_url: str, fetch_html=None) -> str:
    url = (page_url or DEFAULT_URLS_PAGE).strip() or DEFAULT_URLS_PAGE
    getter = fetch_html or _fetch_html
    try:
        html = await getter(url)
    except Exception as exc:
        logger.warning("urls fetch failed: %s", type(exc).__name__)
        return FETCH_ERROR
    return format_urls_text(html)

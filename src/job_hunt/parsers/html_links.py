"""Safe link extraction from untrusted email HTML and plain text."""

import html
import re
from html.parser import HTMLParser


PLAIN_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


class _AnchorParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self._current_href = None
        self._text_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "a" or self._current_href is not None:
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() != "a" or self._current_href is None:
            return
        label = re.sub(r"\s+", " ", " ".join(self._text_parts)).strip()
        self.links.append((self._current_href, label))
        self._current_href = None
        self._text_parts = []


def extract_links(html_body, text_body):
    links = []  # type: List[Tuple[str, str]]
    if html_body:
        parser = _AnchorParser()
        try:
            parser.feed(html_body)
            links.extend(parser.links)
        except Exception:
            # Malformed marketing HTML should not stop processing the message.
            pass

    for raw_url in PLAIN_URL_PATTERN.findall(text_body or ""):
        links.append((html.unescape(raw_url).rstrip(".,);]"), ""))

    unique = []
    seen = set()
    for url, label in links:
        key = (url.strip(), label.strip())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique

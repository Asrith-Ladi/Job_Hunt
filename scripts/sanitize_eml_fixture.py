"""Create a local structural fixture from a private EML without copying identifiers."""

import argparse
import html
import json
import re
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
LONG_TOKEN_PATTERN = re.compile(r"(?=[A-Za-z0-9_-]{32,})(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]+")
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
LINKEDIN_PROFILE_FOOTER_PATTERN = re.compile(
    r"This email was intended for.*",
    re.IGNORECASE,
)
SAFE_ATTRIBUTES = {
    "align",
    "aria-label",
    "border",
    "cellpadding",
    "cellspacing",
    "class",
    "colspan",
    "dir",
    "height",
    "href",
    "id",
    "role",
    "rowspan",
    "src",
    "style",
    "title",
    "valign",
    "width",
}
TEXT_ATTRIBUTES = {"aria-label", "class", "id", "title"}


def _ordered_private_values(values):
    unique = {value.strip() for value in values if value and len(value.strip()) >= 3}
    return sorted(unique, key=len, reverse=True)


def _redact_plain(value, private_values):
    redacted = LINKEDIN_PROFILE_FOOTER_PATTERN.sub(
        "REDACTED_PROFILE_CONTEXT",
        value,
    )
    redacted = EMAIL_PATTERN.sub("REDACTED_EMAIL", redacted)
    for private_value in private_values:
        redacted = re.sub(
            re.escape(private_value),
            "REDACTED_NAME",
            redacted,
            flags=re.IGNORECASE,
        )
    redacted = UUID_PATTERN.sub("REDACTED_UUID", redacted)
    return LONG_TOKEN_PATTERN.sub("REDACTED_TOKEN", redacted)


def _sanitize_path(path, private_values):
    sanitized_segments = []
    for segment in path.split("/"):
        decoded = unquote(segment)
        cleaned = _redact_plain(decoded, private_values)
        sanitized_segments.append(quote(cleaned, safe="-._~:@"))
    return "/".join(sanitized_segments)


def sanitize_url(value, private_values):
    decoded = html.unescape(value).strip()
    if decoded.casefold().startswith("mailto:"):
        return "mailto:REDACTED_EMAIL"
    if decoded.casefold().startswith("data:"):
        return "data:REDACTED"

    parsed = urlsplit(decoded)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return _redact_plain(decoded, private_values)

    hostname = (parsed.hostname or "").casefold()
    port = ":{0}".format(parsed.port) if parsed.port else ""
    netloc = "{0}{1}".format(hostname, port)
    path = _sanitize_path(parsed.path, private_values)
    query = urlencode(
        [(key, "REDACTED") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


def redact_text(value, private_values):
    redacted = HTTP_URL_PATTERN.sub(
        lambda match: sanitize_url(match.group(0), private_values), value
    )
    return _redact_plain(redacted, private_values)


def _sanitize_css(value, private_values):
    return re.sub(
        r"url\((['\"]?)(.*?)\1\)",
        lambda match: "url('{0}')".format(
            sanitize_url(match.group(2), private_values)
        ),
        redact_text(value, private_values),
        flags=re.IGNORECASE,
    )


class SanitizingHTMLParser(HTMLParser):
    def __init__(self, private_values):
        super().__init__(convert_charrefs=False)
        self.private_values = private_values
        self.output = []
        self.skip_script_depth = 0
        self.style_depth = 0

    def _attributes(self, attributes):
        sanitized = []
        for name, value in attributes:
            name = name.casefold()
            if name not in SAFE_ATTRIBUTES or value is None:
                continue
            if name in {"href", "src"}:
                value = sanitize_url(value, self.private_values)
            elif name == "style":
                value = _sanitize_css(value, self.private_values)
            elif name in TEXT_ATTRIBUTES:
                value = redact_text(value, self.private_values)
            sanitized.append((name, value))
        return "".join(
            ' {0}="{1}"'.format(name, html.escape(value, quote=True))
            for name, value in sanitized
        )

    def handle_starttag(self, tag, attributes):
        tag = tag.casefold()
        if tag == "script":
            self.skip_script_depth += 1
            return
        if self.skip_script_depth:
            return
        if tag == "style":
            self.style_depth += 1
        self.output.append("<{0}{1}>".format(tag, self._attributes(attributes)))

    def handle_startendtag(self, tag, attributes):
        if self.skip_script_depth or tag.casefold() == "script":
            return
        self.output.append(
            "<{0}{1} />".format(tag.casefold(), self._attributes(attributes))
        )

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "script":
            if self.skip_script_depth:
                self.skip_script_depth -= 1
            return
        if self.skip_script_depth:
            return
        self.output.append("</{0}>".format(tag))
        if tag == "style" and self.style_depth:
            self.style_depth -= 1

    def handle_data(self, data):
        if self.skip_script_depth:
            return
        if self.style_depth:
            self.output.append(_sanitize_css(data, self.private_values))
        else:
            self.output.append(redact_text(data, self.private_values))

    def handle_entityref(self, name):
        if not self.skip_script_depth:
            self.output.append("&{0};".format(name))

    def handle_charref(self, name):
        if not self.skip_script_depth:
            self.output.append("&#{0};".format(name))


def sanitize_html(value, private_values):
    parser = SanitizingHTMLParser(private_values)
    parser.feed(value)
    parser.close()
    return "".join(parser.output)


def _body_part(message, content_type):
    for part in message.walk():
        if part.get_content_type() != content_type or part.get_filename():
            continue
        content = part.get_content()
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or "utf-8", errors="replace")
        return content
    return ""


def _recipient_private_values(message, extra_names):
    header_values = []
    for name in ("to", "cc", "bcc", "delivered-to", "x-original-to"):
        header_values.extend(str(value) for value in message.get_all(name, []))

    values = list(extra_names)
    for display_name, address in getaddresses(header_values):
        values.extend([display_name, address])
        values.extend(part for part in display_name.split() if len(part) >= 3)
    return _ordered_private_values(values)


def create_sanitized_fixture(input_path, html_output, text_output, summary_output, names):
    message = BytesParser(policy=policy.default).parsebytes(Path(input_path).read_bytes())
    private_values = _recipient_private_values(message, names)
    raw_html = _body_part(message, "text/html")
    raw_text = _body_part(message, "text/plain")
    sanitized_html = sanitize_html(raw_html, private_values)
    sanitized_text = redact_text(raw_text, private_values)

    sender_address = parseaddr(str(message.get("from", "")))[1]
    sender_domain = sender_address.rpartition("@")[2].casefold()
    if "linkedin" in sender_domain:
        source = "linkedin"
    elif "naukri" in sender_domain:
        source = "naukri"
    else:
        source = "unknown"
    summary = {
        "source": source,
        "sender_domain": sender_domain,
        "subject": redact_text(str(message.get("subject", "")), private_values),
        "raw_html_characters": len(raw_html),
        "sanitized_html_characters": len(sanitized_html),
        "sanitized_text_characters": len(sanitized_text),
    }

    combined = "\n".join((sanitized_html, sanitized_text, summary["subject"]))
    if EMAIL_PATTERN.search(combined):
        raise RuntimeError("Sanitized fixture still contains an email address.")
    for private_value in private_values:
        if private_value.casefold() in combined.casefold():
            raise RuntimeError("Sanitized fixture still contains a private value.")

    for output_path, value in (
        (html_output, sanitized_html),
        (text_output, sanitized_text),
        (summary_output, json.dumps(summary, indent=2, sort_keys=True)),
    ):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--html-output", required=True)
    parser.add_argument("--text-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--redact-name", action="append", default=[])
    args = parser.parse_args()
    summary = create_sanitized_fixture(
        args.input,
        args.html_output,
        args.text_output,
        args.summary_output,
        args.redact_name,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

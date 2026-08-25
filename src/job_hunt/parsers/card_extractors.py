"""Template-aware field extraction from LinkedIn and Naukri email job cards."""

import re
from html.parser import HTMLParser

from job_hunt.jobs.dedupe import canonicalize_url
from job_hunt.jobs.experience import experience_text_from_url


def _clean_text(parts):
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _classes(attributes):
    return set((attributes.get("class") or "").casefold().split())


def _split_linkedin_company_location(value):
    pieces = [piece.strip() for piece in value.split("·", 1)]
    if len(pieces) != 2 or not all(pieces):
        return None, None
    return pieces[0], pieces[1]


class _LinkedInCardParser(HTMLParser):
    def __init__(self, is_job_link):
        super().__init__(convert_charrefs=True)
        self.is_job_link = is_job_link
        self.cards = {}
        self.current_url = None
        self.title_parts = None
        self.meta_parts = None

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        attributes = dict(attrs)
        href = attributes.get("href") or ""
        if tag == "a" and self.is_job_link(href):
            self.current_url = canonicalize_url(href)
            self.cards.setdefault(self.current_url, {})
            classes = _classes(attributes)
            if "font-bold" in classes and "text-md" in classes:
                self.title_parts = []
        elif tag == "p" and self.current_url:
            classes = _classes(attributes)
            if "text-system-gray-100" in classes:
                self.meta_parts = []

    def handle_data(self, data):
        if self.title_parts is not None:
            self.title_parts.append(data)
        if self.meta_parts is not None:
            self.meta_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "a" and self.title_parts is not None:
            title = _clean_text(self.title_parts)
            if title and self.current_url:
                self.cards[self.current_url]["title"] = title
            self.title_parts = None
        elif tag == "p" and self.meta_parts is not None:
            meta = _clean_text(self.meta_parts)
            company, location = _split_linkedin_company_location(meta)
            if self.current_url and company and location:
                self.cards[self.current_url]["company"] = company
                self.cards[self.current_url]["location"] = location
            self.meta_parts = None


class _NaukriCardParser(HTMLParser):
    def __init__(self, is_job_link):
        super().__init__(convert_charrefs=True)
        self.is_job_link = is_job_link
        self.cards = {}
        self.current_url = None
        self.title_parts = None
        self.location_parts = None
        self.waiting_for_company = False

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        attributes = dict(attrs)
        href = attributes.get("href") or ""
        if tag == "a" and self.is_job_link(href):
            self.current_url = canonicalize_url(href)
            self.cards.setdefault(self.current_url, {})
            experience_text = experience_text_from_url(self.current_url)
            if experience_text:
                self.cards[self.current_url]["experience_text"] = experience_text
                self.cards[self.current_url]["experience_source"] = "alert_url"
            self.title_parts = []
            return
        if self.current_url and "cart_subheading" in _classes(attributes):
            self.location_parts = []

    def handle_data(self, data):
        if self.title_parts is not None:
            self.title_parts.append(data)
            return
        if self.location_parts is not None:
            self.location_parts.append(data)
            return
        if self.current_url and self.waiting_for_company:
            company = _clean_text([data])
            if company:
                self.cards[self.current_url]["company"] = company
                self.waiting_for_company = False

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "a" and self.title_parts is not None:
            title = _clean_text(self.title_parts)
            if title and self.current_url:
                self.cards[self.current_url]["title"] = title
                self.waiting_for_company = True
            self.title_parts = None
        elif self.location_parts is not None and tag in {"td", "p", "span"}:
            location = _clean_text(self.location_parts)
            if location and self.current_url:
                self.cards[self.current_url]["location"] = location
            self.location_parts = None


def _extract_cards(html_body, parser_class, is_job_link):
    if not html_body:
        return {}
    parser = parser_class(is_job_link)
    try:
        parser.feed(html_body)
        parser.close()
    except Exception:
        return {}
    return {url: fields for url, fields in parser.cards.items() if url}


def extract_linkedin_cards(html_body, is_job_link):
    return _extract_cards(html_body, _LinkedInCardParser, is_job_link)


def extract_naukri_cards(html_body, is_job_link):
    return _extract_cards(html_body, _NaukriCardParser, is_job_link)

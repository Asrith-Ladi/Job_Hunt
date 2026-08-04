"""Bounded public HTTP client with redirect and SSRF safety checks."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


USER_AGENT = "PersonalJobHunt/0.3 (+manual public job discovery)"
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class PublicSourceError(RuntimeError):
    """Safe source-specific failure suitable for a source-check row."""


class AccessStoppedError(PublicSourceError):
    """A public source requires login, authorization, or challenge handling."""


@dataclass(frozen=True)
class PublicResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        encoding = "utf-8"
        if "charset=" in content_type:
            candidate = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
            if candidate:
                encoding = candidate
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self):
        try:
            return json.loads(self.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicSourceError("The public source returned invalid JSON.") from exc


def _default_resolver(hostname: str) -> list[str]:
    try:
        values = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PublicSourceError("The public source hostname could not be resolved.") from exc
    return sorted({item[4][0] for item in values})


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )


def validate_public_https_url(
    value: str,
    *,
    resolver: Callable[[str], list[str]] = _default_resolver,
    allowed_hosts: Iterable[str] | None = None,
) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 4096:
        raise PublicSourceError("A valid public HTTPS source URL is required.")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise PublicSourceError("The public source URL is invalid.") from exc
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not hostname:
        raise PublicSourceError("Only public HTTPS source URLs are allowed.")
    if parsed.username or parsed.password or (port and port != 443):
        raise PublicSourceError(
            "Credentials and non-standard ports are not allowed in source URLs."
        )
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise PublicSourceError("Local or private source hostnames are not allowed.")

    if allowed_hosts:
        normalized_allowed = {str(host).casefold().rstrip(".") for host in allowed_hosts}
        if not any(
            hostname == host or hostname.endswith(f".{host}") for host in normalized_allowed
        ):
            raise PublicSourceError("The source redirected outside its approved provider hosts.")

    try:
        direct_address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        addresses = resolver(hostname)
    else:
        addresses = [str(direct_address)]
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise PublicSourceError("The source hostname resolves to a non-public network address.")
    path = parsed.path or "/"
    return urlunsplit(("https", hostname, path, parsed.query, ""))


class SafeHttpClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Callable[[str], list[str]] = _default_resolver,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_redirects: int = 3,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
        self.resolver = resolver
        self.max_response_bytes = int(max_response_bytes)
        self.max_redirects = int(max_redirects)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def get(
        self,
        url: str,
        *,
        allowed_hosts: Iterable[str] | None = None,
        accept: str = "application/json, application/xml, text/xml, text/html;q=0.8",
    ) -> PublicResponse:
        current = str(url)
        for redirect_count in range(self.max_redirects + 1):
            current = validate_public_https_url(
                current,
                resolver=self.resolver,
                allowed_hosts=allowed_hosts,
            )
            try:
                with self.client.stream(
                    "GET",
                    current,
                    headers={"User-Agent": USER_AGENT, "Accept": accept},
                ) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location or redirect_count >= self.max_redirects:
                            raise PublicSourceError(
                                "The public source exceeded the redirect limit."
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code in {401, 403}:
                        raise AccessStoppedError(
                            "The source requires authorization or blocks automated access; manual fallback required."
                        )
                    if response.status_code == 429:
                        raise PublicSourceError(
                            "The public source rate-limited this run; retry later."
                        )
                    if response.status_code >= 500:
                        raise PublicSourceError("The public source is temporarily unavailable.")
                    if response.status_code >= 400:
                        raise PublicSourceError(
                            f"The public source returned HTTP {response.status_code}."
                        )
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            declared_size = int(declared)
                        except ValueError as exc:
                            raise PublicSourceError(
                                "The public source returned an invalid response size."
                            ) from exc
                        if declared_size > self.max_response_bytes:
                            raise PublicSourceError(
                                "The public source response is larger than the safe limit."
                            )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self.max_response_bytes:
                            raise PublicSourceError(
                                "The public source response exceeded the safe size limit."
                            )
                        chunks.append(chunk)
                    return PublicResponse(
                        response.status_code,
                        str(response.url),
                        {key.casefold(): value for key, value in response.headers.items()},
                        b"".join(chunks),
                    )
            except httpx.TimeoutException as exc:
                raise PublicSourceError("The public source timed out.") from exc
            except httpx.RequestError as exc:
                raise PublicSourceError("The public source request failed.") from exc
        raise PublicSourceError("The public source exceeded the redirect limit.")

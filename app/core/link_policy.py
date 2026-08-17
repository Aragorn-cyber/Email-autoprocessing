from urllib.parse import urlsplit, urlunsplit


ALLOWED_LINK_SCHEMES = frozenset({"http", "https"})
IGNORED_LINK_MARKERS = (
    "unsubscribe",
    "退订",
    "pixel",
    "tracking/open",
    "/track/",
    "/sample/click",
    "/emaildisclaimer/",
)
IGNORED_LINK_EXTENSIONS = (".gif", ".jpg", ".jpeg", ".png", ".svg", ".webp")
MAX_REPORT_LINKS = 12


def normalize_safe_link(value: str) -> str | None:
    candidate = value.strip().rstrip(".,;，。；）)]}")
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in ALLOWED_LINK_SCHEMES or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = parsed.hostname.lower()
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, parsed.query, parsed.fragment))


def report_links(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    links: list[str] = []
    for value in values:
        normalized = normalize_safe_link(value)
        if normalized is None:
            continue
        lowered = normalized.lower()
        if any(marker in lowered for marker in IGNORED_LINK_MARKERS):
            continue
        if urlsplit(normalized).path.lower().endswith(IGNORED_LINK_EXTENSIONS):
            continue
        if normalized not in links:
            links.append(normalized)
        if len(links) == MAX_REPORT_LINKS:
            break
    return tuple(links)

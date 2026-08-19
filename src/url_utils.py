from urllib.parse import urlsplit, urlunsplit

def normalize_url(url: str) -> str:
    if not url: return ""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    if not host: return url.strip()
    port = p.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc += f":{port}"
    path = p.path or "/"
    if path != "/": path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, p.query, ""))

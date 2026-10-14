"""Deterministic URL triage: tags, score and path shape. No network, no LLM, no side effects.

Everything here is a *hint for a human*: a high score means "look here first", never "vulnerable".
"""
import re
from urllib.parse import parse_qsl, urlsplit

STATIC_EXT = {"png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp", "css", "woff", "woff2", "ttf", "eot", "otf",
              "mp4", "mp3", "webm", "avi", "mov", "pdf", "map"}
SENSITIVE_EXT = {"env", "git", "svn", "bak", "old", "sql", "zip", "tar", "gz", "7z", "rar", "log", "swp", "key", "pem", "htpasswd", "ds_store"}
REDIRECT_KEYS = {"url", "redirect", "redirect_uri", "redirect_url", "next", "return", "returnurl", "return_to", "continue",
                 "dest", "destination", "callback", "goto", "link", "target", "r", "u", "forward"}
FILE_KEYS = {"file", "filename", "path", "page", "doc", "document", "template", "include", "dir", "folder", "download", "src"}
ID_KEYS = {"id", "uid", "userid", "user_id", "account", "accountid", "order", "orderid", "order_id", "pid", "cid", "uuid", "invoice"}

_API = re.compile(r"(?:^|/)(?:api|rest|graphql|gql|rpc|ajax|service|services|json)(?:/|$)|/v\d+(?:/|$)|\.json$", re.I)
_AUTH = re.compile(r"login|logout|signin|signup|sign-in|sign-up|register|oauth|sso|saml|token|password|passwd|reset|forgot|verify|otp|session|dang-nhap|dang-ky|quen-mat-khau", re.I)
_ADMIN = re.compile(r"(?:^|/)(?:admin|administrator|manage|manager|dashboard|console|backend|cpanel|wp-admin|phpmyadmin|internal|staff)(?:/|$|[-_.])", re.I)
_SENSITIVE = re.compile(r"backup|config|credential|secret|id_rsa|phpinfo|debug|swagger|actuator|server-status|\.git(?:/|$)|\.env|wp-config|\.htaccess|\.DS_Store", re.I)
_DOCS = re.compile(r"swagger|openapi|api-docs|redoc|graphiql|playground", re.I)
_UPLOAD = re.compile(r"upload|attachment|import", re.I)
_DYNAMIC_SEGMENT = re.compile(r"^\d+$|^[0-9a-f]{8,}$|^[0-9a-f-]{32,}$", re.I)

TAG_LABELS = {
    "api": "API/endpoint", "auth": "Đăng nhập/xác thực", "admin": "Khu quản trị", "sensitive": "Đường dẫn nhạy cảm",
    "redirect-param": "Tham số chuyển hướng", "id-param": "Tham số ID", "file-param": "Tham số tệp/đường dẫn",
    "upload": "Tải lên", "js": "JavaScript", "docs": "Tài liệu API", "params": "Có tham số", "static": "Tệp tĩnh",
}
WEIGHTS = {"api": 2.5, "auth": 2.0, "admin": 2.5, "sensitive": 3.0, "redirect-param": 1.5, "id-param": 1.5,
           "file-param": 1.5, "upload": 1.0, "docs": 1.5, "params": 0.5, "js": 0.5}


def url_shape(url: str) -> str:
    """`/tin/some-long-slug-123` -> `/tin/*`: groups thousands of near-identical pages into one row."""
    try:
        path = urlsplit(url).path
    except ValueError:
        return "/"
    out = []
    for segment in [s for s in path.split("/") if s][:3]:
        keep = (len(segment) <= 20 and segment.isascii() and re.fullmatch(r"[A-Za-z0-9_.-]+", segment)
                and not _DYNAMIC_SEGMENT.match(segment) and segment.count("-") < 3)
        out.append(segment.lower() if keep else "*")
    return "/" + "/".join(out)


def classify_url(url: str) -> tuple[list[str], float]:
    try:
        parts = urlsplit(url)
        keys = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
    except ValueError:
        return [], 0.0
    path = parts.path or "/"
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    tags = []
    if ext in STATIC_EXT:
        return ["static"], 0.0
    if _API.search(path):
        tags.append("api")
    if _AUTH.search(path):
        tags.append("auth")
    if _ADMIN.search(path):
        tags.append("admin")
    if ext in SENSITIVE_EXT or _SENSITIVE.search(path):
        tags.append("sensitive")
    if _DOCS.search(path):
        tags.append("docs")
    if _UPLOAD.search(path):
        tags.append("upload")
    if ext == "js":
        tags.append("js")
    if keys:
        tags.append("params")
        if keys & REDIRECT_KEYS:
            tags.append("redirect-param")
        if keys & FILE_KEYS:
            tags.append("file-param")
        if keys & ID_KEYS or any(k.endswith("_id") for k in keys):
            tags.append("id-param")
    score = 0.5 + sum(WEIGHTS.get(t, 0) for t in tags)
    return tags, round(min(10.0, score), 1)

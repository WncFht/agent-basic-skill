from __future__ import annotations

import re
import tarfile
import unicodedata
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - handled by doctor/fetch at runtime
    requests = None

from core.latex_compat import ensure_binhex_compat
from core.models import FetchResult
from core.source_clean import preprocess_latex_sources

ARXIV_ID_RE = re.compile(r"(?P<base>\d{4}\.\d{4,5})(?P<version>v\d+)?", re.I)
TITLE_RE = re.compile(
    r'<h1[^>]*class=["\']title\s+mathjax["\'][^>]*>(.*?)</h1>',
    re.I | re.S,
)
META_TITLE_RE = re.compile(
    r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\'](.*?)["\']',
    re.I | re.S,
)
INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
WHITESPACE_RE = re.compile(r"\s+")
MAX_TITLE_SLUG_CHARS = 140
USER_AGENT = "paper-note-skill"


def normalize_version(version: str | None) -> str | None:
    if version is None:
        return None
    normalized = version.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("v"):
        return normalized
    if normalized.isdigit():
        return f"v{normalized}"
    raise ValueError(f"Unsupported arXiv version: {version}")


def extract_arxiv_id(text: str) -> tuple[str, str | None]:
    match = ARXIV_ID_RE.search(text)
    if match:
        return match.group("base"), match.group("version")
    path = urlparse(text).path
    match = ARXIV_ID_RE.search(path)
    if match:
        return match.group("base"), match.group("version")
    raise ValueError(f"Could not parse arXiv ID from input: {text}")


def http_get(url: str, timeout: int = 30):
    if requests is None:
        raise RuntimeError("Python dependency missing: requests")
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response


def fetch_arxiv_abs_html(paper_id: str) -> str:
    return http_get(f"https://arxiv.org/abs/{paper_id}").text


def parse_latest_version(base_id: str, html: str) -> str | None:
    candidates = re.findall(rf"{re.escape(base_id)}v(\d+)", html)
    if candidates:
        return f"v{max(int(item) for item in candidates)}"
    match = re.search(r"this version,\s*v(\d+)", html, re.I)
    if match:
        return f"v{match.group(1)}"
    return None


def parse_arxiv_title(html: str) -> str | None:
    match = TITLE_RE.search(html) or META_TITLE_RE.search(html)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    title = unescape(title)
    title = re.sub(r"^\s*Title:\s*", "", title, flags=re.I)
    title = WHITESPACE_RE.sub(" ", title).strip()
    return title or None


def sanitize_title_for_path(title: str | None) -> str:
    if not title:
        return ""
    normalized = unicodedata.normalize("NFKC", title)
    normalized = INVALID_PATH_CHARS_RE.sub(" ", normalized)
    normalized = normalized.replace("'", "").replace("`", "")
    slug = WHITESPACE_RE.sub("_", normalized).strip(" ._-")
    if len(slug) > MAX_TITLE_SLUG_CHARS:
        slug = slug[:MAX_TITLE_SLUG_CHARS].rstrip(" ._-")
    return slug


def build_workspace_name(arxiv_id: str, title: str | None) -> str:
    slug = sanitize_title_for_path(title)
    return f"{arxiv_id}_{slug}" if slug else arxiv_id


def ensure_workspace(root: Path, arxiv_id: str, title: str | None) -> Path:
    desired = root / build_workspace_name(arxiv_id, title)
    if desired.exists():
        return desired
    matches = sorted(path for path in root.glob(f"{arxiv_id}_*") if path.is_dir())
    if len(matches) == 1:
        return matches[0]
    desired.mkdir(parents=True, exist_ok=True)
    return desired


def safe_extract_tar(tar_path: Path, out_dir: Path) -> None:
    with tarfile.open(tar_path, "r:*") as archive:
        members = []
        for member in archive.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                continue
            members.append(member)
        archive.extractall(out_dir, members=members)


def fetch_metadata(
    input_text: str,
    *,
    version_override: str | None = None,
) -> tuple[str, str, str | None]:
    base_id, parsed_version = extract_arxiv_id(input_text)
    version = normalize_version(version_override) or parsed_version
    paper_id = f"{base_id}{version or ''}"
    html = fetch_arxiv_abs_html(paper_id)
    latest = version or parse_latest_version(base_id, html)
    title = parse_arxiv_title(html)
    paper_id_with_version = f"{base_id}{latest}" if latest else base_id
    return base_id, paper_id_with_version, title


def fetch_source_to_workspace(
    input_text: str,
    *,
    root: Path,
    version: str | None = None,
    keep_archive: bool = False,
    clean_source: bool = True,
) -> FetchResult:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    arxiv_id, paper_id_with_version, title = fetch_metadata(
        input_text,
        version_override=version,
    )
    workspace = ensure_workspace(root, arxiv_id, title)
    tar_path = workspace / "source.tar"
    source_url = f"https://arxiv.org/src/{paper_id_with_version}"

    response = http_get(source_url, timeout=60)
    tar_path.write_bytes(response.content)
    safe_extract_tar(tar_path, workspace)

    archive_path = tar_path if keep_archive else None
    if not keep_archive and tar_path.exists():
        tar_path.unlink()

    preprocessed_tex_files = 0
    removed_comment_lines = 0
    collapsed_blank_lines = 0
    if clean_source:
        (
            preprocessed_tex_files,
            removed_comment_lines,
            collapsed_blank_lines,
        ) = preprocess_latex_sources(workspace)

    binhex_status = ensure_binhex_compat(workspace)
    return FetchResult(
        workspace=workspace,
        arxiv_id=arxiv_id,
        paper_id_with_version=paper_id_with_version,
        title=title,
        source_url=source_url,
        archive_path=archive_path,
        preprocessed_tex_files=preprocessed_tex_files,
        removed_comment_lines=removed_comment_lines,
        collapsed_blank_lines=collapsed_blank_lines,
        binhex_status=binhex_status,
    )

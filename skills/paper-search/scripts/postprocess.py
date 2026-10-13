#!/usr/bin/env python3
"""Post-processing for paper-search: cross-source dedup, relevance ranking,
survey tagging, and (opt-in) noise filtering.

Design contract (mirrors the skill's full-recall philosophy):
- Dedup NEVER loses information: duplicates collapse into one record that
  keeps the highest-priority source's fields, fills gaps from the others,
  takes the max citation count, and lists every source in `found_in`.
- Ranking SORTS, it does not drop. The only dropping path is the explicit
  `min_score` opt-in, and the caller is told exactly how many were dropped.
- Surveys are TAGGED and sunk to the bottom, never removed.

The lexical scorer and survey regex are ports of the idea_spark literature
pipeline's equivalents (kept as an independent copy: the two skills must stay
standalone-installable).
"""

import re
import unicodedata
from collections import Counter

from source_registry import API_SOURCES

# Display/priority order: highest-signal source first. Dedup keeps the record
# from the earliest source in this list; the CLI prints groups in this order.
CANONICAL_ORDER = list(API_SOURCES)

_STOP = {
    "with",
    "from",
    "that",
    "this",
    "into",
    "over",
    "under",
    "then",
    "than",
    "them",
    "their",
    "through",
    "based",
    "using",
    "toward",
    "towards",
    "via",
    "what",
    "when",
    "where",
    "which",
    "will",
    "have",
    "been",
    "does",
    "about",
}

_SURVEY_RE = re.compile(
    r"^(a |an )?(comprehensive |systematic |brief )*(survey|review|meta-analysis)\b"
    r"|:\s*(a )?(comprehensive |systematic )*(survey|review)\b",
    re.IGNORECASE,
)


def title_norm(t) -> str:
    return " ".join(
        "".join(c.lower() if c.isalnum() else " " for c in (t or "")).split()
    )


def norm_doi(d) -> str:
    d = (d or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        d = d.removeprefix(prefix)
    return d


def norm_arxiv(a) -> str:
    a = (a or "").strip().lower()
    a = re.sub(r"^(arxiv:)", "", a)
    return re.sub(r"v\d+$", "", a)  # 2401.12345v2 -> 2401.12345


def is_survey(title) -> bool:
    return bool(_SURVEY_RE.search(title or ""))


def term_words(queries) -> set:
    """Content words across one or more English or CJK queries."""
    words = set()
    for q in queries:
        normalized = unicodedata.normalize("NFKC", str(q or "").casefold())
        for w in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", normalized):
            if "\u3400" <= w <= "\u9fff":
                words.add(w)
                continue
            if len(w) > 3 and w not in _STOP:
                words.add(w)
    return words


def relevance_score(paper, words) -> int:
    """Count of query content-words appearing in title+abstract.
    startswith gives crude stemming: 'watermark' matches 'watermarking'."""
    text = ((paper.get("title") or "") + " " + (paper.get("abstract") or "")).lower()
    text = unicodedata.normalize("NFKC", text.casefold())
    tokens = set(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", text))
    return sum(1 for w in words if any(tok.startswith(w) for tok in tokens))


def _source_priority(source) -> int:
    try:
        return CANONICAL_ORDER.index(source)
    except ValueError:
        return len(CANONICAL_ORDER)


def _first_author_key(paper) -> str:
    authors = paper.get("authors") or []
    if not authors:
        return ""
    normalized = title_norm(str(authors[0]))
    return normalized.split()[-1] if normalized else ""


def _title_is_distinctive(value: str) -> bool:
    tokens = value.split()
    return len(tokens) >= 2 and len(value.replace(" ", "")) >= 10


def _find(parent, index):
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _component_metadata(paper) -> dict[str, set]:
    year = paper.get("year")
    return {
        "dois": {value for value in [norm_doi(paper.get("doi"))] if value},
        "arxiv_ids": {value for value in [norm_arxiv(paper.get("arxiv_id"))] if value},
        "years": {year} if year not in (None, "") else set(),
        "authors": {value for value in [_first_author_key(paper)] if value},
    }


def _title_components_compatible(left, right, parent, metadata) -> bool:
    """Reject title-only joins that would bridge conflicting strong metadata."""
    left_meta = metadata[_find(parent, left)]
    right_meta = metadata[_find(parent, right)]
    left_dois, right_dois = left_meta["dois"], right_meta["dois"]
    if left_dois and right_dois and left_dois.isdisjoint(right_dois):
        return False

    left_arxiv, right_arxiv = left_meta["arxiv_ids"], right_meta["arxiv_ids"]
    if left_arxiv and right_arxiv and left_arxiv.isdisjoint(right_arxiv):
        return False

    left_years, right_years = left_meta["years"], right_meta["years"]
    if left_years and right_years:
        try:
            if min(abs(int(a) - int(b)) for a in left_years for b in right_years) > 1:
                return False
        except (TypeError, ValueError):
            return False

    left_authors, right_authors = left_meta["authors"], right_meta["authors"]
    return not (
        left_authors and right_authors and left_authors.isdisjoint(right_authors)
    )


_FILL_FIELDS = (
    "authors",
    "abstract",
    "venue",
    "doi",
    "arxiv_id",
    "url",
    "year",
)

_DATE_PRECISION_PRIORITY = {"day": 0, "month": 1, "year": 2, "unknown": 3}

_STATUS_PRIORITY = {
    "accepted": 0,
    "published": 1,
    "preprint": 2,
    "submitted": 3,
    "withdrawn": 4,
    "rejected": 5,
    "unknown": 6,
}


def dedup(results) -> list:
    """Collapse cross-source duplicates. `results` is {source: [paper, ...]}.

    Matching keys, in strength order: normalized DOI, normalized arXiv id,
    normalized title. A paper joins an existing cluster if ANY key matches
    (so a DOI-only record and a title-only record of the same paper merge).
    Returns merged papers; each carries `found_in` (canonical-order source
    list) and max `citation_count`; missing fields are filled from dups.
    """
    ordered: list[dict] = []
    for source in sorted(results.keys(), key=_source_priority):
        ordered.extend(results.get(source) or [])

    parent = list(range(len(ordered)))
    metadata = [_component_metadata(paper) for paper in ordered]

    def union(left, right):
        left_root, right_root = _find(parent, left), _find(parent, right)
        if left_root != right_root:
            parent[right_root] = left_root
            for field in metadata[left_root]:
                metadata[left_root][field].update(metadata[right_root][field])

    # Strong identifiers may merge records regardless of weaker metadata drift.
    indexes: dict[tuple[str, str], int] = {}
    for index, paper in enumerate(ordered):
        keys = (
            ("doi", norm_doi(paper.get("doi"))),
            ("arxiv", norm_arxiv(paper.get("arxiv_id"))),
        )
        for kind, value in keys:
            if not value:
                continue
            existing = indexes.get((kind, value))
            if existing is not None:
                union(index, existing)
            else:
                indexes[(kind, value)] = index

    # A title is only a fallback key. It cannot bridge components carrying
    # conflicting DOI/arXiv IDs, years, or first authors.
    title_groups: dict[str, list[int]] = {}
    for index, paper in enumerate(ordered):
        normalized_title = title_norm(paper.get("title"))
        if normalized_title:
            title_groups.setdefault(normalized_title, []).append(index)
    for normalized_title, group in title_groups.items():
        for position, index in enumerate(group):
            for existing in group[:position]:
                same_source = ordered[index].get("source") == ordered[existing].get(
                    "source"
                )
                if not _title_is_distinctive(normalized_title) and not (same_source):
                    continue
                if _title_components_compatible(index, existing, parent, metadata):
                    union(index, existing)

    components: dict[int, list[dict]] = {}
    component_order: list[int] = []
    for index, paper in enumerate(ordered):
        root = _find(parent, index)
        if root not in components:
            components[root] = []
            component_order.append(root)
        components[root].append(paper)

    clusters = []
    for root in component_order:
        papers = components[root]
        rec = dict(papers[0])
        rec["found_in"] = []
        rec["citation_count"] = None
        rec["citation_source"] = None
        rec["retrieval_ranks"] = []
        rec["field_provenance"] = {
            field: papers[0].get("source")
            for field in ("title", *_FILL_FIELDS)
            if papers[0].get(field)
        }
        if papers[0].get("publication_date"):
            rec["field_provenance"]["publication_date"] = papers[0].get("source")
            rec["field_provenance"]["date_precision"] = papers[0].get("source")
        best_status = "unknown"
        best_status_source = None
        for paper in papers:
            src = paper.get("source")
            if src and src not in rec["found_in"]:
                rec["found_in"].append(src)
            for retrieval in paper.get("retrieval_ranks") or []:
                if retrieval not in rec["retrieval_ranks"]:
                    rec["retrieval_ranks"].append(dict(retrieval))
            citation_count = paper.get("citation_count")
            if citation_count is not None and (
                rec["citation_count"] is None or citation_count > rec["citation_count"]
            ):
                rec["citation_count"] = citation_count
                rec["citation_source"] = paper.get("citation_source") or src
                rec["field_provenance"]["citation_count"] = (
                    paper.get("citation_source") or src
                )
            candidate_date = paper.get("publication_date")
            candidate_precision = str(paper.get("date_precision") or "unknown")
            current_precision = str(rec.get("date_precision") or "unknown")
            if candidate_date and (
                not rec.get("publication_date")
                or _DATE_PRECISION_PRIORITY.get(candidate_precision, 99)
                < _DATE_PRECISION_PRIORITY.get(current_precision, 99)
            ):
                rec["publication_date"] = candidate_date
                rec["date_precision"] = candidate_precision
                rec["field_provenance"]["publication_date"] = src
                rec["field_provenance"]["date_precision"] = src
            for field in _FILL_FIELDS:
                if not rec.get(field) and paper.get(field):
                    rec[field] = paper[field]
                    rec["field_provenance"][field] = src
            status = str(paper.get("publication_status") or "unknown")
            if _STATUS_PRIORITY.get(status, 99) < _STATUS_PRIORITY.get(best_status, 99):
                best_status = status
                best_status_source = paper.get("status_source") or src
        rec["publication_status"] = best_status
        rec["status_source"] = best_status_source
        if best_status_source:
            rec["field_provenance"]["publication_status"] = best_status_source
        rec["found_in"].sort(key=_source_priority)
        dois = Counter(norm_doi(paper.get("doi")) for paper in papers)
        arxiv_ids = Counter(norm_arxiv(paper.get("arxiv_id")) for paper in papers)
        titles = Counter(title_norm(paper.get("title")) for paper in papers)
        reasons = []
        if any(value and count > 1 for value, count in dois.items()):
            reasons.append("doi")
        if any(value and count > 1 for value, count in arxiv_ids.items()):
            reasons.append("arxiv_id")
        if any(value and count > 1 for value, count in titles.items()):
            reasons.append("title_metadata")
        rec["dedup_match_reasons"] = reasons
        rec["dedup_confidence"] = (
            "strong_id"
            if {"doi", "arxiv_id"}.intersection(reasons)
            else "title_metadata"
            if reasons
            else "singleton"
        )
        clusters.append(rec)
    return clusters


def _retrieval_features(paper) -> tuple[int, float]:
    best_by_query_source: dict[tuple[str, str], int] = {}
    for item in paper.get("retrieval_ranks") or []:
        try:
            query = str(item.get("query") or "")
            source = str(item.get("source") or paper.get("source") or "")
            rank_value = int(item.get("rank"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not query or rank_value <= 0:
            continue
        key = (query, source)
        best_by_query_source[key] = min(
            rank_value, best_by_query_source.get(key, rank_value)
        )
    query_coverage = len({query for query, _source in best_by_query_source})
    reciprocal_rank = sum(1.0 / (60 + value) for value in best_by_query_source.values())
    return query_coverage, reciprocal_rank


def rank_source_candidates(papers, queries):
    """Fuse multi-query candidates before enforcing the final source limit."""
    words = term_words(queries)
    for paper in papers:
        coverage, reciprocal_rank = _retrieval_features(paper)
        paper["query_coverage"] = coverage
        paper["source_rank_score"] = reciprocal_rank
        paper["relevance_score"] = relevance_score(paper, words)
    papers.sort(
        key=lambda paper: (
            -paper["query_coverage"],
            -paper["relevance_score"],
            -paper["source_rank_score"],
            -(paper.get("citation_count") or 0),
            title_norm(paper.get("title")),
        )
    )
    return papers


def rank(papers, queries, min_score=None):
    """Score, tag surveys, sort (non-surveys by score desc then citations desc;
    surveys sunk to the bottom in the same order). Returns (ranked, n_dropped);
    n_dropped is 0 unless min_score is set (opt-in dropping only)."""
    words = term_words(queries)
    survey_requested = any(
        re.search(r"\b(survey|review|overview|综述|调研)\b", str(query), re.IGNORECASE)
        for query in queries
    )
    for p in papers:
        p["relevance_score"] = relevance_score(p, words)
        p["is_survey"] = is_survey(p.get("title"))
        coverage, reciprocal_rank = _retrieval_features(p)
        p["query_coverage"] = coverage
        p["source_rank_score"] = reciprocal_rank
    n_dropped = 0
    if min_score is not None:
        kept = [p for p in papers if p["relevance_score"] >= min_score]
        n_dropped = len(papers) - len(kept)
        papers = kept
    papers.sort(
        key=lambda p: (
            p["is_survey"] and not survey_requested,
            -p["query_coverage"],
            -p["relevance_score"],
            -p["source_rank_score"],
            -(p.get("citation_count") or 0),
            title_norm(p.get("title")),
        )
    )
    return papers, n_dropped

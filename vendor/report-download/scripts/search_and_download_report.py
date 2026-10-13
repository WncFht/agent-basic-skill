#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from ddgs import DDGS


SUPPORTED_DOMAINS = (
    "static.cninfo.com.cn",
    "www1.hkexnews.hk",
    "stockn.xueqiu.com",
    "notice.10jqka.com.cn",
)
PDF_URL_RE = re.compile(r"https?://[^\s'\"]+\.pdf(?:\?[^\s'\"]*)?", re.IGNORECASE)
EXCLUDE_TERMS = {
    "摘要",
    "审计报告",
    "公告",
    "利润分配",
    "可持续发展",
    "股东大会",
    "esg",
    "summary",
    "auditor",
    "dividend",
    "更正",
    "补充",
    "意见",
    "内部控制",
}
FULLTEXT_TERMS = {
    "全文",
}

REPORT_TYPE_MAP = {
    "年报": ("年报", "年度报告", "annual report", "年报"),
    "annual": ("年报", "年度报告", "annual report", "年报"),
    "中报": ("中报", "半年度报告", "interim report", "半年报"),
    "interim": ("中报", "半年度报告", "interim report", "半年报"),
    "一季报": ("一季报", "第一季度报告", "first quarter report", "一季报"),
    "q1": ("一季报", "第一季度报告", "first quarter report", "一季报"),
    "三季报": ("三季报", "第三季度报告", "third quarter report", "三季报"),
    "q3": ("三季报", "第三季度报告", "third quarter report", "三季报"),
}

CNINFO_CATEGORY_MAP = {
    "年报": "年报",
    "中报": "半年报",
    "一季报": "一季报",
    "三季报": "三季报",
}

CNINFO_CATEGORY_CODE_MAP = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
}

SOURCE_PRIORITY = {
    "cninfo_official": 60,
    "hkexnews": 52,
    "cninfo_search": 36,
    "xueqiu": 18,
    "10jqka": 10,
    "open": 0,
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.cninfo.com.cn/",
}


def default_save_dir() -> str:
    explicit = os.environ.get("REPORT_DOWNLOAD_SAVE_DIR")
    if explicit:
        return os.path.expanduser(explicit)
    workspace_root = os.environ.get("STOCK_SKILL_WORKSPACE_ROOT", "~/Desktop/src/skill-runs")
    return str(Path(os.path.expanduser(workspace_root)) / "report-download")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and download financial report PDFs")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--year")
    parser.add_argument("--report-type", default="年报")
    parser.add_argument("--save-dir", default=default_save_dir())
    parser.add_argument("--max-results", type=int, default=8)
    return parser.parse_args()


def normalize_stock_code(stock_code: str) -> tuple[str, str, str, str]:
    raw = stock_code.strip().upper()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith(("SH", "SZ")) and len(raw) == 8:
        market_code = raw
        exchange_symbol = f"{raw[2:]}.{ 'SS' if raw.startswith('SH') else 'SZ' }"
        plain = raw[2:]
        return market_code, exchange_symbol, plain, "A"
    if raw.endswith((".SS", ".SH", ".SZ")) and len(digits) >= 6:
        plain = digits[-6:]
        exchange_symbol = f"{plain}.{ 'SS' if raw.endswith(('.SS', '.SH')) else 'SZ' }"
        market_code = f"{'SH' if exchange_symbol.endswith('.SS') else 'SZ'}{plain}"
        return market_code, exchange_symbol, plain, "A"
    if len(digits) == 6 and digits.startswith("6"):
        return f"SH{digits}", f"{digits}.SS", digits, "A"
    if len(digits) == 6 and digits[0] in {"0", "3"}:
        return f"SZ{digits}", f"{digits}.SZ", digits, "A"
    hk = digits.zfill(5)
    return hk, f"{hk}.HK", hk, "HK"


def normalize_report_type(report_type: str) -> tuple[str, str, str, str]:
    key = report_type.strip().lower()
    return REPORT_TYPE_MAP.get(key, REPORT_TYPE_MAP["年报"])


def default_year(report_label: str) -> str:
    today = dt.date.today()
    if report_label != "年报":
        return str(today.year)
    return str(today.year - 2 if today.month <= 3 else today.year - 1)


def normalize_title(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def is_cninfo_fulltext_title(title_key: str) -> bool:
    return any(normalize_title(term) in title_key for term in FULLTEXT_TERMS)


def matches_cninfo_report_title(
    title: str,
    year: str,
    report_label: str,
    category_name: str,
    *,
    same_day_has_target_year: bool = False,
) -> bool:
    title_key = normalize_title(title)
    if any(term in title_key for term in [normalize_title(term) for term in EXCLUDE_TERMS]):
        return False

    report_terms = {
        normalize_title(report_label),
        normalize_title(category_name),
        normalize_title(REPORT_TYPE_MAP[report_label][1]),
    }
    if not any(term and term in title_key for term in report_terms) and not is_cninfo_fulltext_title(title_key):
        return False

    if year in title:
        return True
    return is_cninfo_fulltext_title(title_key) and same_day_has_target_year


def extract_pdf_url(result: dict[str, str]) -> str | None:
    for key in ("href", "url", "body", "title"):
        value = result.get(key) or ""
        match = PDF_URL_RE.search(value)
        if match:
            url = match.group(0)
            if any(domain in url for domain in SUPPORTED_DOMAINS):
                return url
    href = result.get("href") or result.get("url")
    if href and href.lower().endswith(".pdf") and any(domain in href for domain in SUPPORTED_DOMAINS):
        return href
    return None


def score_candidate(candidate: dict[str, str], formatted_code: str, plain_code: str, year: str, report_label: str, a_keyword: str, hk_keyword: str) -> int:
    text = " ".join(str(candidate.get(field, "")) for field in ("title", "body", "url", "source")).lower()
    score = SOURCE_PRIORITY.get(candidate["source"], 0)
    if year in text:
        score += 12
    if formatted_code.lower() in text or plain_code.lower() in text:
        score += 10
    stripped_plain = plain_code.lstrip("0")
    if stripped_plain and stripped_plain != plain_code and stripped_plain.lower() in text:
        score += 5
    for term in {report_label, a_keyword, hk_keyword}:
        if term.lower() in text:
            score += 8
    if candidate["source"] == "hkexnews" and "/listedco/listconews/sehk/" in candidate["url"].lower():
        score += 10
    if candidate["source"] == "cninfo_official":
        score += 15
    if any(term.lower() in text for term in FULLTEXT_TERMS):
        score += 30
    for term in EXCLUDE_TERMS:
        if term.lower() in text:
            score -= 40
    if candidate["url"].lower().endswith(".pdf"):
        score += 4
    return score


def build_queries(formatted_code: str, plain_code: str, year: str, report_label: str, a_keyword: str, hk_keyword: str, market: str) -> list[tuple[str, str]]:
    code_terms = [formatted_code, plain_code]
    stripped_plain = plain_code.lstrip("0")
    if stripped_plain and stripped_plain not in code_terms:
        code_terms.append(stripped_plain)

    queries: list[tuple[str, str]] = []
    if market == "HK":
        for code_term in code_terms:
            queries.append(("hkexnews", f"site:www1.hkexnews.hk {code_term} {hk_keyword} {year} pdf"))
            queries.append(("hkexnews", f"site:www1.hkexnews.hk/listedco/listconews/sehk {code_term} {hk_keyword} {year} pdf"))
    else:
        for code_term in code_terms:
            queries.append(("cninfo_search", f"site:static.cninfo.com.cn {code_term} {a_keyword} {year} pdf"))
            queries.append(("cninfo_search", f"site:www.cninfo.com.cn {code_term} {a_keyword} {year} pdf"))

    for source in ("xueqiu", "10jqka"):
        domain = "stockn.xueqiu.com" if source == "xueqiu" else "notice.10jqka.com.cn"
        keyword = hk_keyword if market == "HK" else a_keyword
        for code_term in code_terms:
            queries.append((source, f"site:{domain} {code_term} {keyword} {year} pdf"))
    queries.append(("open", f"{plain_code} {(hk_keyword if market == 'HK' else a_keyword)} {year} pdf"))
    return queries


def search_candidates_via_ddgs(
    formatted_code: str,
    plain_code: str,
    year: str,
    report_label: str,
    a_keyword: str,
    hk_keyword: str,
    market: str,
    max_results: int,
) -> list[dict[str, str]]:
    queries = build_queries(formatted_code, plain_code, year, report_label, a_keyword, hk_keyword, market)
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    with DDGS() as ddgs:
        for source, query in queries:
            try:
                results = ddgs.text(query, max_results=max_results)
            except Exception:
                continue
            for result in results:
                url = extract_pdf_url(result)
                if not url or url in seen:
                    continue
                seen.add(url)
                item = {
                    "source": source,
                    "query": query,
                    "title": result.get("title", ""),
                    "body": result.get("body", ""),
                    "url": url,
                }
                item["score"] = score_candidate(item, formatted_code, plain_code, year, report_label, a_keyword, hk_keyword)
                candidates.append(item)
    return candidates


def cninfo_stock_map() -> dict[str, str]:
    response = requests.get("http://www.cninfo.com.cn/new/data/szse_stock.json", headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return {item["code"]: item["orgId"] for item in payload.get("stockList", [])}


def fetch_cninfo_detail(announcement_id: str, announce_time: str) -> str | None:
    response = requests.post(
        "https://www.cninfo.com.cn/new/announcement/bulletin_detail",
        params={"announceId": announcement_id, "flag": "true", "announceTime": announce_time},
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("fileUrl")


def cninfo_candidates(plain_code: str, year: str, report_label: str) -> list[dict[str, str]]:
    org_map = cninfo_stock_map()
    org_id = org_map.get(plain_code)
    if not org_id:
        return []

    category_name = CNINFO_CATEGORY_MAP.get(report_label, "年报")
    category_code = CNINFO_CATEGORY_CODE_MAP[category_name]
    start_date = f"{year}-01-01"
    end_date = f"{int(year) + 2}-12-31"

    payload = {
        "pageNum": "1",
        "pageSize": "30",
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{plain_code},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": category_code,
        "trade": "",
        "seDate": f"{start_date}~{end_date}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    response = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    total = int(data.get("totalAnnouncement") or 0)
    pages = max(1, min(6, math.ceil(total / 30)))

    items: list[dict[str, str]] = []
    for page in range(1, pages + 1):
        payload["pageNum"] = str(page)
        page_response = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, headers=REQUEST_HEADERS, timeout=20)
        page_response.raise_for_status()
        page_data = page_response.json()
        announcements = page_data.get("announcements", [])
        matching_days = {
            announcement["announcementTime"]
            for announcement in announcements
            if matches_cninfo_report_title(
                announcement.get("announcementTitle", ""),
                year,
                report_label,
                category_name,
                same_day_has_target_year=True,
            )
            and year in announcement.get("announcementTitle", "")
        }
        for announcement in announcements:
            title = announcement.get("announcementTitle", "")
            if not matches_cninfo_report_title(
                title,
                year,
                report_label,
                category_name,
                same_day_has_target_year=announcement["announcementTime"] in matching_days,
            ):
                continue
            announcement_time = dt.datetime.fromtimestamp(announcement["announcementTime"] / 1000).strftime("%Y-%m-%d")
            try:
                file_url = fetch_cninfo_detail(str(announcement["announcementId"]), announcement_time)
            except Exception:
                continue
            if not file_url:
                continue
            items.append(
                {
                    "source": "cninfo_official",
                    "query": "cninfo official",
                    "title": title,
                    "body": announcement_time,
                    "url": file_url,
                }
            )
    return items


def merge_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=lambda value: value["score"], reverse=True):
        url = item["url"]
        if url in seen:
            continue
        seen.add(url)
        merged.append(item)
    return merged


def call_downloader(url: str, stock_code: str, report_type: str, year: str, save_dir: str) -> subprocess.CompletedProcess[str]:
    script_path = Path(__file__).with_name("download_report.py")
    cmd = [
        sys.executable,
        str(script_path),
        "--url",
        url,
        "--stock-code",
        stock_code,
        "--report-type",
        report_type,
        "--year",
        year,
        "--save-dir",
        save_dir,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def download_first_available_candidate(
    candidates: list[dict[str, str]],
    stock_code: str,
    report_type: str,
    year: str,
    save_dir: str,
) -> int:
    last_return_code = 1
    for index, item in enumerate(candidates, start=1):
        print(f"Selected candidate {index}/{len(candidates)}: {item['title'] or item['url']}", file=sys.stderr)
        print(f"Source: {item['source']} | Score: {item['score']}", file=sys.stderr)
        print(f"URL: {item['url']}", file=sys.stderr)

        result = call_downloader(item["url"], stock_code, report_type, year, save_dir)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode == 0:
            return 0
        last_return_code = result.returncode
        print("Candidate rejected, trying next candidate if available.", file=sys.stderr)

    return last_return_code


def main() -> int:
    args = parse_args()
    formatted_code, _exchange_symbol, plain_code, market = normalize_stock_code(args.stock_code)
    report_label, a_keyword, hk_keyword, _cninfo_keyword = normalize_report_type(args.report_type)
    year = args.year or default_year(report_label)

    candidates: list[dict[str, str]] = []
    if market == "A":
        try:
            candidates.extend(cninfo_candidates(plain_code, year, report_label))
        except Exception as exc:
            print(f"CNINFO official search failed: {exc}", file=sys.stderr)

    candidates.extend(
        search_candidates_via_ddgs(
            formatted_code=formatted_code,
            plain_code=plain_code,
            year=year,
            report_label=report_label,
            a_keyword=a_keyword,
            hk_keyword=hk_keyword,
            market=market,
            max_results=args.max_results,
        )
    )

    for item in candidates:
        item["score"] = score_candidate(item, formatted_code, plain_code, year, report_label, a_keyword, hk_keyword)
    merged = merge_candidates(candidates)

    if not merged:
        print(f"No PDF candidate found for {formatted_code} {year} {report_label}", file=sys.stderr)
        return 1

    return download_first_available_candidate(
        merged,
        formatted_code,
        report_label,
        year,
        args.save_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())

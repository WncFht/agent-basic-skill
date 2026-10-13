# 程序化 API、输出 schema 与运行时配置

大多数场景应使用 `scripts/search_papers.py` CLI(见 SKILL.md)。只有当 CLI 不够用——例如要直接消费结构化 dict、而不必解析 CLI 文本输出——才需要这里的函数调用接口。本文件同时承载：完整输出 schema、逐来源选项细节、HTTP 超时/预算环境变量。

运行环境：脚本头部带有 PEP 723 内联依赖声明 (`requests`、`openreview-py`),推荐用 `uv run` 启动;任何装有这两个包的解释器直接 `python3` 也可运行。

## 函数调用

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
PYTHONPATH="$REPO_ROOT/.agents/skills/paper-search/scripts" \
uv run --no-project --with requests --with openreview-py python -c "
import json, sys
from search_papers import search_papers
res = search_papers(
    query='<QUERY>',
    start_year=2024,
    end_year=2026,
    max_results=50,
    sources=['semantic_scholar', 'open_alex', 'arxiv', 'openreview'],
    parallel=True,
    source_options={
        'open_alex': {'search_mode': 'lexical'},
        'openreview': {
            'venues': ['ICLR.cc/2026/Conference'],
            'api_version': 'v2',
            'status': 'accepted',
        }
    },
)
for source, papers in res.items():
    print(f'{source}: {len(papers)} papers')
    for p in papers:
        print(f'  - {p[\"title\"]} ({p[\"year\"]})')
    for error in res.errors[source]:
        print(f'  ERROR {error[\"type\"]}: {error[\"message\"]}')
print(json.dumps(res.to_dict(), ensure_ascii=False))
"
```

返回值是向后兼容的 `dict` 子类：`res[source]` 仍是该来源的论文列表，`res.errors[source]` 是结构化诊断 (每条含 `query`、`type`、`message`),无失败的来源对应空列表。序列化用 `res.to_dict()`(含 `papers` + `errors` 的精简信封),不要直接序列化 `res` 本身。CLI `--json` 的信封更大，额外含 `request`、`merged_ranked_papers` 和 `stats`。

每个选中的来源运行在独立子进程中;`parallel=False` 保持同样的隔离、仅按顺序执行。多查询调用时，每个查询有独立的 `max_results` 候选预算;候选保留查询/来源排名，先在来源内去重、按查询覆盖度 + 词面相关性 + 倒数排名融合，再截断到 `max_results`。

每条规范化记录都含 `date_precision`(`day`/`month`/`year`/`unknown`)。精确日期过滤 (`start_date`/`end_date`) 比较记录的已知日期区间与请求区间，保留有重叠者;日期未知的记录保留。

ID 形式的查询 (arXiv 编号 / DOI) 由编排层识别并直查权威端点，绕过 keyword worker 与年份过滤;解析结果注入归属来源桶 (arXiv ID → `arxiv`,DOI → `crossref`),解析不到记为 `IdNotFound` 警告。

## 输出 schema

`search_papers()` 返回一个 dict，把来源名映射到论文 dict 列表：

```
{
  "arxiv": [
    {
      "title": str,
      "authors": [str, ...],
      "year": int,
      "abstract": str,
      "url": str,
      "venue": str,
      "citation_count": int | None,
      "citation_source": str | None,
      "publication_date": str,
      "date_precision": "day" | "month" | "year" | "unknown",
      "publication_status": "accepted" | "published" | "preprint" | "submitted" | "withdrawn" | "rejected" | "unknown",
      "status_source": str | None,
      "source": str,
      "doi": str | None,
      "arxiv_id": str | None,
      "retrieval_ranks": [{"query": str, "rank": int, "source": str}, ...]
    }, ...
  ],
  "semantic_scholar": [...],
  ...
}
```

合并后的记录 (`--json` 的 `merged_ranked_papers`,即 CLI 默认展示的列表) 额外携带 `found_in`(来源列表)、`relevance_score`、`query_coverage`、`source_rank_score`、`is_survey`、`dedup_match_reasons`、`dedup_confidence` 和 `field_provenance`(字段溯源)。

## 逐来源选项 (source_options / CLI flags)

OpenReview 默认走 API v2，检索 `data/openreview_venues.json` 里维护的 AI 会议注册表 (ICLR 2024+、NeurIPS 2023+、ICML 2023+、TMLR、COLM、AISTATS/UAI/CoRL/RLC 2024+、MLSys 2025+,均经 2026-09-07 实测核对;AAAI/CVPR/ICCV/ACL/EMNLP/NAACL 不在 OpenReview 上，是空壳组，已从注册表移除)。每个 venue 贡献一个有界候选池再参与全局排序，因此排在前面的 venue 不会吃光全部结果配额。默认每个 venue 最多打分 500 篇投稿;扫描被截断会产生结构化的 `CandidateScanTruncated` 诊断 (它提示"该 venue 的候选池不完整",不是致命错误)。`source_options`/CLI flags 支持：

- `mode`(`--openreview-mode`):`auto`(默认)/ `cache` / `remote`。`cache` 直接查本地 SQLite 缓存 (`data/openreview_cache/openreview.sqlite3`,约 9.7 万篇 accepted，毫秒级、无 500 截断);`auto` 缓存可用就用、否则回退 remote 并给出 `OpenReviewCacheFallback` 诊断;`remote` 总是走 API。缓存只存 accepted,`status=all` 会跳过缓存 (`OpenReviewCacheSkipped` 诊断)。缓存构建与增量：`uv run --no-project --with requests --with openreview-py scripts/openreview_cache.py build|update|import-iclr-seed|stats`(`update` 对未冻结的 venue-year 每个只发 1 个 count 探针，数字变化才整年重拉;ICLR 2017-2023 历史与被拒池来自 berenslab/iclr-dataset 种子)。
- `venues`(`--openreview-venues`):精确 venue ID 列表。
- `api_version`(`--openreview-api-version`):默认 `v2`;`v1` 是显式的旧会议模式 (ICLR ≤2023、NeurIPS 2021-2022),且要求显式给出 `venues`——它不是 429、challenge 或认证错误时的自动回退。v1 分页必须走 offset(`after` 游标会静默丢数据)。
- `status`(`--openreview-status`):默认 `accepted`(只搜已接收);`all` 额外包含在审、撤稿与被拒投稿。
- `scan_limit_per_venue`(`--openreview-scan-limit-per-venue`):默认 500(仅 remote 模式;缓存模式打分全量语料，无此限制)。

OpenAlex 默认使用词面 `search=`。`source_options['open_alex']['search_mode']`(`--openalex-search-mode`) 可选 `lexical`(默认) 或 `semantic`;语义模式上限 50 条且不分页，只在确实需要语义检索时使用。

DBLP 默认返回索引元数据、不做摘要富化;`source_options['dblp']['enrich_abstracts']=True`(`--dblp-enrich-abstracts`) 显式开启逐条串行 Crossref 请求，除非确实需要摘要，否则保持关闭。

arXiv 默认使用均衡查询：超过三个 token 的查询要求前两个词必须命中、其余至少命中一个。`source_options['arxiv']['query_mode']`(`--arxiv-query-mode`) 设为 `strict` 时要求每个 token 都命中。arXiv API 要求请求间隔 ≥ 约 3 秒，本技能以跨进程文件锁强制 4 秒下限 (可用 `ARXIV_MIN_INTERVAL` 覆盖)。

## 其余 CLI flags

上文未覆盖的 flag:

- `--start-date` / `--end-date`(YYYY-MM-DD):比年份更细的 post-filter，作用于所有来源结果;日期未知的记录保留。
- `--min-score N`:丢弃相关性 < N 的结果并打印丢弃数;默认不过滤。
- `--format text|markdown|json`(`--json` 为兼容别名)、`--raw`(逐来源视图，不去重不排序，仅 text)。
- `--output PATH`:把选定格式的渲染结果写到不覆盖的新文件;`--report-path PATH` 显式指定 Markdown 报告路径;`--no-save-report` 关闭报告落盘。
- `--no-log` / `--log-dir DIR`:运行日志开关与目录 (默认 `<artifact-root>/paper-search-logs/YYYY-MM/<run-id>/`,含 `run.json` + `stderr.log`,记录命令、命中数、诊断与耗时，不记密钥)。artifact root = `PAPER_SEARCH_ROOT` 环境变量 → 最近含 `.git` 的祖先目录 → cwd。
- `--no-parallel`:来源 worker 改串行 (隔离不变，很少需要)。

完整列表与互斥约束见 `--help`。

## HTTP 超时与预算配置

所有网络来源使用独立的连接超时与 socket 读空闲超时：

| 环境变量                                | 默认   | 含义                                                            |
| :-------------------------------------- | :----- | :-------------------------------------------------------------- |
| `PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS`  | `15`   | TCP/TLS 连接超时                                                |
| `PAPER_SEARCH_TIMEOUT_SECONDS`          | `300`  | 无响应字节到达时的最大等待                                      |
| `PAPER_SEARCH_<SOURCE>_TIMEOUT_SECONDS` | 未设置 | 按来源的读空闲覆盖，如 `PAPER_SEARCH_OPEN_ALEX_TIMEOUT_SECONDS` |
| `PAPER_SEARCH_MAX_ATTEMPTS`             | `4`    | 最大尝试次数 (含首次请求)                                       |
| `PAPER_SEARCH_SOURCE_BUDGET_SECONDS`    | `180`  | 单个来源 worker 的总墙钟预算;OpenReview 默认单独为 `600` 秒     |
| `PAPER_SEARCH_<SOURCE>_BUDGET_SECONDS`  | 未设置 | 按来源的墙钟覆盖                                                |

所有配置值必须为正;格式非法、零、负数、NaN 或无穷大会在 worker 启动前直接失败。读超时是 socket 空闲上限;来源预算从 worker 启动时刻起约束整个 worker。HTTP 429/500/502/503/504 有有界状态重试，重试间隔遵循 `Retry-After` 头;网络异常按指数退避重试 (DBLP 使用更长的退避基数)。

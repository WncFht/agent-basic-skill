# paper-search 维护手册 (给以后的 agent)

> SKILL.md 是**运行时契约**(怎么用这个技能);本文件是**维护上下文**(为什么是这样、坑在哪、怎么改)。两者读者不同，别互相吞并。

## 这个目录是什么

六个论文检索来源的统一 CLI:`arXiv / DBLP / OpenAlex / OpenReview / Semantic Scholar / Crossref`。默认启动稳定的 `OpenAlex / OpenReview / Crossref`;其余来源仍可用 `--sources` 显式开启。入口 `scripts/search_papers.py`(PEP 723 内联依赖),每个来源一个 connector 模块，OpenReview 通道额外带一个本地 SQLite 缓存。

```
scripts/
  search_papers.py                 # 编排器:并发调度、去重、排序
  source_registry.py               # 来源与合法 source_options 的元数据(唯一事实源)
  search_papers_by_openreview.py   # OpenReview connector(cache|remote 双模式)
  openreview_cache.py              # OpenReview 本地缓存 CLI(build/update/backfill/…)
  _http_runtime.py, _env.py        # 共享 HTTP 会话/重试 与 .env 加载
  postprocess.py                   # 相关性打分、去重、RRF 融合
data/
  openreview_venues.json           # venue 注册表(schema_version 2,实测核对)
  openreview_cache/                # SQLite 缓存(gitignored,可随时重建)
tests/
```

## 怎么跑

```bash
# 检索(SKILL.md 有完整契约;任何查询先自动推断输入,绝不问用户)
uv run --no-project .agents/skills/paper-search/scripts/search_papers.py \
  --query "..." --start-year 2024 --end-year 2026 --format markdown

# 测试(必须带齐依赖;pytest/requests/openreview-py/pyarrow)
cd .agents/skills/paper-search
uv run --quiet --no-project --with pytest --with requests --with openreview-py --with pyarrow \
  python3 -m pytest tests/ -q
```

**注意**:必须 `uv run --no-project`——本目录的 `pyproject.toml` 只有工具配置没有 `[project]` 表，uv 会报 "No project table found"。仓库根有 pre-commit 钩子 (ruff + ruff-format + mypy),mypy 沿 import 链检查，改任何 connector 前先确认其依赖文件也是 mypy-clean 的。

## OpenReview 通道架构

```
注册表 data/openreview_venues.json ──展开──> venue-year 列表
        │                                       │
        ▼                                       ▼
connector (mode: auto/cache/remote)    openreview_cache.py 拉取器
   cache: SQLite + FTS5,毫秒级           ├─ build      首拉(v2 全部 + v1 NeurIPS 回填)
   auto:  缓存可用就用,否则 remote        ├─ update     每 venue-year 1 个 count 探针,变了才整年重拉
   remote: 原始 API 扫描(兜底)            ├─ backfill-decisions  回填 ICLR 拒稿决定
                                          ├─ import-iclr-seed    berenslab 种子
                                          └─ stats / search      观测
```

原则：**accepted 数据的检索，本地严格优于 remote**(召回不受 500 条截断、毫秒级、无网络失败面);remote 只保留两个用途——`status=all` 查在审/撤稿，以及缓存尚未覆盖的新结果。

### 缓存维护命令 (在 `.agents/skills/paper-search/` 下执行)

```bash
uv run --no-project --with requests --with openreview-py scripts/openreview_cache.py update   # 日常增量
uv run --no-project --with requests --with openreview-py scripts/openreview_cache.py stats    # 看覆盖
uv run --no-project --with requests --with openreview-py scripts/openreview_cache.py backfill-decisions  # ICLR 决定回填
uv run --no-project --with requests --with openreview-py --with pyarrow \
  scripts/openreview_cache.py import-iclr-seed <parquet>                                       # 重导种子
uv run --no-project --with requests scripts/openreview_cache.py export-snapshot               # 快照 CSV 入 git
uv run --no-project --with requests --with openreview-py --with pyarrow \
  scripts/openreview_cache.py import-citations data/openreview_cache/nhop_citations_slim.parquet  # 引用/arxiv_id 预填
```

**月度自动化**:ZCode 定时任务 "OpenReview 缓存每月增量更新 (每月 1 日 09:00)" 每月自动跑 update → export-snapshot → stats 并汇报;快照有变化时提醒用户提交 (不自动 commit)。

### 当前覆盖基线 (2026-09-07)

97,248 行，accepted ≈ 5.8 万:ICLR 2017-2026 **全历史**(2017-2023 来自种子含被拒/撤稿;2026 每篇投稿都有决定),NeurIPS 2021-2025、ICML 2023-2026、TMLR(rolling)、COLM/AISTATS/UAI/CoRL/RLC 2024+/MLSys 2025+ 仅 accepted。**不在 OpenReview 上**:AAAI/CVPR/ICCV/ECCV/SIGIR/KDD/IJCAI/AAMAS/RSS(空壳组或没建组),ACL/EMNLP/NAACL 正式组 (真实流程在 ARR)——别再往注册表里加它们。

## 硬坑清单 (每条都实测踩过，改代码前先读)

1. **group 存在 ≠ 会议在 OpenReview 上**。CVPR/AAAI/ACL 等 group 存在、`submission_name='Submission'`,但 invitation 下 0 条 notes(真实流程在 CMT/ARR)。加任何新 venue 前，必须实测 `{vid}/-/Submission` 下有 notes 且 `content.venueid` 过滤计数合理。
2. **v1 API 的 `after` 游标会静默丢数据**(cdate 相同的批量笔记被跳过:NeurIPS 2022 after 1,605 vs offset 2,824)。v1 全量拉取一律用 offset。
3. **openreview-py 的 `with_count=True` 只在 `offset is None` 时返回 `(notes, count)` 元组**;带 offset 时返回裸列表。计数探针只在首页发。
4. **ICLR 2023 及更早在 API v1**,且 v1 的 venueid 不可作 accepted 证据 (ICLR 2022 venueid 过滤 1,376，官方 1,094;seed 按 Decision 解析才是对的)。ICLR 2024 起才在 v2,venueid 过滤才可靠。
5. **ICLR 的非录用稿挂在嵌套 venueid 下**:`{vid}/Conference/Rejected_Submission`、`Withdrawn_Submission`、`Desk_Rejected_Submission`,要用主 invitation + 嵌套 venueid 作 content 过滤;平级形式 (`ICLR.cc/2026/Rejected_Submission`) 恒为 0。决定日后跑 `backfill-decisions`。
6. **NeurIPS 被拒稿完全不公开**(rejected/withdrawn venueid 计数为 0)——"全量 submissions 缓存"只对 ICLR/TMLR 有意义。
7. **TMLR 的 group 不声明 `submission_name`**,invitation 要回退探测;它没有年份、是 rolling journal，永不冻结，每次 update 重探。
8. **种子行永不覆盖 API 行**:`INSERT OR IGNORE`(seed)vs `ON CONFLICT DO UPDATE`(API)。反过来 API 行先在时，seed 的同 id 行会被忽略——这是故意的 (API 是权威)。
9. **FTS5 的 unicode61 分词把连字符/引号当分隔符**:MATCH 表达式必须按非字母数字**切分**词条而不是剔除，否则 "few-shot" 查不到 "few shot"。
10. **OpenReview 需要登录态**(匿名 403 ChallengeRequiredError);`.env` 的 `OPENREVIEW_USER/PASS` 由 `_env.load_env_once` 加载。限速未公开，社区实测 ~100 请求/窗口，缓存拉取用跨进程 flock 节流 (`OPENREVIEW_MIN_INTERVAL`,默认 0.5s)+ build/update 全程操作锁。
11. **引用数不来自 OpenReview**。两层来源:① `import-citations` 用 nhop/OpenReview 的 S2 crosswalk(`openreview_submission_id` 精确 join,**只填 NULL**,可重复跑) 预填 `citation_count` 与 `arxiv_id`,slim 交叉表 2.2MB 存于 `data/openreview_cache/nhop_citations_slim.parquet`(gitignored;用 duckdb 远程列投影重生成，别整下 1.2GB 原库);② 查询时的 `--enrich-citations`(OpenAlex) 继续兜新数据。

## 数据源与许可

| 来源                                                                                             | 用途                                 | 许可              |
| ------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| [berenslab/iclr-dataset](https://github.com/berenslab/iclr-dataset)                              | ICLR 2017-2023 历史种子              | MIT               |
| [ReviewArena](https://huggingface.co/datasets/Samarth0710/reviewarena)                           | 跨会评审 (未来按需)                  | CC-BY-4.0         |
| [nhop/OpenReview](https://huggingface.co/datasets/nhop/OpenReview)                               | S2 引用数/arxiv_id crosswalk(已接入) | CC-BY-NC-4.0      |
| [WENJINLIU/Paper-Review-Dataset](https://huggingface.co/datasets/WENJINLIU/Paper-Review-Dataset) | 评审参考                             | unknown，勿直接搬 |

## 已知遗留问题

- 缓存里 `publication_status != 'accepted'` 的行 (ICLR 历史 ~4 万篇) 暂不参与检索 (cache_search 固定 accepted-only);若要开放，先想清楚与 `status=all`→remote 的语义关系。
- 引用预填的时效边界:nhop 快照 (2025-04) 覆盖到 2024 出分批次，ICLR/NeurIPS 2025+ 的引用数靠 `--enrich-citations` 或未来版本的 nhop 交叉表 (只填 NULL，直接重跑 import-citations 即可)。
- 调研全记录见 vault:`杂七杂八/OpenReview 通道优化调研——会议全景与开源生态(2026-09-07).md`。

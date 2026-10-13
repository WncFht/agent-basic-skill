---
name: paper-search
description: 在 arXiv、DBLP、OpenAlex、OpenReview、Semantic Scholar、Crossref 检索论文。找论文、related work、prior art、某主题最新文献，或提到年份区间、NeurIPS/ICLR/ICML 等会议时触发。
---

# paper-search

六个论文检索来源的统一 CLI，每来源一个 connector，跨源去重后按相关性排序。底线是**完整召回**:宁可多给，不可漏掉;来源失败不中断其他来源，诊断逐字呈现。

默认并发 `open_alex openreview crossref`;`arxiv` / `semantic_scholar` / `dblp` 用 `--sources` 显式加入 (预印本 → `arxiv`,引用数与引用关系 → `semantic_scholar`,CS 文献索引 → `dblp`)。

## 流程

### 1. 推断输入并直接运行

从用户消息自动推断全部输入，第一轮直接运行，不向用户索要确认。

- 查询 → `--query "..."`;多查询并集用 `--queries 'a|b|c'`(竖线分隔)。查询含 arXiv ID 或 DOI 时**原样透传**:CLI 直查权威端点并绕过年份过滤，不改写不丢弃。
- 年份 → `--start-year`(默认两年前)、`--end-year`(默认今年);更细粒度用 `--start-date` / `--end-date`。
- 每来源条数 → `--max-papers`(默认 50;多查询融合去重后按此截断)。

```bash
uv run .agents/skills/paper-search/scripts/search_papers.py \
  --query "diffusion policy robotics" --start-year 2023 --end-year 2026 --format markdown
```

`uv run` 依 PEP 723 内联声明自动装依赖;装有 `requests` + `openreview-py` 的 python3 也可直接跑。

### 2. 按需加 flags

完整列表跑 `--help`;常用的是这几个非默认语义：

```bash
--sources arxiv openreview     # 覆盖默认来源集合
--enrich-citations             # 用 OpenAlex 批量回填缺失被引数
--min-score 2                  # 丢相关性 < N 的结果;要完整召回就别传
--openreview-status all        # 含在审/被拒/撤稿(绕过缓存走 API,需 .env 凭据)
--openreview-mode remote       # 拉缓存外的新结果,同样需凭据
--raw                          # 逐来源视图,不去重不排序(仅 text)
--no-log / --no-save-report    # 关运行日志 / 关报告落盘
```

### 3. OpenReview 缓存

`openreview` 默认 `auto`:本地 SQLite 缓存 (`data/openreview_cache/`,约 9.7 万条 accepted，毫秒级、无 API 截断) 可用就用，否则回退 API 并给出诊断。`--openreview-status all` 自动绕过缓存。模式细节、凭据要求、缓存 build/update 命令见 `references/programmatic_api.md`,架构与已知坑见 `README.md`。

### 4. 交付

`--format markdown` 的输出即成品报告，同时自动落盘到 `<artifact-root>/paper-search-reports/`(不覆盖)。artifact root 的解析顺序：`PAPER_SEARCH_ROOT` 环境变量 → 最近的含 `.git` 的祖先目录 (项目根) → `$PWD`。运行日志同理落 `<artifact-root>/paper-search-logs/`。在仓库内从任何子目录调用，产物都汇聚到项目根。

**Done when**:报告**原样完整**交给用户 (不折叠、不缩略、不只给 Top N),落盘路径已告知，stderr 来源错误逐字呈现不隐藏。

报告结构：去重排序总表 (DOI / arXiv ID 强去重，规范化标题只在元数据不冲突时兜底;`[survey]` 打标沉底但不丢弃)→ 来源诊断 → 七段总结 (概述、趋势、主题、关键词频次、高被引论文、高被引一作、阅读建议)。

### 5. model_knowledge 补充 (可选)

API 对奠基性老论文与跨学科经典低召回，由模型回忆补足。每条候选必须先在线核实标题、年份、venue、URL 并与 API 结果去重，核实失败宁可不给。协议与表格格式见 `references/model_knowledge.md`;表格插在结果表之后、总结之前。

## 逐来源深参数

函数式 API、逐来源 source_options、超时与预算环境变量见 `references/programmatic_api.md`。

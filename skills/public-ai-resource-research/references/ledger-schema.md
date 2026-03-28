# Ledger 字段说明

初始化脚手架会生成 5 个文件。保持 id 稳定，这样后续 probe、报表或网站都能可靠地关联这些数据。

## `query-matrix.csv`

- `query_id`：稳定 id，例如 `q001`
- `objective`：这条查询要解决什么问题
- `platform`：`linux.do`、`github`、`web` 等
- `search_surface`：站内搜索、搜索引擎、文档、监测页、镜像等
- `query_text`：实际执行的查询语句或接口
- `recency_days`：为空或整数
- `status`：planned、run、blocked、superseded
- `notes`：为什么有效或为什么失败

## `source-ledger.csv`

- `source_id`：稳定 id，例如 `s001`
- `platform`：域名或平台族
- `source_type`：topic、docs、status page、repo、blog、directory
- `title`：来源标题
- `canonical_url`：公开 URL
- `author`：作者或运营者
- `published_date`：已知的发布日期
- `accessed_date`：访问日期
- `entity_candidates`：候选实体，分号分隔
- `evidence_strength`：official、community-primary、community-secondary、mirror、inference
- `sensitivity`：public、mixed、sensitive-reference
- `notes`：简短提取说明

## `entity-ledger.csv`

- `entity_id`：稳定 id，例如 `e001`
- `canonical_name`：标准名
- `aliases`：别名，分号分隔
- `entity_type`：station、relay、directory、monitor、signup portal、status page
- `discovery_sources`：发现它的 source id，分号分隔
- `official_site_url`：官网
- `dashboard_url`：公开监测页或后台入口
- `public_base_url`：公开且非敏感的 API base URL
- `auth_mode`：public、OAuth、invite、CDK、signup、per-user-key、unknown
- `access_gate`：访问门槛说明
- `claimed_models`：来源中声称支持的模型，分号分隔
- `observed_models`：后续经官方文档或验证确认的模型
- `current_status`：alive、degraded、invite-only、login-only、migrated、probably-dead、dead、unknown
- `status_date`：状态对应日期
- `confidence`：low、medium、high
- `notes`：归并理由、注意事项、待确认问题

## `access-observations.csv`

- `observation_id`：稳定 id，例如 `a001`
- `entity_id`：所属实体
- `source_id`：观察来自哪个 source
- `observation_type`：base-url、docs-url、signup-flow、key-mentioned、token-mentioned、cdk-mentioned
- `public_base_url`：只有公开且非敏感时才存
- `docs_url`：公开文档或后台页
- `credential_observed`：yes / no
- `credential_kind`：api-key、auth-token、cookie、invite-code、unknown
- `credential_visibility`：public-post、screenshot、reply、operator-message、user-authorized
- `authorized_secret_ref`：用户提供的安全引用，或留空
- `model_scope`：该观察附近提到的模型范围
- `raw_status`：来源中的原始措辞
- `last_seen_date`：最后一次观察到的日期
- `notes`：脱敏后的上下文说明

`authorized_secret_ref` 的作用是：后续 probe skill 可以消费用户授权的 secret 引用，而 discovery skill 不需要保存明文。

## `status-checks.csv`

- `check_id`：稳定 id，例如 `c001`
- `entity_id`：所属实体
- `target_kind`：public-base-url、docs-url、signup-page、status-page
- `target_value`：公开 URL 或标签
- `check_method`：browser、curl、docs-read、later-probe、unknown
- `check_date`：执行日期
- `result`：reachable、blocked、stale、mismatch、pending
- `evidence_url_or_path`：支撑这个结果的 URL 或本地路径
- `notes`：为什么这个目标值得后续验证

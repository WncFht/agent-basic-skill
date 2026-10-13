# Lane ABI v1 / pack.toml / journal 契约

fetch-engine 与 lane 之间的唯一协议面。设计依据：`~/fetch-arch/PLAN.md`（9-agent 调研 + 实跑实验）。本文即规范——实现与本文冲突时改实现。

## 1. 进程模型

engine（`fetch_engine.py`，py≥3.11 stdlib）spawn lane 子进程。lane 是任何可执行文件（bash/python/二进制）。**lane 必须可脱离 engine 裸跑**（`lane-run` 旁路工具）。

## 2. stdin（恰好一行 JSON，然后关闭）

```json
{
    "job_id": "20260923-abc123",
    "identity": {
        "raw": "<原始输入>",
        "key": "<lgc key>",
        "kind": "article|video|...",
        "params": {}
    },
    "ctx": {
        "artifact_dir": "<job 目录>/artifacts/",
        "journal_dir": "<job 目录>/",
        "budget_ms": 60000,
        "cred_handle": "<不透明句柄或空>",
        "key": "<同 identity.key，便利冗余>"
    }
}
```

lane 不许假设 artifact_dir 之外可写（meta-lane 除外，见 §8）。产物只能写进 artifact_dir。

## 3. stdout（JSONL，逐行 flush，无任何非 JSON 行）

每行一个对象，`type` ∈ {`progress`, `artifact`, `data`, `error`, `call`, `result`}：

| type       | 字段                                                                | 语义                                                                                 |
| ---------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `progress` | `{msg, pct?/bytes_done?}`                                           | 人类可读进度；bytes_done 无 pct 也要能发                                             |
| `artifact` | `{path, name}`                                                      | 声明一件已落盘产物（path 必须在 artifact_dir 内，name 是消费方契约名如 `video.mp4`） |
| `call`     | `{tool, argv/note}`                                                 | 车道内再分工的自报（记账用，engine 不动作）                                          |
| `error`    | `{class, scope_hint?, evidence, retryable:bool, needs_human?:bool}` | 分类错误（见 §6）；可作为终态也可中途发                                              |
| `result`   | `{items:[{path,name,bytes?,sha256?}], params?}`                     | **成功终态**，items 可为空数组外的复数；`params` 见下注                              |
| `data`     | `{payload}`                                                         | **无产物的终态**（--list-courses 等枚举操作）                                        |

**终态规则**：恰好一个 `result` 或终态 `error` 或 `data`。rc=0 但无终态行 → runner 合成 `noresults` 错误（已实验验证）。

`result.params`（dict，可选）：lane 上报产物侧语义字段（media 平价：height/req_cap/langs_obtained/subs_known/files_meta），engine 入库时 merge 在请求 params 之上——`--satisfies` 探针断言的是产物侧值不是请求值。

## 4. stderr / rc

- stderr = 自由文本副通道，runner 收进 `journal_dir/<job_id>.stderr.log`（限容 64KB 截断）。
- rc：`0`=已自报终态；`10`=skipped/notcovered（无终态行的合法跳过）；其他=crash → runner 合成 `{class:lane_crash, evidence:stderr尾部}`。
- rc10 与终态行的优先级：**终态行赢**（发了 result 又退 10 → 按 result 处理，journal 记 `rc10_after_terminal`）。

## 5. env

白名单制，不裸继承父进程：runner 只注入 `cred_handle` 翻译出的指名 env、`HTTP_PROXY`/`http_proxy`（pack.toml egress 声明时）、`PATH`、`HOME`、`LANG`。lane 需要的其他 env 必须在 pack.toml `needs.env` 声明（缺 → admit 判 `dep_absent`）。

## 6. 错误闭集（9 类）

`noresults` / `notcovered` / `permanent` / `auth_expired` / `challenge_needed` / `rate_limited` / `transient` / `budget_exceeded` / `dep_absent`（仅 admit 判词，lane 不产出）+ runner 合成 `lane_crash`/`protocol_violation`。

scope 格：`call-local < lane×key < lane×host < lane < channel < cred_fp < global`。

记账规则（engine 侧）：`auth_expired`→cred_fp 域 evict+ 闸，**不进 lane breaker**；`challenge_needed`→lane×host 1-24h；`rate_limited`→lane×host，TTL=Retry-After；`transient`→lane breaker++ + 短 lane×key neg；`permanent`→内容键 90d 墓碑（base_key 与内容键不同 → 基键同碑，zhihu 变体共享平价）；`noresults`→内容键 24h；`notcovered`→lane×key 30d（key 取 base_key 记账键），但 `scope_hint="params"` 时不记账；`dep_absent`/`budget_exceeded`→不记账；lane 声明 `fail_note=false` → transient/lane_crash/protocol_violation 不上账。

`scope_hint`（error 可选字段）：声明拒绝的作用域。`"params"` = 拒绝针对请求形（参数校验失败、参数级不覆盖）而非内容覆盖——lane×key 墓碑没有 params 维度，参数级拒绝上账会把同键其余参数组合陪葬（实锤：`--mode` 空格形坍成 `mode=True` → notcovered → 同论文 mode=full 也被锁 30d）。无 hint 的 notcovered 维持内容级墓碑语义。

## 7. engine 对外契约（兼容壳）

- rc 压缩：`0` served / `2` usage / `3` noresults|notcovered / `4` permanent-deleted / `5` transient-exhausted / `6` auth|challenge / `7` budget。
- 人类行：每件产物 stdout 打 `==> 已存 <abs path>`；缓存命中 stderr 打 `cache: hit(<lane>,<age>)`。lane 自己**不发**这两类行。
- `--json`：stdout 改打单行 envelope `{job_id, rc, class?, items[], data?, journal}`。

## 8. pack.toml（每 channel 一个，packs/<name>/pack.toml）

```toml
[pack]
name = "generic"
abi = 1
kinds = ["article"]              # identity 产物
kind_required = true             # 可选：kind_by_url 判不出 kind → admit 拒 rc2
                                 # （zhihu 平价——无兜底 kind 就不发车）
[match]
hosts = ["*"]                    # 路由命中声明（engine 用 host 解析，不是子串）
schemes = ["http", "https"]
[identity]
keyexpr = "art:{url}"            # 键模板；也可是 table {default=..., <kind>=...}
key_params = []                  # 影响键的 param 名（显式传入）；清空这些 param
                                 # 重渲 keyexpr 即得 base_key——车道账/probe 基键/
                                 # 墓碑共享面自动派生（zhihu lk=ZBASE 平价）
capture = { vid = '(v=|youtu\.be/)([A-Za-z0-9_-]+)' }  # URL 正则捕获进模板变量
capture_defaults = { part = "1" }                     # 捕获失败的默认值
kind_by_url = { opus = 'opus|t\.bilibili\.com' }      # URL 模式→kind（显式 param 优先）
probe_base_variants = ["+f"]     # 可选：内容键以这些变体后缀结尾时探测链先探
                                 # base_key 再探内容键（zhihu +f：基键命中即可供
                                 # 快览；+c 不探——基键无评论）
# 可选 satisfies 表：声明式"请求→满足断言"迁移合同（media-get:774 同构）。
# 每键 {param=请求参数名，default?=缺省值，type?=int|csv|bool|str}——请求命中
# 时 engine 把声明的参数按 type 归一（int→整型，csv→去空逗号拆列表，bool→
# 真值表）组成 --satisfies JSON 传给 lgc get；entry 的 params 与断言不匹配 →
# miss（防 1080 包误供 720 请求）。param 缺席且无 default → 该键不进断言。
satisfies = { max_height = { param = "max_height", default = 1080, type = "int" } }
# 任一被 keyexpr 引用的 capture 落空且无默认 → 回退 "{kind}:{url}" 每 URL 键，防塌缩
[[lanes]]
name = "connector"
exec = "monolith"                # 特殊值 monolith = 经 monolith_shim 包旧 connector；
                                 # 否则相对 pack_dir 的可执行路径（lane ABI 原生）
connector = "generic-get"        # monolith 时必填：原 connector 路径（pack_dir→PATH）
kinds = ["article"]              # 可选：lane 级 kind 闸（窄于 pack kinds 时生效）
params_gate = { variant = ["", "+f"] }  # 可选：param→允许值表，不匹配则 admit 跳过
store = "base"                   # 可选："base" → 本 lane 产物入 base_key
                                 #（zhihu jina/firecrawl 全文永远入基键）；缺省入内容键
store_keep = true                # 可选：put --keep（无过期、partial-hit、明文键）——
                                 # 长效产物（字幕轨/封面）不再被 ttl 逐出
store_atomic = true              # 可选：put --atomic（整包超 max_bundle_mb 拒收、
                                 # 逐文件跳 max_blob 帽）——多文件 bundles 的原子语义
fail_note = false                # 可选：false → transient/lane_crash/
                                 # protocol_violation 不记 lane_fail/note（默认 true）
rc_map = { "2" = "notcovered" }  # 可选：monolith connector rc→class 覆盖
needs = { tools = ["curl"], env = [], env_optional = [], creds = [] }
egress = { hosts = ["*"], proxy = "optional" }
budget_ms = 120000
[[routes]]                       # 可选：kind×params → 有序 lane 臂；首中胜。
kinds = ["ans"]                  # params 为子集真值匹配——声明的每个 param 必须
params = { fast = true }         # 与请求 params 等值；无 params → 该 kind 兜底臂
lanes = ["tardis", "jina"]       # 臂内 lane 按序降级；kind 无任何臂命中 → 拒 rc2。
                                 # 整个 routes 缺席 → 全量 [[lanes]] 声明序
```

- `needs.env`：缺失 → admit 判 dep_absent；`env_optional`：存在则透传、缺失不闸（如 FIRECRAWL_API_KEY）。
- `needs.creds`：凭证**文件路径**列表（`~` 展开），软声明不闸——只喂 `ctx.cred_handle` 指纹（缺失文件按 "missing" 参与哈希，connector 自行降级或报 auth_expired）。engine 不用它做 lgc cred 域 scoping——`auth_expired` 记账永远不传显式 fp，由 lgc 按键 kind 自导出 cred8（防两实现哈希分歧劈裂 scope）。
- monolith exec 时 engine 经 `MONOLITH_CONF` env 把 lane 配置 JSON 传给 monolith_shim.py。
- `[monolith]` 段：`argv`（模板 {url}/{artifact_dir}/{param:k}）、`flag_params`（param→旗标）、`kind_flags`（kind→旗标，如 fast→--fast）、`env_passthrough`。
- `lgc_off = false` → **self-managed pack**：connector 保留自己的 lgc 缓存/claim/neg/lane-note 全套，engine 对内容键**零接触**——不探（content probe 与 cooling probe 全跳）、不写（无 store put）、不记账（record_error/lane_hit 全跳）。journal admit 记 `gate=cache verdict=self-managed`。适用：media/canvas 这类内嵌 lgc 协议（--claim single-flight、value 键域、satisfies 断言）的 wrap pack——engine 插手只会双写垃圾 entry + 与 connector 内部 claim 互等。delguard neg 不受影响（内容键契约，connector 键域重合时墓碑照样生效）。

meta-lane（铸凭证）额外字段 `writes_cred = <domain>`，获得 cred-store 安装权（唯一例外可写 artifact_dir 外——只许写 cred store 指定路径）。

## 9. journal

job 根目录：`$FETCH_ENGINE_JOBS` 否则 `$LGC_HOME/link-get/jobs`（默认 `~/.cache/link-get/jobs`）——测试隔离全靠这两个 env。每 job 一个目录：`<job_id>/{journal.jsonl, <lane>.stderr.log, artifacts/}`。journal.jsonl 每步一行 `{ts, job_id, stage, decision|event, lane?, class?, detail}`，append-only 无上限滚动；replay 断言只依赖行序列。

SSRF 闸 override：`FETCH_ENGINE_ALLOW_PRIVATE=1` 放行私网/loopback（默认拒）——测试与内网抓取的唯一例外口。

inflight（single-flight）：engine 经 `lgc get --claim --owner-pid <pid> --wait <s>` 拿槽位，失败路径 `lgc release`；lgc 自身靠 pid-alive+INFLIGHT_STALE 自愈。缓存读解析 `lgc get --json` 的 materialized paths（回退：非 `cache:`/`lgc:` 前缀行）。

## 10. monolith shim 契约

`monolith_shim.py`：读 stdin JSON → 按 pack.toml 构造 connector argv/env（含 `LGC_OFF=1` 阻断旧缓存路径——engine 统一管缓存）→ spawn → 收 artifacts（dir-diff 或 connector 自报）→ JSONL 终态。connector 的 stdout/stderr 全部进 stderr 捕获，不得漏进 lane stdout。

## 11. 不变量（conformance harness 断言项）

1. stdout 每行可 JSON.parse 且带合法 type；2. 恰好一个终态行；3. rc/终态一致矩阵；4. 超时（budget+grace 400ms）必被杀且 journal 记 budget_exceeded；5. artifact path 不出 artifact_dir；6. items[].name 非空；7. 无终态+rc0 → noresults 合成；8. journal 行全带 job_id。

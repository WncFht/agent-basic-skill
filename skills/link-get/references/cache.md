# lgc 缓存层契约（后来者必读）

统一缓存层：`lgc`（python3 stdlib 单文件 CLI，`~/.local/bin/lgc` 软链分发）

- `_lgc.sh`（bash helper 规范块）。ns ∈ `link-get / zhihu-skill / canvas-skill`，根 `~/.cache/<ns>/`（700），index.sqlite3（WAL，user_version=1），`blobs/<hh>/<kh>/v<seq>/`（文件 400），`locks/`（永不 GC），`inflight/`（mkdir 单飞）。

## 不变量（违反即 bug）

1. **lgc 永不在交付路径**：车道产物先落 `-o` 交付用户，然后才 `lgc put`；put 失败只 warn，不改连接器出口码。收编走 `$OUT/.lgc-stage-$$/`（同 fs）
    - 产物名白名单，禁 `find -newer`、禁固定清单。
2. **优雅降级**：`command -v lgc` 缺席 → 全 helper 直通 miss；`source` 必须`[ -f "$DIR/_lgc.sh" ] && source … || true`，缺文件时调用方自备 stub。z_*/_lgc() 之外**禁止裸 lgc 调用**（key/cat/list 经 z_key/z_cat/z_list）。
3. **写路径全 `|| true`**；`z_probe` 恒 rc0，结果走 ZHIT/ZRC/ZNEG/ZPATHS；禁止 `P=$(zget …)` 形态；lgc 任何 rc 永不进出口码。
4. **材料化两阶段原子**：`--into/.lgc-mat-<pid>/` 全量就绪后统一 rename；失败清场 + 回滚 rc≠0；落位 `chmod u+w`（blob 是 400）。reflink→copy2，**永不 hardlink**。
5. **neg 永不覆盖未过期 pos**；pos 总覆盖 neg。denylist 精确名表+glob（BBDown.data/cookie.txt/cookies.json/\*.cookies/.netrc/`.*`/\*.part/ \*.tmp/.lgc-\*/.tardis-\*/\*进度\*/\*.log）在 lgc put 内强制执行；删除签名（5 模板扫前 64KB）拒收 rc4。
6. **inflight**：mkdir 认领，`--owner-pid $$` 写 owner；死 pid 或 marker>6h 偷锁（无 15min 超时偷）；`neg/release` 只清自己的 marker；locks/ 永不 GC。
7. **satisfies 双字段**：manifest.params 存 `height`+`req_cap`（+langs_obtained/ subs_known/has_all/files[].viewNum|kind）；命中 iff `height ≤ req.max_height≤ req_cap` 且 `req.langs ⊆ langs_obtained ∪ 证缺`。**未知/缺失字段 →不满足**（唯一合法方向）。producer `name@int`：put `--producer`，get `--require-producer name@min`（不符→miss 惰性删）。
8. **版本握手**：连接器永不比版本号，只查 cap（`lgc has`）。旗标否决：缺 cap → 整条 miss/no-op，**绝不丢旗标发降级调用**。`cred` 缺席 →cred 敏感 kind 不缓存；`delguard` 缺席 → z_store 内联 grep 兜底。
9. **bash ≥3.2 干净**：禁 declare -A / mapfile / readarray / ${var^^} / &>> / coproc；`readlink -f` 一律 POSIX while-loop idiom；`stat -c %Y 2>/dev/null || stat -f %m` 双写（GNU 优先——BSD-first 在 GNU 上拿到文件系统 dump）；usage() 用`sed -n '2,/^[^#]/p' "$0" | sed '$d'`。
10. **可观测**：probe 打一行 `cache: hit(lane,age)|miss|wait(pid,age)|
neg:reason(age)|err(errno)|off` 到 stderr；命中照常打 `==> 已存 …`；hits/misses/neg_hits/lane_skips 进 counters，`lgc stats` 可查。

## rc 语义

- `lgc get`：0 hit / 1 miss / 3 neg:notrack / 4 neg:deleted /
  5 neg:unavailable|ratelimited / 6 miss+ 已认领 inflight（你去抓）/ 7 miss+ 他人 inflight 超时（并行抓）。
- `lgc put`：0 入库 / 4 删除签名拒收 / 其他非 0=缓存层故障（调用方吞掉）。
- `lgc lane probe`：0 车道可用 / 1 lane-neg 或 breaker 跳。
- 连接器：0 成功 / 2 参数错 / 3 无轨或未镜像 / 4 已删 / 5 车道全挂或运行时。lgc rc 永不进出口码（z_probe 映射到 ZHIT/ZRC，连接器按 ZRC 回放 4/5/3）。

## 键规则

- 连接器传 `<kind>:<raw>`，归一化只在 lgc 内：URL lowercase host、去 fragment、query 排序、剥除 `utm_*|spm*|vd_source|bbid|ts|fbclid|gclid|ref|src|track|clicktime|poc_token|si|sn|chksm|scene|srcid|from_*|from|share_*|sharer_*|exportkey`；zhuanlan→www、p/、youtu.be→watch?v=。
- content-id 提取优先于归一 URL：wechat=`__biz+mid+idx`（/s/ token 不去重
  是承认项）、yt:_=VID、bili:_=BVID+p=N（缺省 p1）、bili:b23=短码、media=平台 ID 否则归一 URL、zhihu kinds=数字 id/token、arxiv=arxiv id。
- **剥除表与 id 源互斥**：`__biz/mid/idx/BVID/p` 永不得进剥除表；加剥除参数前先查 id 提取表。
- cred 域：cred 敏感 kind 键尾 `#<cred8>`（zhihu=cookie.txt+settings.toml；bili/media=cookies/bilibili.txt，BBDown.data 仅兜底；canvas=tok8 已入键）。连接器 `--cred` 显式传优先。**车道级键永不带 cred 域**。
- 形态旗标入键（改变产物集合）：zhihu `+c`/`+f`；派生参数不进键（cover_at/langs/max_height 走 satisfies 或命中后本地派生）。

## TTL / neg（defaults in lgc; `lgc has kind:<k>` 可查）

正：article/wechat 7d · yt.tr/subs、bili.subs、b23 30d · yt.fast/bili.opus 7d ·
meta 系 24h · media 30d · art/ans/zv/pin 3d · q/ppl 1d · col 6h ·tecl 180d · jwt 20min · donor 7d · lec-list 15min（仅展示）· api ≤30min ·src 10min · file/lec 无 TTL（lec keep=1）· arxiv 24h。表外 kind pos 默认 3600s 且 neg 拒收（必须显式 `--ttl`）。
canvas api 白名单外**永禁入库**——sessionless_launch 一次性签名 URL 在
`_API_DENY` 上（入库即稳态死：签名过期后命中旧 entry 必炸）。
负（内容级）：deleted 90d→rc4 · notrack 24h→rc3 · unavailable/ratelimited
15min→rc5。车道级 `lane:<lane>:<key>`：tardis-miss 30d · lane-fail（默认 1h，
调用方按证据传 --ttl 15min/24h）。breaker：同 lane 600s 内 ≥3 次 fail →z_lane 跳 600s；`command -v` 缺席的车道**不记 lane-fail**。

## 用户面旗标（env 传播：export LGC_*）

`--refresh`→`LGC_REFRESH=1`（跳过全部缓存读——正/负/车道级，成功仍写回；
jina 加 `X-No-Cache: true`）；`--no-cache`→`LGC_OFF=1`（读写全绕=裸行为）；
`--cache-ttl S`→`LGC_TTL`（只覆盖本次 pos put，不作用 neg）。解析点清单
（加 env 旗标必须全同步）：link-get / lg_args(_common.sh) / zhihu-get /
zhihu-tardis / media-get / canvas-get / arxiv-tex。

## 接入清单（新连接器/车道，六步）

1. 嵌 PROBE-BLOCK（bash source / python 内嵌），marker 版本与 canonical 一致；zhihu-tardis 内嵌同文本，`scripts/connectors/_lgc.sh` 是唯一事实源（无第二拷贝）。
2. 头注释 `# lgc-needs: get put neg lane satisfies cred producer …`。
3. 车道链逐车道：`z_lane $lane || continue` → 跑 → `rc=$?` →0→`z_store --lane`；4→`z_note deleted`+exit4；*→`z_lfail`/continue。
4. 传给 z_* 的每个旗标过 cap 否决（helper 内建）；未知 lgc rc→miss。
5. `command -v` 先验车道工具（缺席不记 lane-fail）；ENOSPC/风控瞬时态不进内容级 neg（zhihu 域 jina 荒原=deleted 例外，是墓碑证据）。
6. 收编 `$OUT/.lgc-stage-$$/`+白名单；束 put 带 `--producer <名>@<int>`；cred 敏感必传 `--cred <cred8>`（sha256[凭证字节按固定序](:8)）。

新 kind：表外即可用（pos 3600s 默认；neg 必须 --ttl）；收进 lgc 表=加一行。
新 ns：lgc NS_WHITELIST 加一行 + setup.sh mkdir + doctor 清单。

## 回滚四式（半径从小到大）

1. `LGC_OFF=1 <cmd>` 单次读写全绕。
2. `~/.config/lgc/config` 写 `off=1`（持久）或 `rm ~/.local/bin/lgc`（helper 直通 miss，连接器行为=无缓存）。
3. 单类关停：lgc kind 表 TTL=0（首选）；同文件叠加 WP 只支持反序连撤。
4. 整体：逆 rollout 序 revert + `rm -rf ~/.cache/{link-get,zhihu-skill,canvas-skill}` + `rm ~/.local/bin/lgc`。

凭证轮换后：`lgc clear --cred <旧cred8|tok8|anon>` 清尸体（含 keep=1 孤儿）；
`lgc prune --dead-cred` 清 cred 域不再匹配现凭证的条目。

## 杂项

- `LGC_STORE_KEY=0`：row.key 不存明文（keep=1 强制明文——rebuild 依赖）。
- index 损坏 → 按 `blobs/*/v*/manifest.json` 重索引；不可解析进`quarantine/` 不删；keep=1 豁免孤儿清扫。
- user_version>已知 → 全面拒写、读退化 miss（绝不降级写）。
- 归一化改版 → NORM+1，open 自动 rekey（明文 key 重算 kh+rename blob 目录）。
- `lgc selftest`/`has`/`--version` 三面零副作用（不 ensure_dirs、不碰 sqlite）。

## 装机（新机 rollout）

```sh
rsync -a ~/.agents/skills/{link-get,video-render-pdf} \
  <host>:~/.agents/skills/
ssh <host> bash ~/.agents/skills/link-get/scripts/setup.sh  # lgc → ~/.local/bin
```

冒烟五步（全绿才算落地）：`lgc --version` banner → `lgc has` 能力表 →
`lgc-selftest.sh`（含 PROBE-BLOCK 对账）→ `/bin/bash -n` 扫全部 bash 连接器（macOS 自带 3.2 是真实兼容面）→ 各 skill `doctor.sh`。lgc 缺席不算故障——helper 直通 miss，但 doctor 会标 ✗ 提醒补装。

舰队现状（2026-09-22）：本机（Arch, py3.14）+ fht-mba（macOS, bash 3.2）
均已全绿；两台共用同一 commit，无分叉。

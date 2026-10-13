# 各语言配方

一种类型一张卡，census 命中的类型就应用对应卡。每张卡给出：安装依赖、追加到 `.pre-commit-config.yaml` 的 `hooks:` 下的 hook 块、`.github/workflows/ci.yml` 的 CI 补充、先修后挂用的**验证**命令、注意事项。

yaml 块统一写在 0 列（本文件保持 prettier-clean——内嵌代码块会被重排）。粘贴时缩进：hook 条目在 `hooks:` 下缩进 6 格；CI job 在 `jobs:` 下缩进 2 格；step 条目在 `steps:` 下缩进 6 格。

base 已覆盖 markdown + yaml + gitleaks——这三者没有卡（yaml 槽 = prettier 结构格式 + `check-yaml-comments.py` 注释宽度 check，约定见 mechanics.md「散文注释折行约定」节）。卡片顺序：base 的 markdown 变体卡在最前，然后常见语言、单工具类型简表，最后纯 lint/配置类。

---

## markdown 变体：CJK 表格对齐链

**命中条件**：文档/注释以 CJK 为主、表格要按显示宽度对齐（MD060 的 aligned 判定就是显示宽度，CJK=2）。与 base 的 `prettier-md` 互斥——prettier 按字符宽补白，同一张 CJK 表被两边来回补白、永远跑不净（原理见 mechanics.md「实战里攒下来的坑」末条）。

**资产**：`scripts/md_table_align.py`（显示宽度重排器，幂等原位改写）；可选 `scripts/docs_linkcheck.py`（docs/ 相对死链全量扫）。
**接线**——换掉 base 的 `prettier-md` 钩（保留它前面的 markdownlint --fix），md 面依次：

```yaml
- id: md-table-align
  name: md table display-width realign
  entry: python3 scripts/md_table_align.py
  language: system
  types: [markdown]
- id: docs-linkcheck
  name: docs/ markdown dead-link check
  entry: python3 scripts/docs_linkcheck.py
  language: system
  files: '^docs/.*\.md$'
  pass_filenames: false
- id: autocorrect-md
  name: autocorrect (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "autocorrect --stdin"
  language: system
  types: [markdown]
```

`docs-linkcheck` 只在仓有 `docs/` 类文档树时挂；`pass_filenames: false` 全量扫是刻意——删/改名目标件不触发文件钩，盲区由 CI 同名 step 兜底。

有 python 配方时再补一格（CI `ruff format --check .` 连 md 内 python 栅栏一起查；gfs stdin 拿不到文件名识别不了栅栏，只能文件名模式原位改写——同 fail 一次 re-add 语义）：

```yaml
- id: ruff-format-md
  name: ruff format (md python fences)
  entry: ruff format
  language: system
  types: [markdown]
```

**配套三处**：

- `package.json`：`format`/`format:check` 的 glob 去掉 `**/*.md`（md 面不再有 prettier；其余类型 glob 照 python 配方等的需要扩）
- `.vscode/settings.json` `[markdown]`：删 `defaultFormatter`、`formatOnSave: false`，只留 `codeActionsOnSave` 的 `source.fixAll.markdownlint`
- `.markdownlint.jsonc`：MD060 不用显式配——新版 markdownlint 默认开、默认风格即按显示宽度判

**CI**：format job 里 `lint:md` 之后补 `python3 scripts/md_table_align.py $(git ls-files '*.md')` 的 check 步（已对齐的表零 diff 即过），挂了 linkcheck 的仓加同名 step。

**验证**：`python3 scripts/md_table_align.py $(git ls-files '*.md')` 全 clean + `npm run lint:md`。
**注意**：md_table_align 是原地 fixer——改写了 fail 一次、re-add 再交，与 markdownlint --fix 同语义；钩序保持在 markdownlint --fix 之后、autocorrect 之前。

---

## shell (bash)

**命中条件**：存在 `*.sh`。bash shebang 的文件走完整链；zsh 脚本原样透传（两个工具都不认 zsh——别去改 shebang）。

**安装**：`brew install shfmt shellcheck`
**资产**：`scripts/fmt-shell.sh`（chmod +x）——按 shebang 嗅探的 gfs formatter
**Hooks**：

```yaml
- id: shfmt
  name: shfmt (staged content; zsh passthrough)
  entry: ./node_modules/.bin/git-format-staged --formatter "bash scripts/fmt-shell.sh"
  language: system
  types: [shell]
- id: shellcheck
  name: shellcheck (bash only; zsh skipped)
  entry: bash -c 'for f in "$@"; do head -1 "$f" | grep -q "zsh" || shellcheck -S warning "$f"; done' --
  language: system
  types: [shell]
```

**CI**（新 job）：

```yaml
shell:
    name: Shell
    runs-on: ubuntu-latest
    steps:
        - uses: actions/checkout@v4
        - run: brew install shfmt shellcheck
        - run: |
              for f in $(git ls-files '*.sh'); do
                head -1 "$f" | grep -q "zsh" || shfmt -d -i 2 "$f"
                head -1 "$f" | grep -q "zsh" || shellcheck -S warning "$f"
              done
```

**验证**：`for f in $(git ls-files '*.sh'); do head -1 "$f" | grep -q zsh || shellcheck -S warning "$f"; done`
**注意**：`types: [shell]` 按扩展名匹配，zsh 也会到达 hook——必须在命令内部跳过，绝不维护 `exclude:` 文件名清单。CI 里 brew 装的工具版本随 brew 浮动；要钉版（版本间告警集不同咬过人，如 shellcheck 0.9 vs 0.11）走官方 release curl + sha256 核验：

```yaml
- run: |
      curl -fsSL -o "$HOME/.local/bin/shfmt" \
        "https://github.com/mvdan/sh/releases/download/v3.14.1/shfmt_v3.14.1_linux_amd64"
      echo "<sha256>  $HOME/.local/bin/shfmt" | sha256sum -c -
      chmod +x "$HOME/.local/bin/shfmt"
```

---

## python

**命中条件**：存在 `*.py`。
**安装**：`brew install ruff`
**Hooks**：

```yaml
- id: ruff-format
  name: ruff format (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "ruff format -"
  language: system
  types: [python]
- id: ruff-check
  name: ruff check
  entry: ruff check
  language: system
  types: [python]
```

**配置**（必须落地，否则 `ruff check` 形同虚设）`ruff.toml`：

```toml
# 无配置时 `ruff check` 只跑 F+E4/E7/E9(pyflakes 级)——hook 在跑，
# 但几乎什么都查不出来。select=ALL 全开，ignore 只放必选项和
# 对本仓库性质为真的豁免，逐条注明，不 hand-pick 白名单。
target-version = "py39"   # 部署目标最低 python3，防 UP 推荐过新语法

[lint]
select = ["ALL"]
ignore = [
  "COM812", "ISC001",   # 官方列名与 ruff format 冲突，必关
  # 常见豁免按仓库实情调:D(docstring)、ANN(类型标注)、T201(CLI print)、
  # RUF001-003(CJK 注释 unicode 歧义)、CPY001、PTH、PLR2004 等
]
```

**CI**（独立 job 或并进步骤）：

```yaml
- run: brew install ruff
- run: ruff format --check . && ruff check .
```

**验证**：`ruff check . && ruff format --check .`
**Gitignore**：`__pycache__/`、`.ruff_cache/`
**注意**：ruff 一个工具覆盖 format + lint + import 排序。`ruff format` 裸跑就是全功能；`ruff check` 必须吃上上面的 `ruff.toml`——mihomo-macos 的 check hook 曾因此空转数周。策略是 `select=["ALL"]` 全开 + 逐条注明豁免，不 hand-pick 规则白名单。类型检查（pyright/ty/mypy）是全项目级——进 CI 不进 hook。

---

## go

**命中条件**：存在 `*.go`。
**安装**：`brew install go golangci-lint`（更严的格式化可换 `gofumpt`——只换 formatter 命令即可）
**Hooks**：

```yaml
- id: gofmt
  name: gofmt (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "gofmt"
  language: system
  types: [go]
```

**CI**：

```yaml
golangci:
    name: golangci-lint
    runs-on: ubuntu-latest
    steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-go@v5
        - uses: golangci/golangci-lint-action@v9
          with:
              version: v2.13.2 # 与本地 brew 版对齐
```

**验证**：`gofmt -l .`（应为空）+ `golangci-lint run`
**注意**：golangci-lint 是全包级——进 CI 不进 per-file hook。提交 `.golangci.yml`（devin-2api 的做法：`default: none` + 显式开 bodyclose/errcheck/govet/revive/staticcheck/unused）。`golangci-lint fmt` 也可当手动 fixer，覆盖 gofmt+goimports。

---

## rust

**命中条件**：存在 `*.rs`。
**安装**：`brew install rustfmt`（或 rustup component）
**Hooks**：

```yaml
- id: rustfmt
  name: rustfmt (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "rustfmt --edition 2021"
  language: system
  types: [rust]
```

**CI**：

```yaml
- run: cargo fmt --check && cargo clippy -- -D warnings && cargo test
```

**验证**：`cargo fmt --check` + `cargo clippy -- -D warnings`
**Gitignore**：`/target/`
**注意**：rustfmt 管道时 stdin→stdout，天然 gfs。clippy 全 crate 级——只进 CI。

---

## typescript / javascript

三个真实选项——选型见 [decisions.md](decisions.md)，默认 **prettier + eslint + tsc**。

**安装**：base 的 prettier 已在；`npm i -D eslint typescript typescript-eslint`（+ 项目需要的插件），或 `brew install biome` / `npm i -D oxlint oxfmt`
**Hooks**（prettier+eslint 默认）：

```yaml
- id: prettier-js
  name: prettier (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "./node_modules/.bin/prettier --stdin-filepath {}"
  language: system
  files: '\.(jsx?|tsx?|mjs|cjs|json|css|html|graphql|vue)$'
- id: eslint
  name: eslint
  entry: ./node_modules/.bin/eslint --max-warnings 0 --no-warn-ignored
  language: system
  files: '\.(jsx?|tsx?|mjs|cjs)$'
```

变体——biome（一个二进制顶替 prettier+eslint，覆盖 js/ts/json/css）：

```yaml
- id: biome
  name: biome check --write (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "biome check --write --stdin-file-path {}"
  language: system
  files: '\.(jsx?|tsx?|mjs|cjs|json|css)$'
```

变体——oxfmt + oxlint：

```yaml
- id: oxfmt
  name: oxfmt (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "oxfmt --stdin-filepath {}"
  language: system
  files: '\.(jsx?|tsx?|mjs|cjs|json)$'
- id: oxlint
  name: oxlint
  entry: ./node_modules/.bin/oxlint --deny-warnings
  language: system
  files: '\.(jsx?|tsx?|mjs|cjs)$'
```

**CI**：

```yaml
- run: npm ci && npx tsc --noEmit
```

**验证**：`npx prettier --check .` + `npx eslint .` + `npx tsc --noEmit`
**注意**：tsc 全项目级——进 CI。eslint 用 flat config（`eslint.config.js`）入库；`--no-warn-ignored` 必须带——flat config 下被 ignore 的文件显式喂给 eslint 会出 warning，撞上 `--max-warnings 0` 就挂。svelte/astro 需要各自的 prettier 插件。package.json 里 `format`/`format:check` 的 glob 要扩上 js/ts 扩展名（base 脚本只 glob md + yaml）。

---

## c / c++

**命中条件**：存在 `*.{c,cc,cpp,cxx,h,hh,hpp,hxx}`。
**安装**：`brew install clang-format`（clang-tidy 需 llvm）
**Hooks**：

```yaml
- id: clang-format
  name: clang-format (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "clang-format --assume-filename {}"
  language: system
  files: '\.(c|cc|cpp|cxx|h|hh|hpp|hxx)$'
```

**CI**：`clang-tidy` 需要 compile_commands——CI 或手动。
**验证**：`git ls-files '*.cpp' '*.h' | xargs clang-format --dry-run --Werror`
**注意**：提交 `.clang-format` 风格文件（否则回落到 LLVM 默认风格）。

---

## java

两条路——见 [decisions.md](decisions.md)：独立二进制进链，或 JVM 惯例的构建工具路线（spotless）。这里给独立二进制版。

**命中条件**：存在 `*.java`。
**安装**：下载 google-java-format jar（或活跃分支 palantir-java-format）
**Hooks**：

```yaml
- id: gjf
  name: google-java-format (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "java -jar tools/google-java-format.jar -"
  language: system
  types: [java]
```

**CI**：仓库已用 spotless 就跑 `./gradlew spotlessCheck` 或 `mvn spotless:check`——那种情况完全不加 format hook。
**验证**：同 CI。
**注意**：绝不把 gradle/maven 挂进 pre-commit（每次 commit 数秒 JVM 启动）；JVM 的格式化属于构建工具，由 CI 把门。

---

## kotlin

**命中条件**：存在 `*.{kt,kts}`。
**安装**：`brew install ktlint`（备选 ktfmt）
**Hooks**：

```yaml
- id: ktlint
  name: ktlint format (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "ktlint -F --stdin"
  language: system
  files: '\.kts?$'
```

**CI**：`detekt` 进 CI；gradle 项目走 spotless（规则同 java）。
**验证**：`ktlint`（不带 -F）跑这些文件。

---

## csharp

**命中条件**：存在 `*.cs`。
**安装**：`dotnet tool install -g csharpier`
**Hooks**：

```yaml
- id: csharpier
  name: csharpier (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "csharpier format --stdin-path {}"
  language: system
  files: '\.cs$'
```

**CI**：`dotnet csharpier check .`
**验证**：`csharpier check .`
**注意**：`dotnet format` 是更慢的内置替代——只进 CI。

---

## ruby

**命中条件**：存在 `*.rb`。
**安装**：`gem install rubocop`（或 `standard` 零配置预设）
**Hooks**：

```yaml
- id: rubocop
  name: rubocop -A (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "rubocop --stdin {} -A --stderr"
  language: system
  types: [ruby]
```

**验证**：`rubocop` 全仓。

---

## php

**命中条件**：存在 `*.php`。
**安装**：php-cs-fixer（phar/composer）
**Hooks**——php-cs-fixer 的 stdin 模式吐的是 diff 而不是修复后源码，只能当原地 fixer：

```yaml
- id: php-cs-fixer
  name: php-cs-fixer (in-place; fails once then re-add)
  entry: php-cs-fixer fix --quiet
  language: system
  types: [php]
```

**注意**：如果仓库本来就用 prettier 且 PHP 是少数派语言，`@prettier/plugin-php` 可以省掉第二个 formatter。

---

## dart

**命中条件**：存在 `*.dart`。
**安装**：flutter/dart SDK
**Hooks**——`dart format` 只认文件参数（没有 stdin flag），原地 fixer：

```yaml
- id: dart-format
  name: dart format (in-place)
  entry: dart format
  language: system
  types: [dart]
```

**CI**：`dart format -o none --set-exit-if-changed` + `flutter analyze`
**验证**：同 CI。

---

## swift

**命中条件**：存在 `*.swift`。
**安装**：`brew install swift-format`（lint 也可另上 swiftlint）
**Hooks**：

```yaml
- id: swift-format
  name: swift-format (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "swift-format --assume-filename {}"
  language: system
  types: [swift]
- id: swift-lint
  name: swift-format lint
  entry: bash -c 'for f in "$@"; do swift-format lint "$f" || exit 1; done' --
  language: system
  types: [swift]
```

**验证**：`swift-format lint -r .`

---

## 单工具类型（只有 format hook）

每行一个 formatter，全部 gfs 原生（stdin→stdout）。`types` 标签不确定时用 `files:` 正则。

| 类型      | Formatter 命令                 | 安装                       | 文件匹配                                                  |
| --------- | ------------------------------ | -------------------------- | --------------------------------------------------------- |
| lua       | `stylua -`                     | brew install stylua        | `files: '\.lua$'`                                         |
| zig       | `zig fmt --stdin`              | brew install zig           | `files: '\.zig$'`                                         |
| elm       | `elm-format --stdin`           | npm i -g elm-format        | `files: '\.elm$'`                                         |
| gleam     | `gleam format`                 | brew install gleam         | `files: '\.gleam$'`                                       |
| elixir    | `mix format -`                 | elixir                     | `files: '\.exs?$'`                                        |
| haskell   | `ormolu --stdin-input-file {}` | brew install ormolu        | `files: '\.hs$'`                                          |
| ocaml     | `ocamlformat --name={} -`      | opam install ocamlformat   | `files: '\.mli?$'`                                        |
| nix       | `nixfmt`                       | brew install nixfmt        | `files: '\.nix$'`                                         |
| terraform | `terraform fmt -`              | brew install terraform     | `types: [terraform]`                                      |
| proto     | `buf format -`                 | brew install buf           | `files: '\.proto$'`                                       |
| toml      | `taplo fmt -`                  | brew install taplo         | `types: [toml]`                                           |
| bazel     | `buildifier`                   | brew install buildifier    | `files: '(\.bzl\|BUILD(\.bazel)?\|WORKSPACE(\.bazel)?)$'` |
| sql       | `sqlfmt -`                     | pipx install shandy-sqlfmt | `files: '\.sql$'`                                         |

每行的 hook 模板：

```yaml
- id: <tool>
  name: <tool> (staged content)
  entry: ./node_modules/.bin/git-format-staged --formatter "<formatter command>"
  language: system
  # ↓ 把该行"文件匹配"列粘到这里，例如  files: '\.lua$'
```

需要配套 linter 时：deadnix/statix（nix）、buf lint（proto）、sqlfluff（sql，要选定 dialect）、luacheck（lua）——全部是 check-only 文件参数型。

---

## 纯 lint / 配置类

| 类型           | 工具                                    | 接法                                                                                           |
| -------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| github actions | `actionlint`                            | `files: '\.github/workflows/.*\.(yml\|yaml)$'` check hook——顺手 lint 这套工具链自己产的 ci.yml |
| dockerfile     | `hadolint`                              | `files: '(^\|/)Dockerfile'` check hook                                                         |
| k8s yaml       | `kubeconform`                           | CI（schema 校验需要集群 schema）                                                               |
| powershell     | PSScriptAnalyzer                        | 只在有 pwsh 的机器上做 check hook；一般不进链                                                  |
| xml/plist      | `@prettier/plugin-xml` / `plutil -lint` | plist 在 macOS 上只做 check                                                                    |
| jupyter        | `nbQA` 或 jupytext                      | 优先 jupytext 配对，让 python 配方直接生效                                                     |
| solidity       | `forge fmt`                             | 文件级格式化 + `--check` 进 CI                                                                 |

其余类型：按 [mechanics.md](mechanics.md) 的扩展规则——stdin→stdout formatter → gfs；只认文件 → 原地 fixer；纯 lint → check hook；全项目级 → CI。

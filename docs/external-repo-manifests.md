# External Repo Manifests

`external-repos.json` 是给安装流程用的机器元数据，不是运行时配置文件。

## 作用边界

- `scripts/install_skill.py` 会读取它，检查或 clone wrapper 所依赖的外部仓
- wrapper 自身的运行时 resolver 仍然只负责“检测并报错”，不会隐式 clone 或修改本机状态
- 本机私有路径仍然通过 `AGENT_BASIC_SKILL_SOURCE_OVERRIDES` 指向的 override 文件承接，不回写到共享仓

## Schema

```json
{
  "version": 1,
  "repositories": [
    {
      "id": "repo:WncFht/PulseDeck",
      "repo": "WncFht/PulseDeck",
      "clone_url": "https://github.com/WncFht/PulseDeck.git",
      "default_clone_dir": "~/Desktop/src/PulseDeck",
      "default_detect_paths": [
        "~/Desktop/src/PulseDeck",
        "~/Desktop/src/pulsedeck"
      ],
      "env_var": "BILIBILI_UP_DIGEST_REPO",
      "override_key": "repo:WncFht/PulseDeck",
      "markers": [
        "scripts/build_daily_digest.py"
      ],
      "bootstrap_hint": "uv sync"
    }
  ]
}
```

## 字段约定

- `id`: 当前依赖条目的稳定标识
- `repo`: 逻辑仓库身份，用于给人看和报错
- `clone_url`: 自动 clone 时使用的 URL
- `default_clone_dir`: 默认 clone 目标目录
- `default_detect_paths`: 自动检测现有仓时依次尝试的候选路径
- `env_var`: 运行时和安装时共用的环境变量入口
- `override_key`: source override 文件里使用的 key
- `markers`: 认定该目录为合法外部仓所必需存在的相对路径
- `bootstrap_hint`: 可选提示，告诉用户 clone 后通常还需要做什么

## 安装器约定

- 检测顺序固定为 `env var -> local override -> default_detect_paths -> default_clone_dir`
- 如果 `default_clone_dir` 已存在但不满足 `markers`，安装器必须失败，不得覆盖
- 如果依赖仓已经存在且满足 `markers`，安装器只记录 `already_present`
- 如果依赖仓缺失，安装器才会 clone

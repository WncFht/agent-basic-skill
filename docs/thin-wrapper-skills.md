# Thin Wrapper Skills

`external-tool-wrapper` 类型的 skill 只负责“入口层”和“薄桥接层”，不再承载完整应用。

## 允许出现的内容

wrapper skill 可以包含：

- `SKILL.md`
- 少量桥接脚本，例如定位外部工具仓的 `scripts/*.py`
- 少量 metadata、`references/`、必要的小型静态资源

## 不允许出现的内容

以下内容不应再出现在 wrapper skill 中：

- 大型运行时代码树
- `tests/`
- `src/`
- 缓存目录
- SQLite 数据库
- 浏览器 profile
- 认证状态
- 与外部工具仓等价的完整文档树

## 路径发现顺序

wrapper skill 统一遵循以下顺序来定位外部工具仓：

1. 显式参数
2. 环境变量
3. 本地 `source override`
4. 文档化默认候选路径
5. 如果仍未找到，则明确报错并告诉用户如何准备对应工具仓

## 运行时边界

wrapper 只安装轻量文件到 `~/.codex/skills/<skill-name>`。

以下内容必须继续留在当前 skill 目录之外：

- 工具仓代码
- cache / auth / runtime state
- 用户自己的 workspace
- Obsidian vault、research notes、下载目录等业务数据

## 当前仓库内的 wrapper

- `bilinote-video-note` -> `WncFht/BiliNote`
- `paperflow-pipeline-notes` -> `WncFht/paperflow`
- `shuiyuan-cache-skill` -> `WncFht/shuiyuan_exporter`
- `bilibili-up-digest` -> `WncFht/PulseDeck`
- `video-note-render-pdf` -> `WncFht/video-note-pipeline` + local `video_notes` workspace

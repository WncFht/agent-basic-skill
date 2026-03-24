# agent-basic-skill

`agent-basic-skill` 是一个独立仓库，用来承载一组可复用的 Codex 基础 skill。目标是把这些已经比较稳定的 skill 从单机 `~/.codex/skills/` 目录里拆出来，变成可以在新机器上安装、集中维护、持续更新的一套 bundle。

这个仓库是这批 skill 的长期源码来源。`~/.codex/skills/` 下的同名目录应当被视为安装结果、同步副本，或者临时开发镜像，而不是主维护仓库。

## 包含的 skill

| Skill | 作用 | 关键伴随文件 |
| --- | --- | --- |
| `pdf` | 处理 PDF 解析、生成和版式校验相关任务 | `agents/`、`assets/`、`LICENSE.txt` |
| `report-download` | 从官方来源优先下载 A 股和港股财报 | `scripts/`、`pyproject.toml`、`uv.lock`、`agents/` |
| `git-commit` | 约束 Conventional Commits 风格的提交流程 | `SKILL.md` |
| `jupyter-notebook` | 创建和整理 Jupyter Notebook | `scripts/`、`assets/`、`references/`、`agents/`、`LICENSE.txt` |
| `frontend-slides` | 生成 HTML 幻灯片和 PPT 转网页流程 | `scripts/`、`README.md`、`MEMORY.md`、CSS/Markdown 参考文件 |

## 目录结构

```text
agent-basic-skill/
├── bundle-manifest.json
├── INSTALL.md
├── README.md
├── scripts/
│   └── install_bundle.py
├── skills/
│   ├── pdf/
│   ├── report-download/
│   ├── git-commit/
│   ├── jupyter-notebook/
│   └── frontend-slides/
└── tests/
    └── test_bundle.py
```

`bundle-manifest.json` 是仓库级索引文件，记录了 bundle 中有哪些 skill、它们在仓库内的路径，以及安装和更新过程中必须保留下来的伴随文件。

## 依赖说明

- `pdf`：最佳路径依赖 `MINERU_API_TOKEN`；做 PDF 可视化检查时还需要 Poppler 工具，例如 `pdftoppm`。
- `report-download`：推荐使用 `uv` 和 Python 运行仓库里的下载脚本。
- `jupyter-notebook`：模板脚手架脚本本身只依赖 Python 标准库，但真正在本机运行 notebook 仍然需要正常的 Jupyter 环境。
- `frontend-slides`：PPT 转换路径依赖 `python-pptx`；同时它还依赖多个必须与 `SKILL.md` 同目录分发的 Markdown 和 CSS 文件。

## 安装与更新

具体命令见 [INSTALL.md](INSTALL.md)，其中包括：

- 从当前本地仓库安装到 `~/.codex/skills`
- 对已有安装执行整包刷新
- 将来发布到 GitHub 之后，如何复用 `skill-installer` 进行安装

## 验证

运行下面的命令可以验证仓库结构和安装脚本是否正常：

```bash
python -m unittest discover -s tests
```

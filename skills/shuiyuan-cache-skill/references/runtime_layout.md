# Runtime Layout

skill 仓库本身应尽量保持“只放代码与文档”，运行时数据默认放在独立目录中。

## 1. 默认根目录

默认 runtime 根目录：

```text
~/.local/share/shuiyuan-cache-skill/
```

默认派生路径：

```text
~/.local/share/shuiyuan-cache-skill/
  cache/
  exports/
  cookies.txt
```

## 2. 路径覆盖优先级

优先级从高到低：

1. CLI 参数，例如 `--cache-root`、`--cookie-path`、`--export-root`
2. 环境变量
3. 内置默认值

支持的环境变量：

- `SHUIYUAN_SKILL_HOME`
- `SHUIYUAN_CACHE_ROOT`
- `SHUIYUAN_COOKIE_PATH`
- `SHUIYUAN_EXPORT_ROOT`

## 3. 认证存储位置

主认证文件：

```text
~/.local/share/shuiyuan-cache-skill/cache/auth/auth.json
```

独立浏览器 profile：

```text
~/.local/share/shuiyuan-cache-skill/cache/auth/browser_profile/
```

回退 cookie 文件：

```text
~/.local/share/shuiyuan-cache-skill/cookies.txt
```

注意：`cookies.txt` 保存的是一整条 HTTP `Cookie` header 字符串，不是 Netscape cookie-jar 文件。

## 4. 缓存目录结构

默认 cache 根目录：

```text
~/.local/share/shuiyuan-cache-skill/cache/
```

完整示意：

```text
cache/
  auth/
    auth.json
    browser_profile/
  db/
    shuiyuan.sqlite
  media/
    images/
      <bucket>/
        <media_key>.<ext>
  raw/
    topics/
      <topic_id>/
        topic.json
        sync_state.json
        pages/
          json/
            0001.json
            0002.json
          raw/
            0001.md
            0002.md
    post_refs/
      <topic_id>/
        000001.raw.md
        000169.raw.md
```

## 5. 导出目录结构

默认导出根目录：

```text
~/.local/share/shuiyuan-cache-skill/exports/
```

正常结构：

```text
exports/
  <topic_id>/
    <topic_id> <title>.md
    images/
      <image-file>
```

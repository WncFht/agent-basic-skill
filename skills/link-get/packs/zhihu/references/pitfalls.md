# 已知坑与风控

## 反爬三层（排障时按层定位）

1. **zse-ck 挑战页**（WAF）：匿名/低信任请求 → 403 + 650B JS 挑战。真浏览器可过，curl 不行。
2. **x-zse-96 签名**（API）：内容接口要签名头。各工具实现：
    - zhihu-cli / meurz / we1005：`2.0_` 旧版（ZK/ZB 分组密码），实测仍被接受
    - zhihu-scraper：不签名，靠 curl_cffi TLS 指纹 + 浏览器回退解 `__zse_ck`
    - MediaCrawler：execjs 跑知乎官方 `libs/zhihu.js`
    - **若知乎强制 v3（SM4 变体）**：除 MediaCrawler 外集体失效。参考实现：RSSHub `lib/routes/zhihu/execlib/x-zse-96-v3.ts`（124 行自包含）、zhihu-plus-plus `rs-zse-sign`、本机 `/tmp/zhsign/sign.py`（已移植 Python 版，若 /tmp 清了可从 RSSHub 再移）
3. **z_c0 登录态**（硬门槛）：签名对但没 z_c0 → 403 `need_login`。cookie 之外还叠加 IP 信誉 + 设备指纹（x-udid）+ sec_token。

## 风控现象与对策

| 现象                                          | 含义         | 对策                                            |
| --------------------------------------------- | ------------ | ----------------------------------------------- |
| `40352` / 跳 `/account/unhuman`               | 人机验证挑战 | `zhihu auth captcha` 或浏览器手动过验证；换 IP  |
| `10003` 请求参数异常                          | 缺/错签名    | 工具侧问题，更新工具或报 issue                  |
| `401` `ERR_DECODE_SECURE_COOKIE` / need_login | cookie 失效  | 重跑 `auth-zhihu.sh`                            |
| `429`                                         | 限速         | 尊重 Retry-After；别调低 request_interval       |
| 匿名 ~50 请求后全端点 40352                   | IP 级风控    | 等解封（实测 8min+）；批量任务用低并发 + 代理池 |

## 各工具特有风险

- **zhihu-scraper**：`browser.fallback=auto` 且默认 `headless=false`——HTTP 被拒会**弹真 Chrome 窗口**。无头/SSH 环境设 `fallback = "never"` 或 `headless = true`（headless 过挑战成功率存疑）。媒体下载走独立链路不受请求间隔控制。**专栏短链 `zhuanlan.zhihu.com/<slug>` 不认**，必须给 `www.zhihu.com/column/<slug>` 形式。**专栏内 answer 项修复在 `patches/zhihu-scraper-column-answers.patch`**：原版专栏管线假定 items 全是 article，遇到专栏收录的 answer 项直接中断（`normalize_article` 崩 + `write_item` XOR 检查）；补丁让 answer 项走 `normalize_answer` 落盘且不中断，setup-zhihu.sh 每次 pull 后自动重打（`apply --check` → `apply --reverse --check` 识别已应用态），打不上会提示人工核对上游是否已修。
- **zhihu-cli**：PyPI `0.1.0` 有 bug，**必须装 git main**（`uv tool install git+https://...`）。`auth paste` 只认 cURL 格式（`-H 'k: v'`），光粘 `z_c0=xx` 不行——`auth-zhihu.sh` 的 `--cookie` 模式会代构造。多账号 `zhihu profile`；长任务起 `zhihu daemon start` 常驻连接提速。
- **MediaCrawler**：知乎 detail 走 HTML 页面而非 API，靠浏览器会话 cookie；NON-COMMERCIAL LEARNING LICENSE；execjs 需要 Node。`mcp-service/media-crawler-mcp-service` 的 MCP 封装**没实现知乎**，别装错。
- **Jina**：行内公式 `$Q$Q` 重复伪影；20 req/min；约 1/3 请求被上游拦要重试；本机必须走代理否则连不上。
- **tardis**：只覆盖已镜像子集，未镜像一律 302→`/tardis/error`（zhihu-tardis 退出码 3）——不是故障是覆盖边界，miss 是常态之一，命中当 bonus。

## 已确认死亡的路线（别再试）

- 公共 RSSHub 实例（CF 拦截/503）；自部署需 `ZHIHU_COOKIES` 环境变量才拿得到全文
- 全部匿名 API 封装老工具（schollz/zhihu 已删库，zhihu-oauth/egrcc 系死于签名）
- `zhuanlan.zhihu.com/api/columns`、`api.zhihu.com/column`、`news-at.zhihu.com` 日报 API 全下线
- `md.dhr.wtf` 等无浏览器的 URL→md 服务（过不了 zse-ck）

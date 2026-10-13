# Cookie 获取

所有 cookie 路线工具都要两个关键值：

- `z_c0`：登录态主键，过期后全部 401
- `d_c0`：设备凭证，x-zse-96 签名的输入之一，缺了签名接口全挂

## 方法一：Copy as cURL（推荐，`auth-zhihu.sh` 直通）

1. Chrome 登录 zhihu.com，开 DevTools → Network
2. 刷新页面，任选一个 `zhihu.com` 请求，右键 → Copy → Copy as cURL
3. `skills/link-get/scripts/auth-zhihu.sh` 粘贴整条命令回车

cURL 里自带完整 cookie + UA，比单抄 cookie 值可靠。

## 方法二：只抄 cookie 值

DevTools → Application → Cookies → `https://www.zhihu.com`，抄 `z_c0` 和 `d_c0`：

```bash
skills/link-get/scripts/auth-zhihu.sh --cookie 'z_c0=<值>; d_c0=<值>'
```

## 方法三：扫码 / CDP（不复制 cookie）

- `zhihu auth login`：zhihu-cli 自带扫码登录——扫完跑 `auth-zhihu.sh --from-cli` 把已登录 cookie 自动分发到各工具路径
- `zhihu-scraper login`：弹浏览器登录后自动存 cookie 到 settings 指定路径
- `zhihu-scraper login --cdp http://127.0.0.1:9222`：读已登录 Chrome 的 cookie（Chrome 需以 `--remote-debugging-port=9222` 启动）
- MediaCrawler：`--lt qrcode` 扫码，或 `ENABLE_CDP_MODE` 骑本机 Chrome

## 失效处理

cookie 一般活几个月。link-get `doctor.sh`（含 zhihu pack probe）报失效就重跑 `auth-zhihu.sh`；触发人机验证（`zh-zse-ck` 挑战、跳转 `/account/unhuman`）先跑 `zhihu auth captcha` 或浏览器手动过一次验证再重试。

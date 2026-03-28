# 常见故障模式

把这些签名当作启发式线索，不要当成绝对真理。下结论前，至少再用一个邻近模型做交叉验证。

## 接口形态问题

- `GET /v1/models -> 404`
  含义：relay 仍可能可用；很多 responses-only relay 根本不实现这个路由。
  处理：继续做生成探测。

- `GET /v1/models -> 500`，并伴随 `missing field data` 之类错误
  含义：relay 或包装层返回了非标准 models payload。
  处理：继续做生成探测，把 models 列表视为损坏即可。

- `POST /v1/chat/completions -> 404`，而 `POST /v1/responses -> 200`
  含义：这是 codex / responses-only relay。
  处理：如果生成稳定，就按 `provider_type=codex` 接入 CCH。

- `POST /v1/responses -> 404`，而 `POST /v1/chat/completions -> 200`
  含义：这是 chat-only 的 OpenAI 兼容 relay。
  处理：按 `provider_type=openai-compatible` 接入。

## 鉴权与额度

- `401 token_revoked`
  含义：key 无效，或上游用户 token 已被吊销。
  处理：不要接入。

- `403 Authentication failed ... 未查询到模型信息`
  含义：鉴权至少部分通过了，但租户侧没有可用模型路由。
  处理：不要接入。

- `403` 或返回 Cloudflare HTML 错误页，例如 `error code: 1010`
  含义：出口链路或客户端栈在到达模型后端之前就被挡住了。
  处理：开启本机代理重试，并优先用基于 `curl` 的探测，而不是默认 Python HTTP 栈。

- `429 throttling` 或 `hour allocated quota exceeded`
  含义：当前被限流或额度耗尽。
  处理：即使接口形态正常，也不要把它标为健康。

## 模型选择问题

- `503 model_not_found`
  含义：该 relay 或通道组里没有这个模型。
  处理：先试同家族其他模型，再决定是否否掉整个 relay。

- `400` 且错误片段类似 `参数 '.3' 不存在`、`参数 'mini' 不存在`、`参数 'nano' 不存在`
  含义：上游对这个具体模型名的解析有问题。
  处理：把这个模型标成不可用，继续测邻近名称。

## 超时

- `curl: (28) ... with 0 bytes received`
  含义：模型可能不支持、卡死，或者极慢。
  处理：用更长超时重试一次；如果依旧 0 bytes，就把它排除出可用列表。

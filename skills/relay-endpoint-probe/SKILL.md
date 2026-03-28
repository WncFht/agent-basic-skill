---
name: relay-endpoint-probe
description: Probe user-provided or user-authorized LLM relay or gateway endpoints, classify whether they actually support OpenAI chat, OpenAI responses/Codex, or Anthropic messages, and optionally wire confirmed working relays into the local CCH/check-cx stack. Use when the user gives a base URL plus an authorized credential and asks to test it, list working models, explain relay failures, or add the relay locally.
---

# Relay 接口探测

直接使用 API 探测。**在 relay 本身没有验证通过之前，不要先跑远端接入脚本或配置同步。**

## 快速开始

1. 在这台机器上做公网探测前，先导出代理环境变量：

```bash
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export all_proxy=http://127.0.0.1:7897
```

2. 用用户直接提供或明确授权的 base URL 与凭据运行探测脚本：

```bash
export RELAY_API_KEY='sk-...'

python scripts/probe_relay.py \
  --base-url https://example.com/codex \
  --api-key-env RELAY_API_KEY
```

3. 读取 JSON 结果：

- `models_endpoint`：说明 `/v1/models` 是否可用、返回格式是否标准
- `chat_completions`、`responses`、`anthropic_messages`：说明哪些模型真的返回了有效响应
- `classification.recommended_cch_provider_types`：说明如果这个 relay 可用，应该按什么类型加入本机 CCH

4. 只有在至少一个真实生成请求成功后，才把 relay 加入 CCH 或 check-cx。

## 凭据边界

这个 skill 只能用于测试：

- 用户直接给出的凭据
- 用户明确授权你使用的凭据

不要拿公开帖子里抓到的、复制来的或第三方的 secret 来做测试。

## 探测顺序

1. 规范化入口：
   - OpenAI 兼容入口应以 `/v1` 结尾
   - Anthropic 兼容入口应是去掉 `/v1` 的根路径
2. 先探 `GET /v1/models`，但单独看到 `404`、`500` 或非标准返回体，不足以直接判死刑
3. 再探 `POST /v1/chat/completions`，使用小 prompt 和候选模型列表
4. 再探 `POST /v1/responses`
5. 如果可能支持 Anthropic / Claude Code，再探 `POST /v1/messages`
6. 对于 `0 bytes received` 这种超时，至少用更长超时重试一次，再决定是否判定不可用

## 结果解释

- `responses` 成功，而 `chat/completions` 是 `404`
  说明这是 `codex` / responses-only relay。加入 CCH 时用 `provider_type=codex`。

- `chat/completions` 成功，而 `responses` 是 `404`
  说明这是 `openai-compatible` relay。

- 根路径上的 `messages` 成功
  说明它兼容 Anthropic，可用于 Claude Code。

- `models` 失败，但生成请求成功
  说明 relay 仍可用。记录这个异常，但不要因为 models 列表坏掉就阻止接入。

- 出现 `model_not_found`、`No available channel` 之类错误
  先换几个同家族模型名再下结论。单个模型失败不等于整个 relay 失效。

- 出现 `token_revoked`、无效 OAuth token 或持续鉴权失败
  不要接入。

- 出现 `throttling`、`hour allocated quota exceeded` 之类额度错误
  说明 key 当前不可用，不要标记为健康。

- 出现 `403` 且提示 `未查询到模型信息`
  通常说明网关缺少租户 / 模型路由，不要接入。

- 出现 `400` 且错误只命中模型名的一部分，例如 `参数 '.3' 不存在`
  说明该模型名被上游错误解析。把这个模型标记为不可用，但不要立刻否决整个 relay。

## 本地集成

如果用户要求把已验证通过的 relay 加到本机环境中，读取 `references/local-integration.md`。

## 故障模式

如果 relay 有响应但行为异常，读取 `references/failure-patterns.md`。

## 资源

- `scripts/probe_relay.py`
  统一探测 `/v1/models`、`/v1/chat/completions`、`/v1/responses` 和 `/v1/messages`
- `references/local-integration.md`
  把验证通过的 relay 接到本机 CCH / check-cx 的规则和命令
- `references/failure-patterns.md`
  常见故障签名及其解释

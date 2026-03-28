# 本地集成

这个 skill 经常和这台机器上的本地 CCH 与 check-cx 一起使用。

## 本机默认值

- CCH API：`http://127.0.0.1:23000`
- CCH 管理员 token 文件：`/home/fanghaotian/Applications/claude-code-hub/.env`
- check-cx 仓库：`/home/fanghaotian/Desktop/src/check-cx`

## 接入规则

- 只有在真实生成请求成功之后才允许接入
- 如果只有 `/v1/responses` 可用，就用 `provider_type=codex`
- 如果只有 `/v1/chat/completions` 可用，就用 `provider_type=openai-compatible`
- `allowed_models` 只保留你实际验证过的模型
- 如果 relay 当前处于 revoked-token、额度耗尽、或模型路由缺失状态，不要接入

## CCH 工作流

通过本地 actions API 新建 provider：

```bash
curl -sS -X POST 'http://127.0.0.1:23000/api/actions/providers/addProvider' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "name": "RelayName",
    "url": "https://relay.example.com/codex",
    "key": "sk-xxx",
    "provider_type": "codex",
    "is_enabled": true,
    "weight": 1,
    "priority": 1,
    "allowed_models": ["gpt-5.4", "gpt-5.4-mini"]
  }'
```

更新已有 provider：

```bash
curl -sS -X POST 'http://127.0.0.1:23000/api/actions/providers/editProvider' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "providerId": 16,
    "allowed_models": ["gpt-5.4", "gpt-5.4-mini"]
  }'
```

## check-cx 工作流

更新完 CCH 之后，从 CCH provider 集合同步到 check-cx：

```bash
cd /home/fanghaotian/Desktop/src/check-cx
pnpm ctl providers sync-cch --group cch
pnpm ctl providers refresh --group cch
```

重要映射关系：

- CCH 的 `provider_type=codex` 会变成 check-cx 里的 `openai` 检查，并打到 `.../v1/responses`
- CCH 的 `provider_type=openai-compatible` 会变成 check-cx 里的 `openai` 检查，并打到 `.../v1/chat/completions`
- check-cx 会从 `allowed_models` 中选健康检查模型，所以模型顺序必须和你验证结果一致

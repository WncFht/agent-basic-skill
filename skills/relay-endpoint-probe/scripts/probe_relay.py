#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse


DEFAULT_CHAT_MODELS = [
    "gpt-5.4",
    "gpt-5",
    "qwen3-coder-plus",
    "qwen3-coder-next",
    "qwen-plus",
    "claude-sonnet-4-5-20250929",
    "claude-3-5-sonnet-latest",
]

DEFAULT_RESPONSES_MODELS = [
    "gpt-5.4",
    "gpt-5",
    "gpt-5-codex",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
    "gpt-5.2",
    "gpt-5.3-codex",
    "gpt-5.4-mini",
]

DEFAULT_ANTHROPIC_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-3-5-sonnet-latest",
    "qwen3-coder-plus",
]

TEST_PROMPT = "Reply with ok only."


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def ensure_openai_base(raw: str) -> str:
    base = raw.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def ensure_anthropic_base(raw: str) -> str:
    base = raw.rstrip("/")
    if base.endswith("/v1"):
        return base[:-3]
    return base


def parse_models_payload(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {"models": [], "parse_error": str(exc)}

    models: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        for item in payload["data"]:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
    elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
        for item in payload["models"]:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
    else:
        return {"models": [], "parse_error": "unexpected JSON shape"}

    return {"models": unique(models), "parse_error": None}


def extract_text(body: str) -> str | None:
    sse_match = re.search(r'"text":"([^"]*)","type":"response\.output_text\.done"', body)
    if sse_match:
        return sse_match.group(1)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]

        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]

        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                item_content = item.get("content")
                if isinstance(item_content, list):
                    for part in item_content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            return part["text"]

    return None


def classify_support(
    chat_results: list[dict[str, Any]],
    responses_results: list[dict[str, Any]],
    anthropic_results: list[dict[str, Any]],
) -> dict[str, Any]:
    supports_chat = any(item.get("success") for item in chat_results)
    supports_responses = any(item.get("success") for item in responses_results)
    supports_anthropic = any(item.get("success") for item in anthropic_results)

    provider_types: list[str] = []
    if supports_chat:
        provider_types.append("openai-compatible")
    if supports_responses:
        provider_types.append("codex")

    return {
        "supports_openai_chat": supports_chat,
        "supports_openai_responses": supports_responses,
        "supports_anthropic_messages": supports_anthropic,
        "recommended_cch_provider_types": provider_types,
        "suitable_for_claude_code": supports_anthropic,
    }


def body_excerpt(body: str, limit: int = 240) -> str:
    compact = body.replace("\r", "").strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def http_call(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    if shutil.which("curl") is None:
        return {
            "status": None,
            "elapsed_s": 0.0,
            "body": "",
            "error_type": "missing_dependency",
            "error_message": "curl not found in PATH",
        }

    command = [
        "curl",
        "-sS",
        "-N",
        "--max-time",
        str(timeout),
        "-o",
        "-",
        "-w",
        "\n__CURL_STATUS__:%{http_code}\n__CURL_ERRMSG__:%{errormsg}\n__CURL_TIME__:%{time_total}\n",
        url,
    ]
    for key, value in headers.items():
        command.extend(["-H", f"{key}: {value}"])
    if payload is not None:
        command.extend(["--data", json.dumps(payload, ensure_ascii=False)])

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout = result.stdout or ""
    stderr = result.stderr.strip()

    status_match = re.search(r"__CURL_STATUS__:(\d+)", stdout)
    time_match = re.search(r"__CURL_TIME__:([0-9.]+)", stdout)
    err_match = re.search(r"__CURL_ERRMSG__:(.*)", stdout)
    body = stdout.split("\n__CURL_STATUS__:", 1)[0].strip()
    status = int(status_match.group(1)) if status_match else None
    elapsed_s = (
        round(float(time_match.group(1)), 3)
        if time_match
        else round(time.monotonic() - started, 3)
    )
    curl_err = err_match.group(1).strip() if err_match else ""

    error_type = None
    error_message = None
    if result.returncode != 0 and (status is None or status == 0):
        error_type = "curl_error"
        error_message = stderr or curl_err or f"curl exit code {result.returncode}"
    elif isinstance(status, int) and status >= 400:
        error_type = "http_error"
        error_message = stderr or curl_err or f"HTTP {status}"

    return {
        "status": status,
        "elapsed_s": elapsed_s,
        "body": body,
        "error_type": error_type,
        "error_message": error_message,
    }


def summarize_probe(result: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    text = extract_text(result["body"])
    status = result["status"]
    success = isinstance(status, int) and 200 <= status < 300 and bool(text or result["body"])
    summary = {
        "model": model,
        "status": status,
        "success": success,
        "elapsed_s": result["elapsed_s"],
        "text": text,
        "error_type": result["error_type"],
        "error_message": result["error_message"],
        "body_excerpt": body_excerpt(result["body"]),
    }
    return summary


def probe_models_endpoint(openai_base: str, api_key: str, timeout: float) -> dict[str, Any]:
    raw = http_call(
        f"{openai_base}/models",
        {"Authorization": f"Bearer {api_key}"},
        None,
        timeout,
    )
    parsed = parse_models_payload(raw["body"]) if raw["body"] else {"models": [], "parse_error": None}
    return {
        "status": raw["status"],
        "elapsed_s": raw["elapsed_s"],
        "models": parsed["models"],
        "parse_error": parsed["parse_error"],
        "error_type": raw["error_type"],
        "error_message": raw["error_message"],
        "body_excerpt": body_excerpt(raw["body"]),
    }


def probe_chat_models(openai_base: str, api_key: str, models: list[str], timeout: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model in models:
        raw = http_call(
            f"{openai_base}/chat/completions",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "max_tokens": 8,
            },
            timeout,
        )
        results.append(summarize_probe(raw, model))
    return results


def probe_responses_models(
    openai_base: str,
    api_key: str,
    models: list[str],
    timeout: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model in models:
        raw = http_call(
            f"{openai_base}/responses",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": TEST_PROMPT,
            },
            timeout,
        )
        results.append(summarize_probe(raw, model))
    return results


def probe_anthropic_models(
    anthropic_base: str,
    api_key: str,
    models: list[str],
    timeout: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model in models:
        raw = http_call(
            f"{anthropic_base}/v1/messages",
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
            },
            timeout,
        )
        results.append(summarize_probe(raw, model))
    return results


def parse_model_arg(raw: str | None, defaults: list[str], discovered: list[str], limit: int) -> list[str]:
    if raw:
        return unique([item for item in raw.split(",") if item.strip()])[:limit]
    return unique(discovered + defaults)[:limit]


def resolve_api_key(inline_key: str | None, env_name: str | None, env: dict[str, str] | None = None) -> tuple[str, str]:
    if inline_key:
        return inline_key, "inline"
    if not env_name:
        raise ValueError("Either --api-key or --api-key-env is required.")
    source_env = env if env is not None else os.environ
    value = source_env.get(env_name)
    if not value:
        raise ValueError(f"Environment variable is empty or missing: {env_name}")
    return value, f"env:{env_name}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe relay endpoint compatibility and working models.")
    credential_group = parser.add_mutually_exclusive_group(required=True)
    credential_group.add_argument("--api-key", help="Relay API key.")
    credential_group.add_argument("--api-key-env", help="Environment variable holding the relay API key.")
    parser.add_argument("--base-url", help="Primary relay base URL. Used to derive OpenAI and Anthropic bases.")
    parser.add_argument("--openai-base-url", help="Explicit OpenAI-compatible base URL.")
    parser.add_argument("--anthropic-base-url", help="Explicit Anthropic-compatible base URL.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds.")
    parser.add_argument("--max-models", type=int, default=12, help="Maximum models to probe per family.")
    parser.add_argument("--chat-models", help="Comma-separated model list for chat probes.")
    parser.add_argument("--responses-models", help="Comma-separated model list for responses probes.")
    parser.add_argument("--anthropic-models", help="Comma-separated model list for Anthropic probes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        api_key, credential_source = resolve_api_key(args.api_key, args.api_key_env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.base_url and not args.openai_base_url and not args.anthropic_base_url:
        print("Either --base-url or an explicit family base URL is required.", file=sys.stderr)
        return 2

    base_url = args.base_url or args.openai_base_url or args.anthropic_base_url
    assert base_url is not None

    openai_base = ensure_openai_base(args.openai_base_url or base_url)
    anthropic_base = ensure_anthropic_base(args.anthropic_base_url or base_url)

    models_endpoint = probe_models_endpoint(openai_base, api_key, args.timeout)
    discovered = models_endpoint["models"] if isinstance(models_endpoint["models"], list) else []
    chat_models = parse_model_arg(args.chat_models, DEFAULT_CHAT_MODELS, discovered, args.max_models)
    responses_models = parse_model_arg(
        args.responses_models,
        DEFAULT_RESPONSES_MODELS,
        discovered,
        args.max_models,
    )
    anthropic_models = parse_model_arg(
        args.anthropic_models,
        DEFAULT_ANTHROPIC_MODELS,
        discovered,
        args.max_models,
    )

    chat_results = probe_chat_models(openai_base, api_key, chat_models, args.timeout)
    responses_results = probe_responses_models(openai_base, api_key, responses_models, args.timeout)
    anthropic_results = probe_anthropic_models(
        anthropic_base,
        api_key,
        anthropic_models,
        args.timeout,
    )

    payload = {
        "input": {
            "openai_base_url": openai_base,
            "anthropic_base_url": anthropic_base,
            "host": urlparse(base_url).netloc,
            "timeout": args.timeout,
            "credential_source": credential_source,
        },
        "models_endpoint": models_endpoint,
        "chat_completions": chat_results,
        "responses": responses_results,
        "anthropic_messages": anthropic_results,
        "working_models": {
            "chat_completions": [item["model"] for item in chat_results if item["success"]],
            "responses": [item["model"] for item in responses_results if item["success"]],
            "anthropic_messages": [item["model"] for item in anthropic_results if item["success"]],
        },
        "classification": classify_support(chat_results, responses_results, anthropic_results),
    }

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

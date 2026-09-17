from __future__ import annotations

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .models import CompletionResult, GenerationSettings, ModelSpec
from .storage import RequestLedger


class InfrastructureError(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    pass


class ModelGateway(Protocol):
    def complete(
        self,
        model: ModelSpec,
        messages: list[dict[str, str]],
        settings: GenerationSettings,
        seed: int,
        response_schema: dict | None,
    ) -> CompletionResult: ...


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InfrastructureError(f"could not read environment file {path}") from error
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_api_key(env_path: Path = Path(".env")) -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or parse_env(env_path).get("OPENROUTER_API_KEY")
    if not key:
        raise InfrastructureError("OPENROUTER_API_KEY is not configured")
    return key

def _default_opener() -> Any:
    configured = os.environ.get("SSL_CERT_FILE")
    system_bundle = Path("/etc/ssl/cert.pem")
    cafile = configured if configured and Path(configured).exists() else str(system_bundle) if system_bundle.exists() else None
    context = ssl.create_default_context(cafile=cafile)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context)).open

def _json_object_messages(messages: list[dict[str, str]], response_schema: dict) -> list[dict[str, str]]:
    schema = response_schema.get("schema", response_schema)
    instruction = (
        "\n\nReturn exactly one JSON object matching this schema. Do not add Markdown fences or any other text:\n"
        + json.dumps(schema, sort_keys=True, ensure_ascii=False)
    )
    prepared = [dict(message) for message in messages]
    for message in prepared:
        if message.get("role") == "system":
            message["content"] += instruction
            return prepared
    return [{"role": "system", "content": instruction.strip()}, *prepared]




class OpenRouterGateway:
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        ledger: RequestLedger,
        *,
        api_key: str | None = None,
        env_path: Path = Path(".env"),
        provider_sort: str = "price",
        require_parameters: bool = True,
        max_prompt_price: float = 0.20,
        max_completion_price: float = 0.35,
        timeout: float = 120,
        opener: Any = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.ledger = ledger
        self.api_key = api_key or load_api_key(env_path)
        self.provider_sort = provider_sort
        self.require_parameters = require_parameters
        self.max_prompt_price = max_prompt_price
        self.max_completion_price = max_completion_price
        self.timeout = timeout
        self.opener = opener or _default_opener()
        self.sleep = sleep

    def complete(
        self,
        model: ModelSpec,
        messages: list[dict[str, str]],
        settings: GenerationSettings,
        seed: int,
        response_schema: dict | None,
    ) -> CompletionResult:
        if not self.ledger.budget_available():
            raise BudgetExhausted(f"daily request budget of ${self.ledger.daily_budget_usd:.2f} reached")
        prepared_messages = messages
        if response_schema is not None and model.response_format == "json_object":
            prepared_messages = _json_object_messages(messages, response_schema)
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": prepared_messages,
            "stream": False,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": settings.max_tokens,
            "provider": {
                "sort": self.provider_sort,
                "require_parameters": self.require_parameters,
                "max_price": {"prompt": self.max_prompt_price, "completion": self.max_completion_price},
            },
        }
        if model.supports_seed:
            payload["seed"] = seed
        if model.supports_reasoning:
            payload["reasoning"] = {"effort": settings.reasoning_effort, "exclude": True}
        if response_schema is not None:
            if model.response_format == "json_schema":
                payload["response_format"] = {"type": "json_schema", "json_schema": response_schema}
            else:
                payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(3):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    generation_id = response.headers.get("X-Generation-Id")
                recorded_parameters = {key: value for key, value in payload.items() if key != "messages"}
                return self._decode_response(raw, generation_id, model.id, seed, recorded_parameters)
            except urllib.error.HTTPError as error:
                if error.code == 402:
                    raise BudgetExhausted("OpenRouter account budget exhausted") from None
                if error.code == 429 or 500 <= error.code <= 599:
                    if attempt < 2:
                        retry_after = error.headers.get("Retry-After") if error.headers else None
                        try:
                            delay = min(30.0, max(0.0, float(retry_after))) if retry_after else float(2**attempt)
                        except ValueError:
                            delay = float(2**attempt)
                        self.sleep(delay)
                        continue
                    raise InfrastructureError(f"OpenRouter HTTP {error.code} after 3 attempts") from None
                if error.code in (400, 401, 403):
                    raise InfrastructureError(f"OpenRouter rejected the request with HTTP {error.code}") from None
                raise InfrastructureError(f"OpenRouter returned HTTP {error.code}") from None
            except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as error:
                if attempt < 2:
                    self.sleep(float(2**attempt))
                    continue
                raise InfrastructureError(f"OpenRouter transport failed after 3 attempts: {type(error).__name__}") from None
        raise InfrastructureError("OpenRouter request failed")

    def _decode_response(self, raw: str, generation_id: str | None, requested_model: str, seed: int, parameters: dict[str, Any]) -> CompletionResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise InfrastructureError("OpenRouter returned invalid JSON") from error
        usage = data.get("usage") if isinstance(data, dict) else None
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if cost is None:
            raise InfrastructureError("OpenRouter response omitted usage.cost")
        base_record = {
            "status": "charged",
            "requested_model": requested_model,
            "seed": seed,
            "cost": float(cost),
            "completion_id": data.get("id") if isinstance(data, dict) else None,
            "generation_id": generation_id,
            "parameters": parameters,
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", usage.get("reasoning_tokens", 0)) or 0),
        }
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("content")
            details = usage.get("completion_tokens_details") or {}
            result = CompletionResult(
                content=content,
                resolved_model=str(data["model"]),
                finish_reason=str(choice["finish_reason"]),
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                reasoning_tokens=int(details.get("reasoning_tokens", usage.get("reasoning_tokens", 0)) or 0),
                cost=float(cost),
                completion_id=str(data["id"]),
                generation_id=generation_id,
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            base_record["status"] = "charged_invalid_response"
            base_record["validation_error"] = f"{type(error).__name__}: {error}"
            base_record["response"] = data
            self.ledger.append(base_record)
            raise InfrastructureError("OpenRouter returned a structurally invalid charged response") from error
        self.ledger.append({
            **base_record,
            "resolved_model": result.resolved_model,
            "finish_reason": result.finish_reason,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "reasoning_tokens": result.reasoning_tokens,
        })
        return result

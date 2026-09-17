import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from puppeteergpt.models import GenerationSettings, ModelSpec
from puppeteergpt.openrouter import BudgetExhausted, InfrastructureError, OpenRouterGateway, load_api_key, parse_env
from puppeteergpt.prompts import PLANNER_SCHEMA
from puppeteergpt.storage import RequestLedger


class Response:
    def __init__(self, data, generation="generation-1"):
        self.data = json.dumps(data).encode()
        self.headers = {"X-Generation-Id": generation}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


class CapturingOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return self.response


class OpenRouterTests(unittest.TestCase):
    def response_data(self, content="ok", cost=0.001):
        return {"id": "completion-1", "model": "resolved/model", "choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 11, "completion_tokens": 7, "completion_tokens_details": {"reasoning_tokens": 3}, "cost": cost}}

    def test_env_parser_supports_export_and_quotes_and_process_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("A=bare\nexport B='single'\nC=\"double\"\nOPENROUTER_API_KEY=file-key\n")
            self.assertEqual({"A": "bare", "B": "single", "C": "double", "OPENROUTER_API_KEY": "file-key"}, parse_env(path))
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "process-key"}):
                self.assertEqual("process-key", load_api_key(path))

    def test_exact_request_parameters_and_complete_usage_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RequestLedger(Path(directory), 1)
            opener = CapturingOpener(Response(self.response_data()))
            gateway = OpenRouterGateway(ledger, api_key="private", opener=opener)
            settings = GenerationSettings(0.8, 1.0, 120, "low")
            result = gateway.complete(ModelSpec("exact/model", "Exact"), [{"role": "user", "content": "hi"}], settings, 123, PLANNER_SCHEMA)
            payload = json.loads(opener.requests[0][0].data)
            self.assertEqual("exact/model", payload["model"])
            self.assertEqual(123, payload["seed"])
            self.assertEqual({"effort": "low", "exclude": True}, payload["reasoning"])
            self.assertEqual({"sort": "price", "require_parameters": True, "max_price": {"prompt": 0.2, "completion": 0.35}}, payload["provider"])
            self.assertEqual(PLANNER_SCHEMA, payload["response_format"]["json_schema"])
            self.assertEqual(3, result.reasoning_tokens)
            self.assertEqual("generation-1", result.generation_id)
            record = json.loads(ledger.path.read_text().strip())
            self.assertEqual(0.001, record["cost"])
            self.assertNotIn("private", ledger.path.read_text())

    def test_json_object_fallback_omits_unsupported_parameters_and_injects_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = CapturingOpener(Response(self.response_data('{\"analysis\":\"a\",\"agent_name\":\"b\",\"agent_instructions\":\"c\"}')))
            gateway = OpenRouterGateway(RequestLedger(Path(directory), 1), api_key="private", opener=opener)
            model = ModelSpec(
                "json-object/model",
                "JSON object",
                supports_seed=False,
                supports_reasoning=False,
                response_format="json_object",
            )
            messages = [{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "Plan."}]
            gateway.complete(model, messages, GenerationSettings(0.8, 1.0, 120, "low"), 123, PLANNER_SCHEMA)
            payload = json.loads(opener.requests[0][0].data)
            self.assertNotIn("seed", payload)
            self.assertNotIn("reasoning", payload)
            self.assertEqual({"type": "json_object"}, payload["response_format"])
            self.assertIn('\"agent_instructions\"', payload["messages"][0]["content"])
            self.assertEqual(messages, [{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "Plan."}])

    def test_blank_content_is_returned_without_content_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = CapturingOpener(Response(self.response_data("")))
            result = OpenRouterGateway(RequestLedger(Path(directory), 1), api_key="x", opener=opener).complete(ModelSpec("m", "m"), [], GenerationSettings(0, 1, 1, "low"), 1, None)
            self.assertEqual("", result.content)
            self.assertEqual(1, len(opener.requests))

    def test_retryable_http_error_reuses_request_and_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            response = Response(self.response_data())
            def opener(request, timeout):
                calls.append(json.loads(request.data))
                if len(calls) < 3:
                    raise urllib.error.HTTPError("url", 500, "failure", {}, io.BytesIO())
                return response
            gateway = OpenRouterGateway(RequestLedger(Path(directory), 1), api_key="x", opener=opener, sleep=lambda _: None)
            gateway.complete(ModelSpec("m", "m"), [], GenerationSettings(0, 1, 1, "low"), 77, None)
            self.assertEqual([77, 77, 77], [call["seed"] for call in calls])

    def test_402_is_budget_exhaustion_and_invalid_charged_response_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            def payment(*args, **kwargs):
                raise urllib.error.HTTPError("url", 402, "payment", {}, io.BytesIO())
            gateway = OpenRouterGateway(RequestLedger(Path(directory), 1), api_key="x", opener=payment)
            with self.assertRaises(BudgetExhausted):
                gateway.complete(ModelSpec("m", "m"), [], GenerationSettings(0, 1, 1, "low"), 1, None)
        with tempfile.TemporaryDirectory() as directory:
            ledger = RequestLedger(Path(directory), 1)
            gateway = OpenRouterGateway(ledger, api_key="secret-value", opener=CapturingOpener(Response({"id": "x", "usage": {"cost": 0.02}})))
            with self.assertRaises(InfrastructureError) as caught:
                gateway.complete(ModelSpec("m", "m"), [], GenerationSettings(0, 1, 1, "low"), 1, None)
            self.assertNotIn("secret-value", str(caught.exception))
            self.assertEqual("charged_invalid_response", json.loads(ledger.path.read_text())["status"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Difficulty, GenerationSettings, ModelSpec, Scenario, SuiteConfig


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _settings(data: dict[str, Any]) -> GenerationSettings:
    return GenerationSettings(
        temperature=float(data.get("temperature", 0)),
        top_p=float(data.get("top_p", 0)),
        max_tokens=int(data.get("max_tokens", 0)),
        reasoning_effort=_text(data, "reasoning_effort"),
    )

def _model(data: dict[str, Any]) -> ModelSpec:
    return ModelSpec(
        id=_text(data, "id"),
        label=_text(data, "label"),
        supports_seed=bool(data.get("supports_seed", True)),
        supports_reasoning=bool(data.get("supports_reasoning", True)),
        response_format=_text(data, "response_format") or "json_schema",
    )



def load_scenario(path: Path) -> Scenario:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(
        id=_text(data, "id"),
        title=_text(data, "title"),
        target_name=_text(data, "target_name"),
        target_persona=_text(data, "target_persona"),
        attacker_brief=_text(data, "attacker_brief"),
        scenes=list(data.get("scenes", [])),
        secret_template=_text(data, "secret_template"),
        difficulties=[Difficulty(id=_text(item, "id"), disclosure_policy=_text(item, "disclosure_policy"), decoy_template=item.get("decoy_template")) for item in data.get("difficulties", [])],
    )


def load_suite(path: Path) -> SuiteConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    routing = data.get("provider", {})
    prices = routing.get("max_price", {})
    scenario_dir = str((path.parent / _text(data, "scenario_dir")).resolve())
    return SuiteConfig(
        id=_text(data, "id"),
        version=int(data.get("version", 0)),
        scenario_dir=scenario_dir,
        models=[_model(item) for item in data.get("models", [])],
        scenario_ids=list(data.get("scenario_ids", [])),
        difficulty_ids=list(data.get("difficulty_ids", [])),
        replicates=int(data.get("replicates", 0)),
        rounds=int(data.get("rounds", 0)),
        exchanges_per_round=int(data.get("exchanges_per_round", 0)),
        planner_settings=_settings(data.get("planner_settings", {})),
        dialogue_settings=_settings(data.get("dialogue_settings", {})),
        provider_sort=_text(routing, "sort"),
        require_parameters=bool(routing.get("require_parameters", False)),
        max_prompt_price=float(prices.get("prompt", 0)),
        max_completion_price=float(prices.get("completion", 0)),
        daily_budget_usd=float(data.get("daily_budget_usd", 0)),
        suite_seed=_text(data, "suite_seed"),
    )


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({value for value in values if value in seen or seen.add(value) is not None})


def validate_suite(suite: SuiteConfig, scenarios: list[Scenario]) -> list[str]:
    errors: list[str] = []
    for name, value in (("suite id", suite.id), ("suite seed", suite.suite_seed), ("provider sort", suite.provider_sort)):
        if not value.strip():
            errors.append(f"{name} must not be empty")
    if suite.version <= 0:
        errors.append("version must be positive")
    for name, value in (("replicates", suite.replicates), ("rounds", suite.rounds), ("exchanges_per_round", suite.exchanges_per_round)):
        if value <= 0:
            errors.append(f"{name} must be positive")
    for name, value in (("max prompt price", suite.max_prompt_price), ("max completion price", suite.max_completion_price), ("daily budget", suite.daily_budget_usd)):
        if value <= 0:
            errors.append(f"{name} must be positive")
    for name, settings in (("planner", suite.planner_settings), ("dialogue", suite.dialogue_settings)):
        if settings.max_tokens <= 0:
            errors.append(f"{name} max_tokens must be positive")
        if settings.temperature < 0 or settings.top_p <= 0:
            errors.append(f"{name} generation settings must be positive")
        if settings.reasoning_effort != "low":
            errors.append(f"{name} reasoning_effort must be low")
    model_ids = [model.id for model in suite.models]
    for duplicate in _duplicates(model_ids):
        errors.append(f"duplicate model id: {duplicate}")
    if any(not model.id.strip() or not model.label.strip() for model in suite.models):
        errors.append("model ids and labels must not be empty")
    for model in suite.models:
        if model.response_format not in ("json_schema", "json_object"):
            errors.append(f"model {model.id or '<blank>'} response_format must be json_schema or json_object")
    for duplicate in _duplicates(suite.scenario_ids):
        errors.append(f"duplicate suite scenario id: {duplicate}")
    for duplicate in _duplicates(suite.difficulty_ids):
        errors.append(f"duplicate suite difficulty id: {duplicate}")
    scenario_ids = [scenario.id for scenario in scenarios]
    for duplicate in _duplicates(scenario_ids):
        errors.append(f"duplicate scenario id: {duplicate}")
    unknown = sorted(set(suite.scenario_ids) - set(scenario_ids))
    for scenario_id in unknown:
        errors.append(f"unknown scenario: {scenario_id}")
    for scenario in scenarios:
        prefix = f"scenario {scenario.id or '<blank>'}"
        for name, value in (("id", scenario.id), ("title", scenario.title), ("target_name", scenario.target_name), ("target_persona", scenario.target_persona), ("attacker_brief", scenario.attacker_brief)):
            if not value.strip():
                errors.append(f"{prefix} {name} must not be empty")
        if scenario.secret_template.count("{token}") != 1:
            errors.append(f"{prefix} secret_template must contain exactly one {{token}}")
        if len(scenario.scenes) != suite.rounds:
            errors.append(f"{prefix} must have exactly {suite.rounds} scenes")
        if any(not isinstance(scene, str) or not scene.strip() for scene in scenario.scenes):
            errors.append(f"{prefix} scenes must not be empty")
        difficulty_ids = [difficulty.id for difficulty in scenario.difficulties]
        for duplicate in _duplicates(difficulty_ids):
            errors.append(f"{prefix} duplicate difficulty id: {duplicate}")
        missing = sorted(set(suite.difficulty_ids) - set(difficulty_ids))
        extra = sorted(set(difficulty_ids) - set(suite.difficulty_ids))
        if missing:
            errors.append(f"{prefix} missing difficulties: {', '.join(missing)}")
        if extra:
            errors.append(f"{prefix} extra difficulties: {', '.join(extra)}")
        for difficulty in scenario.difficulties:
            if not difficulty.id.strip() or not difficulty.disclosure_policy.strip():
                errors.append(f"{prefix} difficulty prompts must not be empty")
            if difficulty.decoy_template is not None and difficulty.decoy_template.count("{decoy}") != 1:
                errors.append(f"{prefix} difficulty {difficulty.id} decoy_template must contain exactly one {{decoy}}")
    return errors


def load_suite_scenarios(path: Path) -> tuple[SuiteConfig, list[Scenario]]:
    suite = load_suite(path)
    directory = Path(suite.scenario_dir)
    scenarios: list[Scenario] = []
    for scenario_id in suite.scenario_ids:
        scenario_path = directory / f"{scenario_id}.json"
        if scenario_path.exists():
            scenarios.append(load_scenario(scenario_path))
    return suite, scenarios

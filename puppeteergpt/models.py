from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    PUPPETEER = "puppeteer"
    AGENT = "agent"
    TARGET = "target"
    SCENE = "scene"


class Outcome(StrEnum):
    ATTACKER_WIN = "attacker_win"
    DEFENDER_WIN = "defender_win"


class TerminationReason(StrEnum):
    SECRET_LEAK = "secret_leak"
    TURN_LIMIT = "turn_limit"
    ATTACKER_PROTOCOL_FAILURE = "attacker_protocol_failure"
    DEFENDER_PROTOCOL_FAILURE = "defender_protocol_failure"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    round_index: int
    exchange_index: int


@dataclass(frozen=True)
class GenerationSettings:
    temperature: float
    top_p: float
    max_tokens: int
    reasoning_effort: str


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    supports_seed: bool = True
    supports_reasoning: bool = True
    response_format: str = "json_schema"

@dataclass(frozen=True)
class Difficulty:
    id: str
    disclosure_policy: str
    decoy_template: str | None = None


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    target_name: str
    target_persona: str
    attacker_brief: str
    scenes: list[str]
    secret_template: str
    difficulties: list[Difficulty]


@dataclass(frozen=True)
class SuiteConfig:
    id: str
    version: int
    scenario_dir: str
    models: list[ModelSpec]
    scenario_ids: list[str]
    difficulty_ids: list[str]
    replicates: int
    rounds: int
    exchanges_per_round: int
    planner_settings: GenerationSettings
    dialogue_settings: GenerationSettings
    provider_sort: str
    require_parameters: bool
    max_prompt_price: float
    max_completion_price: float
    daily_budget_usd: float
    suite_seed: str


@dataclass(frozen=True)
class PlannerDecision:
    analysis: str
    agent_name: str
    agent_instructions: str


@dataclass(frozen=True)
class CompletionResult:
    content: str
    resolved_model: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float
    completion_id: str
    generation_id: str | None = None


@dataclass(frozen=True)
class RunSettings:
    suite_id: str
    suite_version: int
    suite_seed: str
    rounds: int
    exchanges_per_round: int
    planner_settings: GenerationSettings
    dialogue_settings: GenerationSettings
    output_path: str


@dataclass(frozen=True)
class CallUsage:
    role: Role
    round_index: int
    exchange_index: int
    seed: int
    requested_model: str
    resolved_model: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float
    completion_id: str
    generation_id: str | None


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    attacker_model: str
    defender_model: str
    scenario_id: str
    difficulty_id: str
    replicate: int
    outcome: Outcome | None
    termination_reason: TerminationReason
    secret: str
    decoy: str | None
    messages: list[Message]
    calls: list[CallUsage]
    total_cost: float
    started_at: str
    finished_at: str
    protocol_error: str | None = None
    infrastructure_error: str | None = None
    verifier_message_index: int | None = None


def to_jsonable(value: Any) -> Any:
    """Convert benchmark dataclasses and enums to JSON-compatible values."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def match_result_from_dict(data: dict[str, Any]) -> MatchResult:
    return MatchResult(
        match_id=data["match_id"],
        attacker_model=data["attacker_model"],
        defender_model=data["defender_model"],
        scenario_id=data["scenario_id"],
        difficulty_id=data["difficulty_id"],
        replicate=int(data["replicate"]),
        outcome=Outcome(data["outcome"]) if data.get("outcome") else None,
        termination_reason=TerminationReason(data["termination_reason"]),
        secret=data["secret"],
        decoy=data.get("decoy"),
        messages=[Message(Role(item["role"]), item["content"], int(item["round_index"]), int(item["exchange_index"])) for item in data.get("messages", [])],
        calls=[CallUsage(role=Role(item["role"]), round_index=int(item["round_index"]), exchange_index=int(item["exchange_index"]), seed=int(item["seed"]), requested_model=item["requested_model"], resolved_model=item["resolved_model"], finish_reason=item["finish_reason"], prompt_tokens=int(item["prompt_tokens"]), completion_tokens=int(item["completion_tokens"]), reasoning_tokens=int(item.get("reasoning_tokens", 0)), cost=float(item["cost"]), completion_id=item["completion_id"], generation_id=item.get("generation_id")) for item in data.get("calls", [])],
        total_cost=float(data.get("total_cost", 0)),
        started_at=data["started_at"],
        finished_at=data["finished_at"],
        protocol_error=data.get("protocol_error"),
        infrastructure_error=data.get("infrastructure_error"),
        verifier_message_index=data.get("verifier_message_index"),
    )

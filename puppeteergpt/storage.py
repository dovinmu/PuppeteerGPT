from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MatchResult, Role, match_result_from_dict, to_jsonable


class RequestLedger:
    def __init__(self, output: Path, daily_budget_usd: float) -> None:
        self.output = output
        self.path = output / "requests.jsonl"
        self.daily_budget_usd = daily_budget_usd
        self.output.mkdir(parents=True, exist_ok=True)
        self._daily_costs: dict[str, float] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                    day = str(record["timestamp"])[:10]
                    self._daily_costs[day] = self._daily_costs.get(day, 0.0) + float(record.get("cost", 0))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue

    @staticmethod
    def utc_day() -> str:
        return datetime.now(UTC).date().isoformat()

    def spent_today(self) -> float:
        return self._daily_costs.get(self.utc_day(), 0.0)

    def budget_available(self) -> bool:
        return self.spent_today() < self.daily_budget_usd

    def append(self, record: dict[str, Any]) -> None:
        stamped = dict(record)
        stamped.setdefault("timestamp", datetime.now(UTC).isoformat())
        encoded = json.dumps(stamped, sort_keys=True, ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        day = str(stamped["timestamp"])[:10]
        self._daily_costs[day] = self._daily_costs.get(day, 0.0) + float(stamped.get("cost", 0))


class ResultStore:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.matches = output / "matches"
        self.transcripts = output / "transcripts"
        self.matches.mkdir(parents=True, exist_ok=True)
        self.transcripts.mkdir(parents=True, exist_ok=True)

    def has_scored(self, match_id: str) -> bool:
        path = self.matches / f"{match_id}.json"
        if not path.exists():
            return False
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("outcome") is not None
        except (OSError, json.JSONDecodeError):
            return False

    def save(self, result: MatchResult) -> None:
        if result.outcome is None:
            raise ValueError("infrastructure errors are pending and must not be persisted as matches")
        data = json.dumps(to_jsonable(result), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        self._atomic_write(self.matches / f"{result.match_id}.json", data)
        self._atomic_write(self.transcripts / f"{result.match_id}.md", self._transcript(result))

    def load_all(self) -> list[MatchResult]:
        results: list[MatchResult] = []
        for path in sorted(self.matches.glob("*.json")):
            try:
                result = match_result_from_dict(json.loads(path.read_text(encoding="utf-8")))
                if result.outcome is not None:
                    results.append(result)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return results

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _transcript(result: MatchResult) -> str:
        lines = [
            f"# Match {result.match_id}",
            "",
            f"- Attacker: `{result.attacker_model}`",
            f"- Defender: `{result.defender_model}`",
            f"- Scenario: `{result.scenario_id}` / `{result.difficulty_id}` / replicate {result.replicate}",
            f"- Outcome: `{result.outcome.value}`",
            f"- Termination: `{result.termination_reason.value}`",
            f"- Cost: `${result.total_cost:.8f}`",
            "",
        ]
        for index, message in enumerate(result.messages):
            heading = message.role.value.upper()
            evidence = " — **VERIFIED SECRET LEAK**" if index == result.verifier_message_index else ""
            lines.extend([f"## {heading} r{message.round_index} e{message.exchange_index}{evidence}", "", message.content, ""])
        if result.protocol_error:
            lines.extend(["## Protocol error", "", result.protocol_error, ""])
        return "\n".join(lines)

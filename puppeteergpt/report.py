from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .models import MatchResult, Outcome, Role, TerminationReason
from .storage import ResultStore


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * ((proportion * (1 - proportion) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return center - margin, center + margin


def paired_bootstrap(pairs: list[tuple[int, int]]) -> dict[str, float | int | list[float]]:
    if not pairs:
        return {"n": 0, "difference_pp": 0.0, "interval_95_pp": [0.0, 0.0]}
    differences = [left - right for left, right in pairs]
    mean = statistics.fmean(differences)
    generator = random.Random(0)
    bootstraps = sorted(
        statistics.fmean(differences[generator.randrange(len(differences))] for _ in differences)
        for _ in range(10_000)
    )
    return {"n": len(pairs), "difference_pp": mean * 100, "interval_95_pp": [bootstraps[249] * 100, bootstraps[9749] * 100]}


def _rate(values: list[int]) -> dict[str, float | int | list[float]]:
    low, high = wilson_interval(sum(values), len(values))
    return {"successes": sum(values), "n": len(values), "rate": statistics.fmean(values) if values else 0.0, "wilson_95": [low, high]}


def _group_rates(results: list[MatchResult], field: str) -> list[dict[str, object]]:
    grouped: dict[str, list[MatchResult]] = defaultdict(list)
    for result in results:
        grouped[str(getattr(result, field))].append(result)
    rows: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        leaks = [int(result.outcome is Outcome.ATTACKER_WIN) for result in group]
        rows.append({field: key, "matches": len(group), "attacker_leak": _rate(leaks), "defender_hold": _rate([1 - value for value in leaks])})
    return rows

def _matchup_rates(results: list[MatchResult]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[MatchResult]] = defaultdict(list)
    for result in results:
        grouped[(result.attacker_model, result.defender_model)].append(result)
    rows: list[dict[str, object]] = []
    for (attacker, defender), group in sorted(grouped.items()):
        leaks = [int(result.outcome is Outcome.ATTACKER_WIN) for result in group]
        rows.append({"matchup": f"{attacker} → {defender}", "attacker_model": attacker, "defender_model": defender, "matches": len(group), "attacker_leak": _rate(leaks), "defender_hold": _rate([1 - value for value in leaks])})
    return rows


def _variability(results: list[MatchResult], success: Outcome, opponent_field: str) -> dict[str, object]:
    cells: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    scenario_difficulty: dict[tuple[str, str], list[int]] = defaultdict(list)
    for result in results:
        value = int(result.outcome is success)
        cells[(str(getattr(result, opponent_field)), result.scenario_id, result.difficulty_id)].append(value)
        scenario_difficulty[(result.scenario_id, result.difficulty_id)].append(value)
    variances = [statistics.variance(values) for values in cells.values() if len(values) >= 2]
    rates = [statistics.fmean(values) for values in scenario_difficulty.values()]
    five_run_cells = [values for values in cells.values() if len(values) == 5]
    mixed = sum(len(set(values)) > 1 for values in five_run_cells)
    return {
        "mean_within_cell_sample_variance": statistics.fmean(variances) if variances else 0.0,
        "scenario_difficulty_rate_sample_stdev": statistics.stdev(rates) if len(rates) >= 2 else 0.0,
        "mixed_five_run_cells": {"mixed": mixed, "five_run_cells": len(five_run_cells), "percentage": 100 * mixed / len(five_run_cells) if five_run_cells else 0.0},
    }



def build_report(results: Iterable[MatchResult], expected_matches: int | None = None) -> dict[str, object]:
    scored = sorted((result for result in results if result.outcome is not None), key=lambda result: result.match_id)
    model_ids = sorted({result.attacker_model for result in scored} | {result.defender_model for result in scored})
    models: dict[str, object] = {}
    for model_id in model_ids:
        offense_results = [result for result in scored if result.attacker_model == model_id]
        defense_results = [result for result in scored if result.defender_model == model_id]
        offense = [int(result.outcome is Outcome.ATTACKER_WIN) for result in offense_results]
        defense = [int(result.outcome is Outcome.DEFENDER_WIN) for result in defense_results]
        attacker_variability = _variability(offense_results, Outcome.ATTACKER_WIN, "defender_model")
        defender_variability = _variability(defense_results, Outcome.DEFENDER_WIN, "attacker_model")
        calls = [call for result in scored for call in result.calls if call.requested_model == model_id]
        models[model_id] = {
            "attacker_leak": _rate(offense),
            "defender_hold": _rate(defense),
            "attacker_variability": attacker_variability,
            "defender_variability": defender_variability,
            "usage": {
                "calls": len(calls),
                "prompt_tokens": sum(call.prompt_tokens for call in calls),
                "completion_tokens": sum(call.completion_tokens for call in calls),
                "reasoning_tokens": sum(call.reasoning_tokens for call in calls),
                "cost": sum(call.cost for call in calls),
            },
            "protocol_failures": {
                "attacker": sum(result.termination_reason is TerminationReason.ATTACKER_PROTOCOL_FAILURE for result in offense_results),
                "defender": sum(result.termination_reason is TerminationReason.DEFENDER_PROTOCOL_FAILURE for result in defense_results),
            },
        }
    comparisons: dict[str, object] = {}
    if len(model_ids) == 2:
        first, second = model_ids
        offense_blocks: dict[tuple[str, str, str, int], dict[str, int]] = defaultdict(dict)
        defense_blocks: dict[tuple[str, str, str, int], dict[str, int]] = defaultdict(dict)
        for result in scored:
            offense_blocks[(result.defender_model, result.scenario_id, result.difficulty_id, result.replicate)][result.attacker_model] = int(result.outcome is Outcome.ATTACKER_WIN)
            defense_blocks[(result.attacker_model, result.scenario_id, result.difficulty_id, result.replicate)][result.defender_model] = int(result.outcome is Outcome.DEFENDER_WIN)
        offense_pairs = [(block[first], block[second]) for block in offense_blocks.values() if first in block and second in block]
        defense_pairs = [(block[first], block[second]) for block in defense_blocks.values() if first in block and second in block]
        comparisons = {"first_model": first, "second_model": second, "offense": paired_bootstrap(offense_pairs), "defense": paired_bootstrap(defense_pairs)}
    expected = expected_matches if expected_matches is not None else len(scored)
    return {
        "partial": len(scored) != expected,
        "completed_matches": len(scored),
        "expected_matches": expected,
        "models": models,
        "comparisons": comparisons,
        "matchups": _matchup_rates(scored),
        "scenarios": _group_rates(scored, "scenario_id"),
        "difficulties": _group_rates(scored, "difficulty_id"),
        "total": {
            "calls": sum(len(result.calls) for result in scored),
            "prompt_tokens": sum(call.prompt_tokens for result in scored for call in result.calls),
            "completion_tokens": sum(call.completion_tokens for result in scored for call in result.calls),
            "reasoning_tokens": sum(call.reasoning_tokens for result in scored for call in result.calls),
            "cost": sum(result.total_cost for result in scored),
        },
        "transcripts": [f"transcripts/{result.match_id}.md" for result in scored],
    }

def _ledger_total(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    def usage(record: dict[str, object], key: str) -> int:
        if key in record:
            return int(record.get(key, 0) or 0)
        response = record.get("response")
        response_usage = response.get("usage", {}) if isinstance(response, dict) else {}
        if key == "reasoning_tokens":
            details = response_usage.get("completion_tokens_details", {}) if isinstance(response_usage, dict) else {}
            return int(details.get("reasoning_tokens", 0) or 0) if isinstance(details, dict) else 0
        return int(response_usage.get(key, 0) or 0) if isinstance(response_usage, dict) else 0
    return {
        "calls": len(records),
        "prompt_tokens": sum(usage(record, "prompt_tokens") for record in records),
        "completion_tokens": sum(usage(record, "completion_tokens") for record in records),
        "reasoning_tokens": sum(usage(record, "reasoning_tokens") for record in records),
        "cost": sum(float(record.get("cost", 0) or 0) for record in records),
        "source": "charged_request_ledger",
    }



def write_report(output: Path, results: Iterable[MatchResult], expected_matches: int | None = None) -> dict[str, object]:
    report = build_report(results, expected_matches)
    ledger_total = _ledger_total(output / "requests.jsonl")
    if ledger_total is not None:
        report["total"] = ledger_total
    output.mkdir(parents=True, exist_ok=True)
    ResultStore._atomic_write(output / "summary.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = ["# PuppeteerGPT benchmark report", ""]
    if report["partial"]:
        lines.extend([f"**PARTIAL REPORT: {report['completed_matches']} of {report['expected_matches']} requested matches completed.**", ""])
    else:
        lines.extend([f"Complete: {report['completed_matches']} of {report['expected_matches']} requested matches.", ""])
    lines.extend(["## Models", ""])
    for model_id, metrics in report["models"].items():
        attacker = metrics["attacker_leak"]
        defender = metrics["defender_hold"]
        lines.extend([
            f"### `{model_id}`",
            "",
            f"- Attacker leak rate: {attacker['rate']:.1%} ({attacker['successes']}/{attacker['n']}), Wilson 95% [{attacker['wilson_95'][0]:.1%}, {attacker['wilson_95'][1]:.1%}]",
            f"- Defender hold rate: {defender['rate']:.1%} ({defender['successes']}/{defender['n']}), Wilson 95% [{defender['wilson_95'][0]:.1%}, {defender['wilson_95'][1]:.1%}]",
            f"- Attacker mean within-cell sample variance: {metrics['attacker_variability']['mean_within_cell_sample_variance']:.4f}",
            f"- Attacker scenario-difficulty rate sample SD: {metrics['attacker_variability']['scenario_difficulty_rate_sample_stdev']:.4f}",
            f"- Attacker mixed five-run cells: {metrics['attacker_variability']['mixed_five_run_cells']['mixed']}/{metrics['attacker_variability']['mixed_five_run_cells']['five_run_cells']} ({metrics['attacker_variability']['mixed_five_run_cells']['percentage']:.1f}%)",
            f"- Defender mean within-cell sample variance: {metrics['defender_variability']['mean_within_cell_sample_variance']:.4f}",
            f"- Defender scenario-difficulty rate sample SD: {metrics['defender_variability']['scenario_difficulty_rate_sample_stdev']:.4f}",
            f"- Defender mixed five-run cells: {metrics['defender_variability']['mixed_five_run_cells']['mixed']}/{metrics['defender_variability']['mixed_five_run_cells']['five_run_cells']} ({metrics['defender_variability']['mixed_five_run_cells']['percentage']:.1f}%)",
            f"- Protocol failures: {metrics['protocol_failures']['attacker']} as attacker; {metrics['protocol_failures']['defender']} as defender",
            "",
        ])
    if report["comparisons"]:
        comparison = report["comparisons"]
        lines.extend(["## Matched model differences", "", f"First minus second: `{comparison['first_model']}` − `{comparison['second_model']}`.", ""])
        for role in ("offense", "defense"):
            metric = comparison[role]
            lines.append(f"- {role.title()}: {metric['difference_pp']:.2f} pp over n={metric['n']} matched blocks; paired bootstrap 95% [{metric['interval_95_pp'][0]:.2f}, {metric['interval_95_pp'][1]:.2f}] pp")
        lines.append("")
    for heading, key, label in (("Matchup table", "matchups", "matchup"), ("Scenario table", "scenarios", "scenario_id"), ("Difficulty table", "difficulties", "difficulty_id")):
        lines.extend([f"## {heading}", "", "| Value | n | Leak rate | Hold rate |", "|---|---:|---:|---:|"])
        for row in report[key]:
            lines.append(f"| `{row[label]}` | {row['matches']} | {row['attacker_leak']['rate']:.1%} | {row['defender_hold']['rate']:.1%} |")
        lines.append("")
    total = report["total"]
    lines.extend(["## Usage", "", f"{total['calls']} calls; {total['prompt_tokens']} prompt, {total['completion_tokens']} completion, and {total['reasoning_tokens']} reasoning tokens; exact cost `${total['cost']:.8f}`.", "", "## Transcripts", ""])
    lines.extend(f"- [{Path(path).stem}]({path})" for path in report["transcripts"])
    lines.append("")
    ResultStore._atomic_write(output / "summary.md", "\n".join(lines))
    return report

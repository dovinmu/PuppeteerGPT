import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from puppeteergpt.config import load_scenario, load_suite, load_suite_scenarios, validate_suite
from puppeteergpt.models import Difficulty


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("benchmark/suites/v4-flash.json")
        cls.suite, cls.scenarios = load_suite_scenarios(cls.path)

    def errors(self, suite=None, scenarios=None):
        return validate_suite(suite or self.suite, scenarios or self.scenarios)

    def test_versioned_suite_is_accepted_and_path_is_resolved(self):
        self.assertEqual([], self.errors())
        self.assertTrue(Path(self.suite.scenario_dir).is_absolute())
        self.assertEqual(4, len(self.scenarios))

    def test_loaders_read_json(self):
        self.assertEqual("nice-birdy", load_scenario(Path(self.suite.scenario_dir) / "nice-birdy.json").id)
        self.assertEqual("v4-flash-comparison", load_suite(self.path).id)

    def test_duplicate_ids_are_rejected(self):
        suite = dataclasses.replace(self.suite, scenario_ids=["nice-birdy", "nice-birdy"])
        self.assertTrue(any("duplicate suite scenario" in error for error in self.errors(suite=suite)))
        duplicate = dataclasses.replace(self.scenarios[1], id=self.scenarios[0].id)
        self.assertTrue(any("duplicate scenario id" in error for error in self.errors(scenarios=[self.scenarios[0], duplicate])))

    def test_secret_placeholder_absent_or_repeated_is_rejected(self):
        for template in ("none", "{token}-{token}"):
            scenario = dataclasses.replace(self.scenarios[0], secret_template=template)
            self.assertTrue(any("exactly one {token}" in error for error in self.errors(scenarios=[scenario] + self.scenarios[1:])))

    def test_decoy_placeholder_must_appear_exactly_once(self):
        hard = dataclasses.replace(self.scenarios[2].difficulties[2], decoy_template="{decoy}-{decoy}")
        scenario = dataclasses.replace(self.scenarios[2], difficulties=self.scenarios[2].difficulties[:2] + [hard])
        self.assertTrue(any("exactly one {decoy}" in error for error in self.errors(scenarios=self.scenarios[:2] + [scenario] + self.scenarios[3:])))

    def test_missing_extra_and_repeated_difficulties_are_rejected(self):
        scenario = dataclasses.replace(self.scenarios[0], difficulties=[self.scenarios[0].difficulties[0], self.scenarios[0].difficulties[0], Difficulty("bonus", "prompt")])
        errors = self.errors(scenarios=[scenario] + self.scenarios[1:])
        self.assertTrue(any("duplicate difficulty" in error for error in errors))
        self.assertTrue(any("missing difficulties" in error for error in errors))
        self.assertTrue(any("extra difficulties" in error for error in errors))

    def test_scene_count_and_empty_prompts_are_rejected(self):
        scenario = dataclasses.replace(self.scenarios[0], scenes=[""], attacker_brief="")
        errors = self.errors(scenarios=[scenario] + self.scenarios[1:])
        self.assertTrue(any("exactly 3 scenes" in error for error in errors))
        self.assertTrue(any("scenes must not be empty" in error for error in errors))
        self.assertTrue(any("attacker_brief must not be empty" in error for error in errors))

    def test_nonpositive_limits_and_non_low_reasoning_are_rejected(self):
        settings = dataclasses.replace(self.suite.planner_settings, max_tokens=0, reasoning_effort="medium")
        suite = dataclasses.replace(self.suite, replicates=0, planner_settings=settings)
        errors = self.errors(suite=suite)
        self.assertTrue(any("replicates must be positive" in error for error in errors))
        self.assertTrue(any("planner max_tokens" in error for error in errors))
        self.assertTrue(any("reasoning_effort must be low" in error for error in errors))

    def test_model_capabilities_are_loaded_and_validated(self):
        suite, scenarios = load_suite_scenarios(Path("benchmark/suites/union-alpha-hard.json"))
        model = suite.models[0]
        self.assertFalse(model.supports_seed)
        self.assertFalse(model.supports_reasoning)
        self.assertEqual("json_object", model.response_format)
        self.assertEqual([], validate_suite(suite, scenarios))
        invalid = dataclasses.replace(model, response_format="xml")
        errors = validate_suite(dataclasses.replace(suite, models=[invalid]), scenarios)
        self.assertTrue(any("response_format" in error for error in errors))

    def test_unknown_scenario_is_rejected(self):
        suite = dataclasses.replace(self.suite, scenario_ids=self.suite.scenario_ids + ["missing"])
        self.assertIn("unknown scenario: missing", self.errors(suite=suite))


if __name__ == "__main__":
    unittest.main()

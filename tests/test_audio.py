import unittest

from puppeteergpt.audio import VoiceSet, build_audio_script, planner_analysis, split_delivery


class AudioTests(unittest.TestCase):
    def test_split_delivery_separates_actions_without_losing_dialogue(self):
        self.assertEqual(
            [("dialogue", "Hello."), ("action", "I bow."), ("dialogue", "Your move.")],
            split_delivery("Hello. *I bow.* Your move."),
        )

    def test_planner_analysis_extracts_only_spoken_scheme(self):
        content = '{"analysis":"Change tactics.","agent_name":"Mara","agent_instructions":"Long private role."}'
        self.assertEqual("Change tactics.", planner_analysis(content))
        self.assertIsNone(planner_analysis("not JSON"))

    def test_script_includes_kate_intro_and_reuses_character_voice_for_actions(self):
        match = {
            "match_id": "match",
            "scenario_id": "midsummer-riddles",
            "difficulty_id": "hard",
            "outcome": "attacker_win",
            "messages": [
                {"role": "scene", "content": "A moonlit wood.", "round_index": 1, "exchange_index": 0},
                {
                    "role": "puppeteer",
                    "content": '{"analysis":"Exploit Puck’s love of pranks.","agent_name":"Bramblejack","agent_instructions":"Play along."}',
                    "round_index": 1,
                    "exchange_index": 0,
                },
                {"role": "agent", "content": "Let us play.", "round_index": 1, "exchange_index": 1},
                {"role": "target", "content": "*I grin.* A fine game.", "round_index": 1, "exchange_index": 1},
            ],
        }
        script = build_audio_script(match, {"title": "Midsummer Riddles", "target_name": "Puck"})
        intro = script[0]
        self.assertEqual(("puppeteer", "intro", "macos", "Kate (Enhanced)"), (intro.role, intro.mode, intro.backend, intro.voice))
        self.assertIn("I am the Puppeteer", intro.text)
        scheme = next(segment for segment in script if segment.mode == "scheming")
        self.assertEqual(("macos", "Kate (Enhanced)"), (scheme.backend, scheme.voice))
        self.assertIn("Exploit Puck’s love of pranks.", scheme.text)
        self.assertNotIn("Play along", scheme.text)
        agent = next(segment for segment in script if segment.role == "agent")
        self.assertEqual(("kokoro", "bm_george"), (agent.backend, agent.voice))
        target = [segment for segment in script if segment.role == "target"]
        self.assertEqual(["action", "dialogue"], [segment.mode for segment in target])
        self.assertEqual({("kokoro", "am_puck")}, {(segment.backend, segment.voice) for segment in target})
        self.assertLess(target[0].speed, target[1].speed)
        self.assertLess(target[0].volume, target[1].volume)


if __name__ == "__main__":
    unittest.main()

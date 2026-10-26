"""Offline regressions; model/network boundaries are mocked unless explicitly tested."""
import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.speech import analyze_speech
from modules import nlp, voice_emotion
from modules.transcript import measured_duration
from modules.insights import _build_prompt
from graph import nodes
from graph.analysis_graph import run_analysis


class SpeechTests(unittest.TestCase):
    def test_timing_union_and_partially_timed_text(self):
        transcript = [{"speaker": "user", "text": "a", "audioStartSeconds": 0, "audioEndSeconds": 4},
                      {"speaker": "user", "text": "b", "audioStartSeconds": 3, "audioEndSeconds": 6},
                      {"speaker": "ai", "text": "question"}]
        self.assertEqual(measured_duration(transcript), 6)
        transcript.append({"speaker": "user", "text": "typed answer"})
        self.assertIsNone(measured_duration(transcript))

    def test_insights_do_not_claim_unavailable_pace(self):
        prompt = _build_prompt("INTERVIEW", analyze_speech("answer"), {}, {}, {}, {}, .7, "answer")
        self.assertIn("WPM=unavailable", prompt)
    def test_pace_without_timing_is_unavailable(self):
        result = analyze_speech("word " * 140)
        self.assertIsNone(result["wpm_estimate"])
        self.assertFalse(result["pace_available"])
        self.assertEqual(result["score"], 0.909)

    def test_measured_pace_and_fillers(self):
        for wpm in (90, 140, 190):
            with self.subTest(wpm=wpm):
                result = analyze_speech("word " * wpm, duration_seconds=60)
                self.assertEqual(result["wpm_estimate"], wpm)
                self.assertTrue(result["pace_available"])
        self.assertEqual(analyze_speech("um uh like you know.")["fillers"], 4)

    def test_invalid_duration_does_not_fabricate_pace(self):
        for duration in (0, -1, float("nan"), float("inf")):
            self.assertIsNone(analyze_speech("hello", duration)["wpm_estimate"])


class GraphTests(unittest.TestCase):
    def test_all_scenarios_and_both_answer_ends_are_scored(self):
        for scenario in ("INTERVIEW", "PITCH", "MEETING"):
            for first, last in ((.2, .8), (.8, .2)):
                def score(text, context, scenario, question=None):
                    value = first if text.startswith("first") else last
                    return {"score": value, "clarity": value, "structure": value, "relevance": value}
                with patch.object(nodes, "analyze_language", side_effect=score):
                    result = nodes.nlp_node({"scenario": scenario, "user_text": "first\nlast", "transcript": [
                        {"speaker": "user", "text": "first"}, {"speaker": "user", "text": "last"}]})
                self.assertEqual(result["nlp"]["score"], .5)

    def test_long_answer_has_no_first_window_bias(self):
        with patch.object(nlp, "_star_classify", return_value=(.5, .5)) as classifier:
            nlp.analyze_language("early " * 300 + "late " * 300, {}, question="actual question")
        joined = " ".join(call.args[0] for call in classifier.call_args_list)
        self.assertIn("early", joined)
        self.assertIn("late", joined)
        self.assertTrue(all(call.args[2] == "actual question" for call in classifier.call_args_list))

    def test_adaptive_template_writes_are_disabled(self):
        with patch.object(nodes, "maybe_add_template") as store:
            nodes.template_store_node({"scenario": "INTERVIEW", "user_text": "private words", "confidence": .99})
        store.assert_not_called()
    def test_alignment_never_receives_ai_words(self):
        with patch.object(nodes, "analyze_alignment", return_value={"score": .8}) as scorer:
            nodes.alignment_node({"scenario": "INTERVIEW", "user_text": "my answer", "full_text": "AI impact metrics"})
            self.assertEqual(scorer.call_args.args[1], "my answer")

    def test_language_uses_all_user_turns(self):
        transcript = [{"speaker": "ai", "text": "question"},
                      {"speaker": "user", "text": "weak answer"},
                      {"speaker": "ai", "text": "another question"},
                      {"speaker": "user", "text": "strong result"}]
        seen = []
        def score(text, context, scenario, question=None):
            seen.append((text, question))
            value = .2 if text.startswith("weak") else .8
            return {"score": value, "clarity": value, "structure": value, "relevance": value,
                    "scoring_method": "fixture", "strengths": [], "weaknesses": [], "suggestions": []}
        with patch.object(nodes, "analyze_language", side_effect=score):
            result = nodes.nlp_node({"scenario": "INTERVIEW", "transcript": transcript,
                                     "user_text": "weak answer\nstrong result", "full_text": "AI words"})
        self.assertEqual(seen, [("weak answer", "question"), ("strong result", "another question")])
        self.assertEqual(result["nlp"]["score"], .5)

    def test_parallel_failures_preserve_siblings_and_errors(self):
        with patch.object(nodes, "analyze_speech", side_effect=ValueError("speech fixture")), \
             patch.object(nodes, "analyze_alignment", side_effect=ValueError("alignment fixture")), \
             patch.object(nodes, "analyze_emotion", return_value={"available": False}), \
             patch.object(nodes, "analyze_language", return_value={"score": .8, "clarity": .8, "structure": .8, "relevance": .8}), \
             patch.object(nodes, "generate_insights", return_value={}), \
             patch.object(nodes, "generate_job_recommendations", return_value=[]), \
             patch.object(nodes, "maybe_add_template"):
            result = run_analysis("INTERVIEW", {}, [{"speaker": "user", "text": "my answer"}])
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(result["nlp"]["score"], .8)
        self.assertIn("confidence", result)


class VoiceTests(unittest.TestCase):
    def test_missing_head_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            voice_emotion._validate_loaded_weights({"missing_keys": ["classifier.dense.weight"]})
        voice_emotion._validate_loaded_weights({"missing_keys": [], "mismatched_keys": [], "error_msgs": []})
    def test_unavailable_model_uses_existing_librosa_fallback(self):
        with patch("modules.voice_emotion.analyze_voice_emotion", return_value={"available": False}), \
             patch("modules.voice.analyze_voice", return_value={"available": True, "confidence_score": .6}) as fallback:
            result = nodes.voice_node({"audio_b64": base64.b64encode(b"\0\0" * 16000).decode()})
        fallback.assert_called_once()
        self.assertEqual(result["voice"]["confidence_score"], .6)

    def test_malformed_pcm_is_unavailable(self):
        self.assertFalse(voice_emotion.analyze_voice_emotion("invalid!")["available"])


if __name__ == "__main__":
    unittest.main()

"""Explicit opt-in real-model smoke; uses cached artifacts and no Gemini calls.

PowerShell: $env:HF_HUB_OFFLINE='1'; $env:RUN_MODEL_SMOKE='1'
Run with the analysis virtual environment's Python and unittest discovery.
"""
import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(os.environ.get("RUN_MODEL_SMOKE") == "1", "set RUN_MODEL_SMOKE=1 to load real cached models")
class ModelSmokeTests(unittest.TestCase):
    def test_publisher_voice_reference_is_reproducible(self):
        from modules.voice_emotion import analyze_voice_emotion
        audio = base64.b64encode(bytes(32000)).decode()
        first = analyze_voice_emotion(audio)
        second = analyze_voice_emotion(audio)
        self.assertTrue(first["available"], first.get("reason"))
        for key, expected in (("arousal", .5460754), ("dominance", .6062266), ("valence", .40431657)):
            self.assertAlmostEqual(first[key], expected, delta=.02)
            self.assertAlmostEqual(first[key], second[key], places=4)

    def test_graph_with_real_models_and_without_audio(self):
        from graph.analysis_graph import run_analysis
        from graph import nodes
        transcript = [{"speaker": "ai", "text": "Describe a project you led."},
                      {"speaker": "user", "text": "I led the checkout project. Our task was to reduce errors. "
                       "I tested the payment flow with the team, fixed the issue and reduced failures by 40%. "
                       "I learned to add monitoring before release."}]
        with patch.object(nodes, "generate_insights", return_value={"generated_by": "offline_smoke"}):
            result = run_analysis("INTERVIEW", {"role": "Software Engineer"}, transcript)
        self.assertFalse(result["errors"])
        self.assertFalse(result["voice"]["available"])
        self.assertIn("star_classifier", result["nlp"]["scoring_method"])
        self.assertTrue(result["emotion"]["available"])
        self.assertGreater(len(result["jobs"]), 0)
        self.assertFalse(result["speech"]["pace_available"])

    def test_real_librosa_still_handles_pcm(self):
        import numpy as np
        from modules.voice import analyze_voice
        samples = (.2 * np.sin(2 * np.pi * 180 * np.arange(16000) / 16000) * 32767).astype("<i2")
        result = analyze_voice(base64.b64encode(samples.tobytes()).decode())
        self.assertTrue(result["available"])


if __name__ == "__main__":
    unittest.main()

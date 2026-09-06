"""
Adaptive template store for NLP structure scoring.
Persists high-quality transcripts (confidence >= 0.85) as scenario-specific
gold standards, replacing the hardcoded SCENARIO_TEMPLATES in nlp.py.

Templates are stored in a JSON file alongside the service and loaded at startup.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── Storage path ───────────────────────────────────────────────────────────────
_STORE_PATH = Path(os.environ.get("TEMPLATE_STORE_PATH", "/tmp/speakez_templates.json"))
_MAX_PER_SCENARIO = 10
_MIN_CONFIDENCE = 0.85

# ── Default templates (used until real ones accumulate) ────────────────────────
_DEFAULTS: Dict[str, List[str]] = {
    "INTERVIEW": [
        "In my previous role I faced a situation where I had to deliver under tight constraints. "
        "My task was to improve team velocity. I coordinated across three teams, introduced a new "
        "deployment pipeline, and as a result we reduced release time by 40% and shipped on schedule.",
        "I led a cross-functional project with competing stakeholder priorities. By mapping each "
        "decision to clear metrics and running weekly syncs, I kept alignment and delivered measurable "
        "improvements in customer satisfaction.",
    ],
    "PITCH": [
        "The core problem is that small businesses waste hours each week on manual invoicing. "
        "Our solution automates this with AI, saving 5+ hours per week per business. "
        "We have 200 beta users and a 92% retention rate. We are raising $500k to scale marketing.",
        "The market for remote collaboration tools is $40B and growing. Our differentiation is "
        "real-time async video that integrates with existing tools. We have signed 3 enterprise pilots.",
    ],
    "MEETING": [
        "Status: we are on track for the Q3 launch. The key decision today is whether to prioritise "
        "the mobile flow or the desktop redesign. I recommend mobile because 60% of our users are on "
        "mobile. The action item is for design to deliver mockups by Thursday — owner: Sarah.",
        "We have two blockers: API rate limits and the vendor delay. I have a resolution for each "
        "with an assigned owner and deadline. The critical path is unblocked if we approve option A today.",
    ],
}


def _load() -> Dict[str, List[str]]:
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text())
            # Merge defaults for any missing scenarios
            for scenario, defaults in _DEFAULTS.items():
                if scenario not in data or not data[scenario]:
                    data[scenario] = defaults
            return data
        except Exception as exc:
            logger.warning("[template-store] load failed: %s — using defaults", exc)
    return dict(_DEFAULTS)


def _save(data: Dict[str, List[str]]) -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("[template-store] save failed: %s", exc)


# ── Public API ─────────────────────────────────────────────────────────────────

def get_templates(scenario: str) -> List[str]:
    """Return stored gold-standard templates for a scenario."""
    data = _load()
    templates = data.get(scenario.upper(), _DEFAULTS.get(scenario.upper(), []))
    return templates or _DEFAULTS.get("INTERVIEW", [])


def maybe_add_template(scenario: str, user_text: str, confidence: float) -> bool:
    """
    If confidence >= threshold, save this transcript as a new gold standard.
    Returns True if the template was added.
    """
    if confidence < _MIN_CONFIDENCE or len(user_text.strip()) < 80:
        return False

    data = _load()
    key = scenario.upper()
    if key not in data:
        data[key] = list(_DEFAULTS.get(key, []))

    # Avoid near-duplicates (simple length+start check)
    for existing in data[key]:
        if existing[:60] == user_text[:60]:
            return False

    data[key].append(user_text.strip()[:1200])
    # Cap at max
    if len(data[key]) > _MAX_PER_SCENARIO:
        # Keep most recently added (remove oldest non-default)
        defaults = _DEFAULTS.get(key, [])
        non_defaults = [t for t in data[key] if t not in defaults]
        data[key] = defaults + non_defaults[-(_MAX_PER_SCENARIO - len(defaults)):]

    _save(data)
    logger.info("[template-store] added template for %s (confidence=%.3f, total=%d)",
                key, confidence, len(data[key]))
    return True

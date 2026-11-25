"""Theory question bank: topics and questions for the Norwegian theory test.

Data lives in data/theory/ (topics.json, questions.json). A question is one of:
  single  - one correct option
  multi   - several correct options ("choose all that apply")
and may carry an image: {"sign": "<sign id>"} or a scene spec rendered by webapp/scene.ts
({"scene": "crossroad" | "t_junction" | "roundabout" | "road", ...}). New situations are new
data, not new pictures. validate() is the contract; tests run it on every change.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

BASE = os.path.dirname(os.path.abspath(__file__))
LANGS = ("no", "en", "uk", "ru")
TYPES = ("single", "multi")
SCENES = ("crossroad", "t_junction", "roundabout", "road")
ARMS = ("N", "E", "S", "W")


def _load(name: str) -> dict:
    with open(os.path.join(BASE, "data", "theory", name), encoding="utf-8") as f:
        return json.load(f)


def load() -> tuple[dict, List[dict]]:
    return _load("topics.json"), _load("questions.json")["questions"]


def validate(topics: dict, questions: List[dict], sign_ids: set) -> List[str]:
    """Every problem as a readable line; an empty list means the bank is consistent."""
    errors: List[str] = []
    classes = set(topics["classes"])
    topic_ids = {t["id"] for t in topics["topics"]}
    for t in topics["topics"]:
        for field in ("names", "summary"):
            missing = [lang for lang in LANGS if not t.get(field, {}).get(lang)]
            if missing:
                errors.append(f"topic {t['id']}: {field} missing {missing}")
    seen = set()
    for q in questions:
        qid = q.get("id", "?")
        if qid in seen:
            errors.append(f"{qid}: duplicate id")
        seen.add(qid)
        if q.get("topic") not in topic_ids:
            errors.append(f"{qid}: unknown topic {q.get('topic')}")
        if q.get("type") not in TYPES:
            errors.append(f"{qid}: unknown type {q.get('type')}")
        if not q.get("classes") or not set(q["classes"]) <= classes:
            errors.append(f"{qid}: classes must be a non-empty subset of {sorted(classes)}")
        option_ids = [o["id"] for o in q.get("options", [])]
        if not 2 <= len(option_ids) <= 4 or len(set(option_ids)) != len(option_ids):
            errors.append(f"{qid}: 2-4 options with unique ids")
        correct = q.get("correct", [])
        if not correct or not set(correct) <= set(option_ids):
            errors.append(f"{qid}: correct must name existing options")
        if q.get("type") == "single" and len(correct) != 1:
            errors.append(f"{qid}: a single-choice question has exactly one correct option")
        texts = [("text", q.get("text", {})), ("explanation", q.get("explanation", {}))]
        texts += [(f"option {o['id']}", o.get("text", {})) for o in q.get("options", [])]
        for label, value in texts:
            missing = [lang for lang in LANGS if not value.get(lang)]
            if missing:
                errors.append(f"{qid}: {label} missing {missing}")
        if not q.get("source"):
            errors.append(f"{qid}: source is required")
        image = q.get("image")
        if image:
            if "sign" in image and image["sign"] not in sign_ids:
                errors.append(f"{qid}: unknown sign {image['sign']}")
            if "scene" in image:
                if image["scene"] not in SCENES:
                    errors.append(f"{qid}: unknown scene {image['scene']}")
                for sign in image.get("signs", []):
                    if sign.get("id") not in sign_ids or sign.get("arm") not in ARMS:
                        errors.append(f"{qid}: scene sign {sign} needs a known id and an arm")
    return errors


def for_class(questions: List[dict], licence_class: str) -> List[dict]:
    return [q for q in questions if licence_class in q["classes"]]


def public(q: dict) -> Dict:
    """What the client may see before answering: no correct ids, no explanation."""
    return {k: q[k] for k in ("id", "topic", "type", "difficulty", "image", "text", "options") if k in q}

"""Checks that a Flow reply matches the screen it opens.

Meta shows a Flow screen from the fields the reply sends. A field the screen shows but the
reply leaves out, or a value of the wrong type, makes the Flow fail with "Something went wrong".
These checks read the Flow JSON that is published and compare each reply with its screen.
"""

import json
import re
from pathlib import Path
from typing import Any

MAX_LIST_ROWS = 20
MAX_OPTION_TITLE = 30
FLOWS = Path(__file__).resolve().parents[1] / "whatsapp_flows"
_PYTHON_TYPES: dict[str, Any] = {"string": str, "array": list, "object": dict, "boolean": bool, "number": (int, float), "integer": int}


def _screen(flow_name: str, screen_id: str) -> dict[str, Any]:
    flow = json.loads((FLOWS / f"{flow_name}.json").read_text(encoding="utf-8"))
    for screen in flow["screens"]:
        if screen["id"] == screen_id:
            return screen
    raise AssertionError(f"{flow_name} has no screen {screen_id}")


def _check_value(path: str, declared: dict[str, Any], value: Any) -> None:
    kind = declared.get("type")
    if kind in _PYTHON_TYPES:
        if kind in ("number", "integer") and isinstance(value, bool):
            raise AssertionError(f"{path} should be {kind}, got bool")
        assert isinstance(value, _PYTHON_TYPES[kind]), f"{path} should be {kind}, got {type(value).__name__}: {str(value)[:60]!r}"
    if kind == "array" and isinstance(declared.get("items"), dict) and declared["items"].get("type") == "object":
        properties = declared["items"].get("properties", {})
        for index, item in enumerate(value):
            assert isinstance(item, dict), f"{path}[{index}] should be an object"
            for key, sub in properties.items():
                assert key in item, f"{path}[{index}] lacks {key}"
                _check_value(f"{path}[{index}].{key}", sub, item[key])


def check_reply(flow_name: str, reply: dict[str, Any]) -> None:
    """Raise AssertionError if the reply does not carry what its screen shows, with the declared types."""
    screen = _screen(flow_name, reply["screen"])
    data = reply.get("data") or {}
    referenced = set(re.findall(r"\$\{data\.([A-Za-z_]+)\}", json.dumps(screen, ensure_ascii=False)))
    missing = sorted(referenced - set(data))
    assert not missing, f"{flow_name} {reply['screen']} reply lacks fields the screen shows: {missing}"
    for key, declared in (screen.get("data") or {}).items():
        if key in data:
            _check_value(f"{reply['screen']}.{key}", declared, data[key])
    bound = set(re.findall(r'"data-source": "\$\{data\.([A-Za-z_]+)\}"', json.dumps(screen, ensure_ascii=False)))
    for key in bound:
        if key in data:
            assert data[key], f"{reply['screen']}.{key} is an empty list; WhatsApp cannot show a choice list with no rows"
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) and "id" in item and "title" in item for item in value):
            assert len(value) <= MAX_LIST_ROWS, f"{reply['screen']}.{key} has {len(value)} rows; WhatsApp allows {MAX_LIST_ROWS}"
            for item in value:
                assert len(str(item["title"])) <= MAX_OPTION_TITLE, f"{reply['screen']}.{key} title is longer than {MAX_OPTION_TITLE}: {item['title']!r}"

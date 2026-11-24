"""The Flow JSON shipped in backend/whatsapp_flows/ must agree with the screens and fields the backend returns.

Meta rejects a Flow whose routing model points at a missing screen, or whose
data fields don't match what the endpoint sends. These checks run without
Meta, so a mismatch fails the build here instead of at publish time.
"""

import json
from pathlib import Path

import pytest

from app.services.registration import TRADE_OPTIONS
from app.services.whatsapp_flows import (
    CONTRACTOR_MENU_CHOICES,
    OWNER_MENU_CHOICES,
    REGISTRATION_SCREEN_FIELDS,
)

FLOW_DIR = Path(__file__).resolve().parents[1] / "whatsapp_flows"
FLOWS = ("registration", "owner_dashboard", "contractor_dashboard")

REGISTRATION_SCREENS = {"SPLASH", "REGISTER", "RESULT_OK", "SUMMARY", "THANKS", "RESULT_ERROR", "EXPIRED"}
DASHBOARD_SCREENS = {"MENU", "DOCUMENTS", "LINKS_SENT", "COMING_SOON", "EXPIRED"}
OWNER_TENDER_SCREENS = {"CREATE_TENDER", "REVIEW", "MY_TENDERS", "TENDER_DETAILS", "AMEND", "OFFERS", "DONE"}
CONTRACTOR_TENDER_SCREENS = {
    "SEARCH", "PROJECT_LIST", "PROJECT_DETAILS", "SUBMIT_OFFER", "REVIEW_OFFER", "MY_OFFERS",
    "OFFER_DETAILS", "OFFER_HISTORY", "AWARDS", "DONE",
}


def _load(name: str) -> dict:
    return json.loads((FLOW_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _screens(flow: dict) -> dict[str, dict]:
    return {screen["id"]: screen for screen in flow["screens"]}


def _components(screen: dict):
    stack = list(screen["layout"]["children"])
    while stack:
        component = stack.pop()
        yield component
        stack.extend(component.get("children", []))


@pytest.mark.parametrize("name", FLOWS)
def test_each_flow_file_is_valid_json_with_the_required_top_level_keys(name):
    flow = _load(name)
    assert flow["version"] == "7.0"
    assert flow["data_api_version"] == "3.0"
    assert isinstance(flow["screens"], list) and flow["screens"]


@pytest.mark.parametrize("name", FLOWS)
def test_screen_ids_are_unique(name):
    ids = [screen["id"] for screen in _load(name)["screens"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("name", FLOWS)
def test_every_routing_target_is_a_real_screen(name):
    flow = _load(name)
    screen_ids = set(_screens(flow))
    for source, targets in flow.get("routing_model", {}).items():
        assert source in screen_ids, f"routing source {source} is not a screen"
        for target in targets:
            assert target in screen_ids, f"{source} routes to missing screen {target}"


@pytest.mark.parametrize("name", FLOWS)
def test_terminal_screens_have_a_complete_action_and_no_routing(name):
    flow = _load(name)
    routing = flow.get("routing_model", {})
    for screen in flow["screens"]:
        if screen.get("terminal"):
            assert screen["id"] not in routing, f"terminal screen {screen['id']} must not route onward"
            footers = [c for c in _components(screen) if c.get("type") == "Footer"]
            assert footers, f"terminal screen {screen['id']} needs a footer"
            assert footers[0]["on-click-action"]["name"] == "complete"


@pytest.mark.parametrize("name", FLOWS)
def test_every_data_exchange_footer_names_fields_the_form_actually_has(name):
    flow = _load(name)
    for screen in flow["screens"]:
        components = list(_components(screen))
        form_fields = {c["name"] for c in components if "name" in c}
        for component in components:
            if component.get("type") != "Footer":
                continue
            action = component["on-click-action"]
            if action["name"] != "data_exchange":
                continue
            for value in action["payload"].values():
                if isinstance(value, str) and value.startswith("${form."):
                    field = value[len("${form.") : -1]
                    assert field in form_fields, f"{screen['id']} submits unknown field {field}"


def test_registration_flow_has_exactly_the_screens_the_backend_uses():
    assert set(_screens(_load("registration"))) == REGISTRATION_SCREENS


def test_registration_data_fields_match_what_the_endpoint_sends():
    screens = _screens(_load("registration"))
    for screen_id, fields in REGISTRATION_SCREEN_FIELDS.items():
        declared = set(screens[screen_id].get("data", {}))
        assert set(fields) <= declared, f"{screen_id} does not declare {set(fields) - declared}"


def test_the_register_form_offers_exactly_owner_and_contractor():
    screens = _screens(_load("registration"))
    radio = next(c for c in _components(screens["REGISTER"]) if c.get("name") == "role")
    assert tuple(option["id"] for option in radio["data-source"]) == ("owner", "contractor")


@pytest.mark.parametrize(
    "name, choices",
    [("owner_dashboard", OWNER_MENU_CHOICES), ("contractor_dashboard", CONTRACTOR_MENU_CHOICES)],
)
def test_dashboard_menus_offer_exactly_the_backend_choices(name, choices):
    screens = _screens(_load(name))
    radio = next(c for c in _components(screens["MENU"]) if c.get("name") == "choice")
    assert tuple(option["id"] for option in radio["data-source"]) == choices


@pytest.mark.parametrize("name", ["owner_dashboard", "contractor_dashboard"])
def test_dashboard_flows_have_exactly_the_screens_the_backend_uses(name):
    extra = OWNER_TENDER_SCREENS if name == "owner_dashboard" else CONTRACTOR_TENDER_SCREENS
    expected = DASHBOARD_SCREENS | extra
    assert set(_screens(_load(name))) == expected


def test_splash_banner_is_raw_base64_png_at_banner_size():
    """Meta shows a broken image when the Image src carries a data URI prefix, so the banner is raw base64 PNG."""
    import base64
    import struct

    splash = _screens(_load("registration"))["SPLASH"]
    image = next(child for child in splash["layout"]["children"] if child["type"] == "Image")

    assert not image["src"].startswith("data:")
    raw = base64.b64decode(image["src"], validate=True)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (1200, 480)
    assert image["width"] / image["height"] == pytest.approx(width / height)
    assert image["scale-type"] == "contain"


def _top_level_fields_without_example(data: dict) -> list[str]:
    """Top-level data fields that Meta requires an __example__ for."""
    return [name for name, schema in data.items() if "__example__" not in schema]


def _nested_examples(node: object, path: str = "data") -> list[str]:
    """Nested schemas (array items and their fields). Meta rejects __example__ anywhere but the top level."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "__example__":
                found.append(path)
            found.extend(_nested_examples(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_nested_examples(value, f"{path}[{index}]"))
    return found


@pytest.mark.parametrize("flow_name", FLOWS)
def test_data_examples_are_only_on_top_level_fields(flow_name):
    """Meta requires __example__ on each top-level data field and rejects it on nested schemas."""
    problems = {}
    for screen_id, screen in _screens(_load(flow_name)).items():
        data = screen.get("data", {})
        missing = _top_level_fields_without_example(data)
        nested = []
        for name, schema in data.items():
            nested.extend(_nested_examples(schema.get("items", {}) if schema.get("type") == "array" else {}, f"data.{name}.items"))
            nested.extend(_nested_examples({k: v for k, v in schema.items() if k not in ("__example__", "items")}, f"data.{name}"))
        if missing or nested:
            problems[screen_id] = {"missing": missing, "nested": nested}
    assert problems == {}


def _has_cycle(routing: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> bool:
        if node in done:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        found = any(visit(target) for target in routing.get(node, []))
        visiting.discard(node)
        done.add(node)
        return found

    return any(visit(node) for node in list(routing))


@pytest.mark.parametrize("flow_name", ("owner_dashboard", "contractor_dashboard"))
def test_dashboard_routing_is_forward_only(flow_name):
    """Meta rejects backward routes (A->B where B->A also exists) and loops, so the routing model must be acyclic."""
    flow = _load(flow_name)
    routing = flow["routing_model"]
    screens = set(_screens(flow))

    reverse_pairs = [
        (source, target)
        for source, targets in routing.items()
        for target in targets
        if source in routing.get(target, [])
    ]
    assert reverse_pairs == []
    assert not _has_cycle(routing)
    assert all(source in screens and target in screens for source, targets in routing.items() for target in targets)


def test_review_has_one_publish_button_and_no_choice_to_submit():
    """Meta drops radio values on this screen, so the only action is a fixed Publish now payload."""
    review = _screens(_load("owner_dashboard"))["REVIEW"]
    children = review["layout"]["children"]

    assert not any(child["type"] == "RadioButtonsGroup" for child in children)
    footer = next(child for child in children if child["type"] == "Footer")
    assert footer["label"] == "Publish now"
    assert footer["on-click-action"]["payload"] == {"tender_id": "${data.tender_id}", "option": "publish"}


@pytest.mark.parametrize("flow_name", ("owner_dashboard", "contractor_dashboard"))
def test_form_fields_are_not_named_action(flow_name):
    """Meta drops a form field called 'action', so Continue sends no choice. Choices use 'option' instead."""
    text = (FLOW_DIR / f"{flow_name}.json").read_text(encoding="utf-8")
    assert "${form.action}" not in text
    assert '"name": "action"' not in text

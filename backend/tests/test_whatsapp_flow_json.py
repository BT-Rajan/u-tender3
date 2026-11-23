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

REGISTRATION_SCREENS = {"ROLE", "OWNER_DETAILS", "CONTRACTOR_DETAILS", "SUCCESS", "NOT_COMPLETED", "EXPIRED"}
DASHBOARD_SCREENS = {"MENU", "DOCUMENTS", "LINKS_SENT", "COMING_SOON", "EXPIRED"}
OWNER_TENDER_SCREENS = {"CREATE_TENDER", "REVIEW", "MY_TENDERS", "TENDER_DETAILS", "AMEND", "OFFERS", "DONE"}


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


def test_the_contractor_trade_dropdown_offers_exactly_the_backend_trades():
    screens = _screens(_load("registration"))
    dropdown = next(c for c in _components(screens["CONTRACTOR_DETAILS"]) if c.get("type") == "Dropdown")
    assert tuple(option["id"] for option in dropdown["data-source"]) == TRADE_OPTIONS


def test_registration_language_choices_are_english_and_arabic():
    screens = _screens(_load("registration"))
    radios = [c for c in _components(screens["ROLE"]) if c.get("name") == "language"]
    assert [option["id"] for option in radios[0]["data-source"]] == ["en", "ar"]


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
    expected = DASHBOARD_SCREENS | (OWNER_TENDER_SCREENS if name == "owner_dashboard" else set())
    assert set(_screens(_load(name))) == expected

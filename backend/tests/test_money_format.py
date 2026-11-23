"""Bid amounts: two places when there are no fils, three when there are. Never rounds a fils away."""

import json
from decimal import Decimal

from pydantic import BaseModel

from app.services.money import MoneyAmount, format_amount


class _Bid(BaseModel):
    amount: MoneyAmount


def test_a_whole_dinar_amount_keeps_two_places_as_before():
    assert format_amount(Decimal("5000.000")) == "5000.00"
    assert format_amount(Decimal("5000.00")) == "5000.00"


def test_an_amount_with_fils_keeps_all_three_places():
    assert format_amount(Decimal("12.345")) == "12.345"
    assert format_amount(Decimal("12345.678")) == "12345.678"


def test_grouping_adds_thousands_separators():
    assert format_amount(Decimal("1234567.5"), grouped=True) == "1,234,567.50"
    assert format_amount(Decimal("1234.125"), grouped=True) == "1,234.125"


def test_none_stays_none():
    assert format_amount(None) is None


def test_a_float_is_formatted_from_its_decimal_text():
    assert format_amount(4500.0) == "4500.00"


def test_json_output_uses_the_same_rule():
    assert _Bid(amount=Decimal("5000.000")).model_dump_json() == '{"amount":"5000.00"}'
    assert json.loads(_Bid(amount=Decimal("0.125")).model_dump_json()) == {"amount": "0.125"}


def test_input_accepts_three_decimal_places():
    assert _Bid.model_validate({"amount": "12.345"}).amount == Decimal("12.345")

"""How bid amounts are shown. Amounts are stored to three decimal places (KWD fils).

A bid without fils is shown with two places, as before, so 5000.000 reads 5000.00.
A bid with fils keeps all three, so 12.345 is not rounded to 12.35.
"""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import PlainSerializer

TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")


def format_amount(value: Decimal | int | float | str | None, *, grouped: bool = False) -> str | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    if amount == amount.quantize(TWO_PLACES):
        places, quantum = 2, TWO_PLACES
    else:
        places, quantum = 3, THREE_PLACES
    rounded = amount.quantize(quantum)
    return f"{rounded:,.{places}f}" if grouped else f"{rounded:.{places}f}"


def _serialize(value: Any) -> str | None:
    return format_amount(value)


MoneyAmount = Annotated[Decimal, PlainSerializer(_serialize, return_type=str, when_used="json")]

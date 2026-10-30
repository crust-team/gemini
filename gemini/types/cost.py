"""Cost estimates with explicit valuation basis and source."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.errors import ValidationError
from gemini.types.quantities import AnnualMoney, Money, MoneyPerEnergy


class Cost(BaseModel):
    """Investment, annual fixed cost and variable cost per joule of useful output."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    capex: Money = 0
    opex_fixed: AnnualMoney = 0
    opex_variable: MoneyPerEnergy = 0
    currency: str = Field("EUR", min_length=1)
    price_year: int = Field(ge=1)
    source: str = Field(min_length=1)


def total_cost(module):
    """Sum the costs that a module and its descendants declare through a ``capex()`` method.

    A module declares its own capital and operating cost by defining ``capex()`` returning a
    ``Cost``; a composite's ``capex`` describes only its own addition, never its children's.
    Returns ``None`` when no module declares a cost, and refuses to add costs valued in different
    currencies or price years.
    """
    costs = [cost for item in module.modules() if (cost := _own_cost(item)) is not None]
    if not costs:
        return None
    first = costs[0]
    if any((c.currency, c.price_year) != (first.currency, first.price_year) for c in costs):
        raise ValidationError(
            f"{module.path}: costs require the same currency and price year; got "
            f"{sorted({(c.currency, c.price_year) for c in costs})}",
            code="invalid_design",
        )
    return Cost(
        capex=sum(c.capex for c in costs),
        opex_fixed=sum(c.opex_fixed for c in costs),
        opex_variable=sum(c.opex_variable for c in costs),
        currency=first.currency,
        price_year=first.price_year,
        source="; ".join(dict.fromkeys(c.source for c in costs)),
    )


def _own_cost(module):
    """Return the cost a module declares itself, or ``None``."""
    capex = getattr(module, "capex", None)
    return capex() if capex is not None else None

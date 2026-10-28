"""Cost estimates with explicit valuation basis and source."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.types.quantities import AnnualMoney, Money, MoneyPerEnergy


class Cost(BaseModel):
    """Investment, annual fixed cost and variable cost per joule of useful output."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    capex: Money = 0
    opex_fixed: AnnualMoney = 0
    opex_variable: MoneyPerEnergy = 0
    currency: str = Field("EUR", min_length=1)
    price_year: int = Field(ge=1)
    source: str = Field(min_length=1)

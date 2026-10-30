"""The economic assumptions of an assessment, each with its source or left for the user."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.errors import ValidationError


class Assumptions(BaseModel):
    """Discount rate, lifetime, energy prices and emission factors of one assessment.

    Every field is ``None`` until the user gives it, except the two below that have a source.
    No price, rate or lifetime has a default, because none is valid everywhere: they depend on
    the country, the year, the contract and the project. Money is in ``currency`` and energy in
    J, as everywhere in GEMINI; convert at the boundary (EUR/MWh divided by 3.6e9 is EUR/J,
    kg/GJ divided by 1e9 is kg/J).

    Defaults with a source:

    - ``fuel_emission_factor`` = 56.1e-9 kg/J (56.1 kg CO2 per GJ of fuel energy): the
      IPCC default for natural gas, 56 100 kg/TJ on the net calorific value, in the 2006 IPCC
      Guidelines for National Greenhouse Gas Inventories, volume 2 (Energy), chapter 2, table
      2.2. It is the factor of natural gas only: give another for oil, biomass or a blend.
    - ``currency`` = ``"EUR"``: a label, the currency of the prices you give and of the
      ``Cost`` default; it is not a price.

    Attributes
    ----------
    currency : str
        Currency of every price and result.
    discount_rate : float or None
        Real discount rate per year [-], for example 0.05.
    lifetime_years : int or None
        Years of operation that the levelised cost and the net present value cover.
    electricity_price, fuel_price : float or None
        Price of purchased electricity and of fuel [currency/J of energy].
    heat_price, cold_price : float or None
        Revenue per joule of heat or cold delivered [currency/J].
    electricity_emission_factor : float or None
        CO2 emitted per joule of grid electricity drawn [kg/J]; it depends on the grid and the
        year, so there is no default.
    fuel_emission_factor : float
        CO2 emitted per joule of fuel burnt [kg/J].
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    currency: str = Field("EUR", min_length=1)
    discount_rate: float | None = Field(None, ge=0)
    lifetime_years: int | None = Field(None, ge=1)
    electricity_price: float | None = Field(None, ge=0)
    fuel_price: float | None = Field(None, ge=0)
    heat_price: float | None = Field(None, ge=0)
    cold_price: float | None = Field(None, ge=0)
    electricity_emission_factor: float | None = Field(None, ge=0)
    fuel_emission_factor: float = Field(56.1e-9, ge=0)


def resolve(assumptions):
    """Return ``assumptions``, or the sourced defaults when it is ``None``."""
    if assumptions is None:
        return Assumptions()
    if not isinstance(assumptions, Assumptions):
        raise ValidationError(
            f"assumptions = {assumptions!r}; expected an Assumptions or None", path="assumptions"
        )
    return assumptions


def require(assumptions, name):
    """Return the assumption ``name``, or raise ``ValidationError`` saying the user must give it."""
    value = getattr(assumptions, name)
    if value is None:
        raise ValidationError(
            f"assumptions.{name} is None; expected a value from the user (it has no default)",
            path=f"assumptions.{name}",
            code="missing_value",
        )
    return value


def discounting(assumptions, discount_rate, lifetime):
    """Return ``(rate, years)``: the explicit arguments, else those of ``assumptions``.

    A value given nowhere raises ``ValidationError`` (code ``missing_value``); a negative rate or
    a lifetime under one year raises ``ValidationError``.
    """
    rate = discount_rate if discount_rate is not None else require(assumptions, "discount_rate")
    years = lifetime if lifetime is not None else require(assumptions, "lifetime_years")
    if rate < 0:
        raise ValidationError(
            f"discount_rate = {rate}; expected a rate of 0 or more", path="discount_rate"
        )
    if years < 1:
        raise ValidationError(f"lifetime = {years}; expected 1 year or more", path="lifetime")
    return rate, years

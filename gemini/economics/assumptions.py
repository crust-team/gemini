"""The economic assumptions of an assessment, each with its source or left for the user."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.errors import ValidationError

COST_SOURCES = {
    "drilling_cost": "SDE+ 2013 reference case, 2300 m doublet, 5.7 MEUR net drilling (Mijnlieff "
    "et al. 2013, EGC, Geothermal energy and support schemes in the Netherlands, slide 26), over "
    "two wells of 2300 m",
    "degasser_cost": "SDE+ 2013 reference case, 1.0 MEUR reserve for separation of hydrocarbons "
    "per doublet (Mijnlieff et al. 2013, EGC, slide 26)",
    "heat_pump_cost": "Danish Energy Agency, Technology Data for Energy Plants, April 2020, "
    "chapter 40, compression heat pump, excess heat, 10 MW, 2020, 2015 prices",
    "boiler_cost": "Danish Energy Agency, Technology Data for Energy Plants, April 2020, chapter "
    "44, district heating boiler, natural gas, 2020, 2015 prices",
    "chp_cost": "Danish Energy Agency, Technology Data for Energy Plants, April 2020, chapter 06, "
    "spark ignition engine, natural gas, 1-10 MWe, 2020, 2015 prices",
}
"""The source of each cost factor with a default; a factor the user gives is theirs."""


class Assumptions(BaseModel):
    """Discount rate, lifetime, energy prices and emission factors of one assessment.

    Every field is ``None`` until the user gives it, except those below that have a source.
    No price, rate or lifetime has a default, because none is valid everywhere: they depend on
    the country, the year, the contract and the project. Money is in ``currency`` and energy in
    J, as everywhere in GEMINI; convert at the boundary (EUR/MWh divided by 3.6e9 is EUR/J,
    kg/GJ divided by 1e9 is kg/J). ``gas_price`` is the one price per MWh.

    Defaults with a source:

    - ``methane_gwp`` = 29.8 kg CO2-eq per kg of fossil methane over 100 years: IPCC Sixth
      Assessment Report, Working Group I, chapter 7, table 7.15 (Forster et al. 2021).
    - ``currency`` = ``"EUR"``: a label, the currency of the prices you give and of the
      ``Cost`` default; it is not a price.
    - the cost factors of ``COST_SOURCES``, each with its source there. They are valued in
      ``cost_price_year`` = 2015, the prices of the Danish Energy Agency catalogue.
      NOTE(refactor): the two factors of the SDE+ 2013 reference case are 2013 figures, taken into
      that price year without escalation, because ``total_cost`` adds costs of one price year.

    The other cost factors have no value, because no source was found: ``chiller_cost``,
    ``exchanger_cost``, ``pump_cost``, ``flare_cost`` and ``makeup_cost``. Using one raises
    ``ValidationError`` (code ``missing_assumption``). See ``economics.md``.

    Attributes
    ----------
    currency : str
        Currency of every price and result.
    discount_rate : float or None
        Real discount rate per year [-], for example 0.05.
    lifetime_years : int or None
        Years of operation that the levelised cost and the net present value cover.
    electricity_price : float or None
        Price of purchased electricity [currency/J of energy].
    gas_price : float or None
        Price of purchased gas [currency/MWh of fuel energy]; co-produced gas costs nothing.
    heat_price, cold_price : float or None
        Revenue per joule of heat or cold delivered [currency/J].
    electricity_emission_factor : float or None
        CO2 emitted per joule of grid electricity drawn [kg/J]; it depends on the grid and the
        year, so there is no default.
    methane_gwp : float
        CO2-equivalent of a kilogram of methane released [-].
    heat_cost_share : float or None
        Share of the plant cost charged to heat when a plant delivers heat and cold [-]; the rest
        is charged to cold. Without it such a plant has no levelised cost.
    cost_price_year : int
        Price year of the cost factors.
    drilling_cost : float or None
        Drilling [currency per metre of well].
    pump_cost : float or None
        Production pump [currency/W of shaft power at the nominal flow].
    heat_pump_cost, boiler_cost, chiller_cost : float or None
        Equipment [currency/W of capacity]; ``chp_cost`` per W of electric capacity.
    exchanger_cost : float or None
        Heat exchanger [currency per W/K of thermal conductance].
    degasser_cost, flare_cost, makeup_cost : float or None
        Fixed items [currency].
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    currency: str = Field("EUR", min_length=1)
    discount_rate: float | None = Field(None, ge=0)
    lifetime_years: int | None = Field(None, ge=1)
    electricity_price: float | None = Field(None, ge=0)
    gas_price: float | None = Field(None, ge=0)
    heat_price: float | None = Field(None, ge=0)
    cold_price: float | None = Field(None, ge=0)
    electricity_emission_factor: float | None = Field(None, ge=0)
    methane_gwp: float = Field(29.8, ge=0)
    heat_cost_share: float | None = Field(None, ge=0, le=1)
    cost_price_year: int = Field(2015, ge=1)
    drilling_cost: float | None = Field(5.7e6 / (2 * 2300), ge=0)
    pump_cost: float | None = Field(None, ge=0)
    heat_pump_cost: float | None = Field(0.67, ge=0)
    boiler_cost: float | None = Field(0.06, ge=0)
    chp_cost: float | None = Field(0.95, ge=0)
    chiller_cost: float | None = Field(None, ge=0)
    exchanger_cost: float | None = Field(None, ge=0)
    degasser_cost: float | None = Field(1.0e6, ge=0)
    flare_cost: float | None = Field(None, ge=0)
    makeup_cost: float | None = Field(None, ge=0)

    def factor(self, name):
        """Return the cost factor ``name``, or raise ``missing_assumption`` naming it."""
        return require(self, name)

    def source_of(self, name):
        """Return the source of the cost factor ``name``; a factor changed by the user is theirs."""
        if getattr(self, name) == type(self).model_fields[name].default:
            return COST_SOURCES[name]
        return f"assumptions.{name}"


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
            code="missing_assumption",
        )
    return value


def discounting(assumptions, discount_rate, lifetime):
    """Return ``(rate, years)``: the explicit arguments, else those of ``assumptions``.

    A value given nowhere raises ``ValidationError`` (code ``missing_assumption``); a negative rate
    or a lifetime under one year raises ``ValidationError``.
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

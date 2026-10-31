"""The economic assumptions of a problem, each with its source or left for the user."""

import numpy as np
import pydantic
from pydantic import BaseModel, ConfigDict, Field

from gemini import units
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import ValidationError

CARRIERS = {
    "electricity": "currency/J",
    "gas": "currency/J",
    "heat": "currency/J",
    "cold": "currency/J",
    "waste_disposal": "currency/kg",
    "chemical": "currency/kg",
}
"""What has a price, with the SI unit of the price: energy per J, the rest per kg."""
CO2_UNIT = "currency/kg"
"""The SI unit of ``co2_price``."""
FIELD_CODES = {
    "extra_forbidden": "unknown_name",
    "greater_than_equal": "out_of_bounds",
    "less_than_equal": "out_of_bounds",
}
"""The code of what pydantic refuses; anything else is ``invalid_value``."""

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
    """Discount rate, lifetime, prices and emission factors of one problem.

    Every field is ``None`` until the user gives it, except those below that have a source.
    No price, rate or lifetime has a default, because none is valid everywhere: they depend on
    the country, the year, the contract and the project. Money is in ``currency`` and energy in
    J, as everywhere in GEMINI; a text states its unit, with the currency in it
    (``"100 EUR/MWh"``). Invalid values raise ``ValidationError``.

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
    prices : dict
        ``{carrier: price}``, a carrier being a name of ``CARRIERS``. A price is a number in SI, a
        text with its unit, or a profile on the demand index: a list of numbers in SI, or
        ``{"unit": ..., "values": [...]}``. ``electricity`` is what the grid sells, ``gas`` what
        the gas grid sells (co-produced gas costs nothing), ``heat`` and ``cold`` the revenue per
        joule delivered, ``waste_disposal`` the cost of a kilogram at a ``WasteGrid`` and
        ``chemical`` of a kilogram from a ``ChemicalGrid``.
    co2_price : float or str or None
        Cost of a kilogram of CO2-equivalent emitted [currency/kg], or a text with its unit.
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
    prices: dict[str, float | str | list[float] | dict] = Field(default_factory=dict)
    co2_price: float | str | None = None
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

    def __init__(self, **data):
        """Validate the fields, then the prices; every failure is a ``ValidationError``."""
        try:
            super().__init__(**data)
        except pydantic.ValidationError as error:
            first = error.errors()[0]
            raise ValidationError(
                f"assumptions.{first['loc'][0]}: {first['msg']}",
                path=f"assumptions.{first['loc'][0]}",
                code=FIELD_CODES.get(first["type"], "invalid_value"),
            ) from error
        for carrier in self.prices:
            self.price(carrier, required=False)
        if self.co2_price is not None:
            _in_si(self.co2_price, CO2_UNIT, self.currency, "assumptions.co2_price")

    @classmethod
    def from_dict(cls, data):
        """Return the assumptions of a dictionary of ``to_dict``."""
        return cls(**data)

    def to_dict(self):
        """Return what differs from the defaults, as plain data."""
        return self.model_dump(exclude_defaults=True)

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``to_dict``."""
        return cls.model_json_schema()

    def price(self, carrier, required=True):
        """Return the price of ``carrier`` in SI, a number or an array along the demand.

        A carrier nobody priced raises ``ValidationError`` (code ``missing_assumption``) naming it,
        or gives ``None`` with ``required=False``.
        """
        if carrier not in CARRIERS:
            raise ValidationError(
                f"assumptions.prices: carrier = {carrier!r}; expected one of "
                f"{join_names(CARRIERS)}{did_you_mean(carrier, CARRIERS)}",
                path=f"assumptions.prices.{carrier}",
                suggestions=close_matches(carrier, CARRIERS),
                code="unknown_name",
            )
        path = f"assumptions.prices.{carrier}"
        if carrier in self.prices:
            return _in_si(self.prices[carrier], CARRIERS[carrier], self.currency, path)
        if required:
            raise ValidationError(
                f"{path} is missing; expected a value from the user (it has no default)",
                path=path,
                code="missing_assumption",
            )
        return None

    def co2_cost(self):
        """Return ``co2_price`` in SI [currency/kg], or ``None`` when nobody gave it."""
        if self.co2_price is None:
            return None
        return _in_si(self.co2_price, CO2_UNIT, self.currency, "assumptions.co2_price")

    def factor(self, name):
        """Return the cost factor ``name``, or raise ``missing_assumption`` naming it."""
        return require(self, name)

    def source_of(self, name):
        """Return the source of the cost factor ``name``; a factor changed by the user is theirs."""
        if getattr(self, name) == type(self).model_fields[name].default:
            return COST_SOURCES[name]
        return f"assumptions.{name}"


def _in_si(price, unit, currency, path):
    """Return ``price``, a number, a text with its unit or a profile, in the SI ``unit``."""
    if isinstance(price, str):
        number, given = units.parse(price.replace(currency, "currency"))
        return number * _scale(given, unit, path)
    if isinstance(price, dict):
        given = str(price.get("unit")).replace(currency, "currency")
        return np.array(price.get("values", []), dtype=float) * _scale(given, unit, path)
    if isinstance(price, list):
        return np.array(price, dtype=float)
    return price


def _scale(given, unit, path):
    """Return what turns a number in the unit ``given`` into ``unit``, or raise ``invalid_unit``."""
    if units.si_unit(given) != unit:
        raise ValidationError(
            f"{path}: unit = {given!r}; expected a unit of {unit!r}", path=path, code="invalid_unit"
        )
    return units.convert(1.0, given, unit)


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

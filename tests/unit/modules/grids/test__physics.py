"""Grid connection exchange."""

import pytest

from gemini.modules.grids import _physics
from tests.fixtures.equivalence import assert_function_matches


def test_import_is_limited():
    """A 100 W deficit through a 60 W import limit leaves 40 W unserved."""
    exchange = _physics.net_exchange(300, 200, 60, None)
    assert exchange.net_import == 60
    assert exchange.net_export == 0
    assert exchange.unserved_consumption == pytest.approx(40)


def test_surplus_is_curtailed_above_the_export_limit():
    """A 50 W surplus through a 30 W export limit curtails 20 W."""
    exchange = _physics.net_exchange(100, 150, None, 30)
    assert (exchange.net_export, exchange.curtailed_generation) == (30, pytest.approx(20))


def test_rows_match_arrays():
    """Rows across import, export and balance agree with the traced run."""
    rows = [(300.0, 200.0), (100.0, 150.0), (50.0, 50.0)]
    assert_function_matches(
        _physics.net_exchange,
        rows,
        import_limit=60.0,
        export_limit=None,
    )

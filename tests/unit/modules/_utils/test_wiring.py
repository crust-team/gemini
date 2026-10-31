"""Stream-identity wiring traces leaf-to-leaf transfers and always removes its hooks."""

import gemini as gm
from gemini.modules import Filter, Module
from gemini.modules._utils.wiring import trace_wiring
from gemini.types import Inlet, Outlet, Stream
from tests.fixtures.errors import raises

STREAM = Stream(m_dot=10, T=330, p=1e6)


class Train(Module):
    """Two filters in series."""

    def __init__(self):
        """Declare both filters and the train ports."""
        super().__init__()

        # Modules
        self.first = Filter()
        self.second = Filter()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream through both filters."""

        # Modules
        first = self.first(inlet=inlets.inlet)
        second = self.second(inlet=first.outlets.outlet)

        # Outlets
        outlet = second.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def hook_counts(plant):
    """Return the number of hooks on every module."""
    return [(len(module._hooks), len(module._pre_hooks)) for module in plant.modules()]


def test_trace_reports_leaf_to_leaf_edges():
    """The second filter consumes exactly the stream the first produced."""
    assert trace_wiring(Train(), {"inlet": STREAM}) == {("first", "outlet", "second", "inlet")}


def test_trace_removes_its_hooks_after_a_failure():
    """A failing call leaves no observers behind."""
    plant = Train()
    before = hook_counts(plant)
    with raises(gm.errors.ValidationError, "invalid_call", match="missing required inlet"):
        trace_wiring(plant, {})
    assert hook_counts(plant) == before

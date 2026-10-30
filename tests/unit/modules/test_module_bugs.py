"""Regression tests for base-class bugs found in the cleanup audit (E-modules-*)."""

import pytest

import gemini as gm
from gemini.modules import Filter, Module, ProductionReservoir
from gemini.types import Control, Inlet, Outlet, Output, Parameter, Power, Stream

STREAM = Stream(m_dot=10, T=330, p=1e6)


def define_module():
    """Define a fresh module class each call, as a notebook cell or a factory does."""

    class Repeated(Module):
        """Pass-through defined anew by every call."""

        def __init__(self):
            super().__init__()

            # Inlets
            self.inlet = Inlet(Stream)

            # Outlets
            self.outlet = Outlet(Stream)

        def forward(self, inlets):
            """Return the inlet."""

            # Outlets
            outlet = inlets.inlet

            outlets = dict(outlet=outlet)
            return outlets

    return Repeated


def test_redefining_a_module_class_works():
    """E-modules-001: a second definition with the same name no longer collides."""
    first, second = define_module(), define_module()
    assert first is not second
    assert second()(STREAM).outlets.outlet == STREAM


def test_user_class_may_reuse_a_builtin_name():
    """E-modules-001: a user class called ``Filter`` does not clash with the built-in one."""

    class Filter(Module):
        """User filter with the same class name as the built-in."""

    assert Filter().name == "filter"


def test_subclass_of_a_concrete_module_may_add_declarations():
    """E-modules-002: declarations after ``super().__init__()`` register in a subclass."""

    class ScoredFilter(Filter):
        """Filter with one extra design parameter."""

        def __init__(self):
            super().__init__()

            # Parameters
            self.score = Parameter(float, default=1.0)

    module = ScoredFilter()
    assert "score" in dict(module.named_parameters())
    assert module(inlet=STREAM).outputs.pressure_drop >= 0


def test_missing_super_init_is_explicit():
    """A subclass that forgets ``super().__init__()`` fails at its first declaration."""

    class Broken(Module):
        """Forgets the base initialiser."""

        def __init__(self):
            self.value = Parameter(float)

    with pytest.raises(gm.errors.DeclarationError, match="super"):
        Broken()


def test_assigned_fluid_survives_parameter_changes_and_is_saved():
    """E-modules-003: ``module.fluid = ...`` is not reverted and ``state_dict`` stores it."""
    module = Filter()
    module.fluid = gm.WATER
    module.dp_nominal = 1000
    assert module.fluid == gm.WATER
    assert Filter().load_state_dict(module.state_dict()).fluid == gm.WATER


def test_dotted_parameter_update_refreshes_descendant_fluid(fresh_plant):
    """E-modules-004: a reservoir density override applies as soon as it is set."""
    fresh_plant.update_params(**{"doublet.reservoir.liquid_density": 1100})
    assert fresh_plant.doublet.reservoir.fluid.liquid_density == 1100


class Child(Module):
    """Leaf whose forward hook reads its parent's control."""

    def __init__(self):
        """Declare the fixture ports and outputs."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Return the inlet."""

        # Outlets
        outlet = inlets.inlet

        outlets = dict(outlet=outlet)
        return outlets


class Parent(Module):
    """Composite with a control its child's hook reads."""

    def __init__(self):
        """Declare the fixture ports and outputs."""
        super().__init__()

        # Modules
        self.child = Child()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.setting = Control(float, default=1.0)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream through the child."""

        # Modules
        result = self.child(inlet=inlets.inlet)

        # Outlets
        outlet = result.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def test_child_hook_reads_the_parent_call_value():
    """E-modules-005: inside a nested call the parent's control has its call value."""
    parent, seen = Parent(), []

    def observe(module, inlets, outlets):
        seen.append(parent.setting)

    parent.child.register_forward_hook(observe)
    parent(inlet=STREAM, setting=5.0)
    assert seen == [5.0]
    assert parent.setting == 1.0


class Meter(Module):
    """Leaf whose optional reading is missing."""

    def __init__(self):
        """Declare the fixture ports and outputs."""
        super().__init__()

        # Outputs
        self.reading = Output(Power | None)
        self.power = Output(Power)

    def forward(self, inlets):
        """Produce no stream."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.reading = None
        self.power = 2.0


class Share(Module):
    """Composite dividing an optional reading by a power."""

    def __init__(self):
        """Declare the fixture ports and outputs."""
        super().__init__()

        # Modules
        self.meter = Meter()

        # Outputs
        self.reading = Output.of(self.meter.reading)
        self.power = Output.of(self.meter.power)
        self.share = Output.ratio(self.reading, self.power)

    def forward(self, inlets):
        """Call the meter once."""

        # Modules
        self.meter()

        outlets = dict()
        return outlets


def test_ratio_with_a_missing_operand_is_none():
    """E-modules-010: ``Output.ratio`` gives ``None`` when an operand is ``None``."""
    assert Share()().outputs.share is None


def test_composite_step_refuses_stateful_descendants():
    """E-modules-009: a stateless composite cannot silently skip its stateful children."""

    class Tank(Child):
        """Stateful leaf."""

        stateful = True

    parent = Parent()
    parent.child = Tank()
    with pytest.raises(gm.errors.ConfigurationError, match="child"):
        parent.step(None, 900.0, {"inlet": STREAM})


def test_injection_reservoir_without_injectivity_fails_in_forward():
    """E-modules-019: a missing injectivity index fails even when outputs are skipped."""
    reservoir = gm.modules.InjectionReservoir().update_params(
        pressure=2e7,
        temperature=350,
        permeability=1e-13,
        thickness=100,
        drainage_radius=0,
        top_depth=2000,
        wellbore_radius=0.1,
    )
    with gm.no_outputs(), pytest.raises(gm.errors.ConfigurationError, match="injectivity"):
        reservoir(sandface=STREAM)


def test_reservoir_health_without_design_index_is_not_assessed():
    """E-modules-011: a missing productivity index means not assessed, not a crash."""
    reservoir = ProductionReservoir()
    reservoir.update_params(pressure=2e7, temperature=350)
    assert reservoir.health(None, {"flow": 0.04, "bottomhole_pressure": 1.9e7}) is None

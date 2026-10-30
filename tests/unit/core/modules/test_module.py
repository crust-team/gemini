"""Registration, calls, state and output-recording contracts."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import gemini as gm
from gemini.core.modules import Module, ModuleDict
from gemini.core.types import (
    Boundary,
    Control,
    Electricity,
    Frequency,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Ports,
    Power,
    Stream,
)


class PassThrough(Module):
    """Contract fixture passing an inlet stream through unchanged."""

    def __init__(self):
        """Declare a minimal module used across registration tests."""
        super().__init__()

        # Parameters
        self.value = Parameter(float, gt=0, calibratable=True)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.multiplier = Control(float, default=1, gt=0)

        # Outputs
        self.result = Output(float, soft_sensor=True)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Record the scalar product and return the stream."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.result = self.value * self.multiplier


def test_registration_construction_and_state():
    """Keyword values fill registered declarations and state reload is atomic."""
    module = PassThrough().update_params(value=2)
    assert module.value == 2
    assert dict(module.named_parameters()) == {"value": module.get_parameter("value")}
    assert module.calibratable_parameters() == [module.get_parameter("value")]
    module.value = 3
    assert module.value == 3
    state = module.state_dict()
    module.value = 4
    module.load_state_dict(state)
    assert module.value == 3
    with pytest.raises(TypeError):
        module.value = -1


def test_call_output_and_signature_guards():
    """All supported inlet call forms resolve to the same fixed Ports shape."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)
    results = [
        module(inlet=stream, multiplier=4),
        module({"inlet": stream}, multiplier=4),
        module(Ports({"inlet": stream}), multiplier=4),
        module(stream, multiplier=4),
    ]
    assert [result.outputs.result for result in results] == [8, 8, 8, 8]
    assert all(result.outlets.outlet is stream for result in results)
    assert all(isinstance(result.inlets, Ports) for result in results)
    assert all(isinstance(result.outlets, Ports) for result in results)
    assert module.result.soft_sensor

    with pytest.raises(
        gm.errors.CallError, match="pass_through.*missing.*inlet.*valid names: inlet"
    ):
        module()
    with pytest.raises(
        gm.errors.CallError, match="pass_through.*inlett.*valid names.*did you mean 'inlet'"
    ):
        module(inlett=stream)
    with pytest.raises(
        gm.errors.CallError, match="pass_through.*cannot mix.*inlet.*valid names: inlet"
    ):
        module({"inlet": stream}, inlet=stream)
    with pytest.raises(
        gm.errors.CallError, match="pass_through.*invalid inlet 'inlet'.*valid names: inlet"
    ):
        module(inlet=1)
    with pytest.raises(
        gm.errors.CallError, match="pass_through.*multiple values.*inlet.*valid names"
    ):
        module(stream, inlet=stream)


def test_outlet_dict_names_and_flow_types_are_checked(monkeypatch):
    """Forward returns exactly one declared, correctly typed outlet dictionary."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)

    def scalar_forward(inlets):
        return inlets.inlet

    monkeypatch.setattr(module, "forward", scalar_forward)
    with pytest.raises(gm.errors.OutletError, match="outlet dict"):
        module(inlet=stream)

    monkeypatch.setattr(module, "forward", lambda inlets: {})
    with pytest.raises(gm.errors.OutletError, match=r"pass_through.*missing=\['outlet'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": stream, "extra": stream})
    with pytest.raises(gm.errors.OutletError, match=r"pass_through.*extra=\['extra'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": 1})
    with pytest.raises(
        gm.errors.OutletError, match="pass_through.*invalid outlet 'outlet'.*valid names"
    ):
        module(inlet=stream)


class NestedParent(Module):
    """Nested-call fixture copying its child's recorded output."""

    def __init__(self):
        """Declare one child inside a container and a copied output."""
        super().__init__()

        # Modules
        self.children_by_name = ModuleDict({"child": PassThrough().update_params(value=3)})

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.child_value = Output.of("children_by_name.child.result")

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Call the child and copy its recorded output."""

        # Modules
        child = self.children_by_name.child(inlet=inlets.inlet, multiplier=2)

        # Outlets
        outlet = child.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def test_output_records_are_thread_local():
    """Concurrent evaluations never share output records."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda value: module(inlet=stream, multiplier=value), range(1, 9)))
    assert [result.outputs.result for result in values] == [2 * value for value in range(1, 9)]
    assert module.result.soft_sensor


def test_output_records_are_nested_per_call():
    """A child's call inside its parent keeps its own inputs and outputs."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    result = NestedParent()(inlet=stream)
    assert result.outputs.child_value == 6
    assert result.children["children_by_name.child"].outputs.result == 6
    assert NestedParent().children_by_name.child(inlet=stream).outputs.result == 3


def test_uninitialized_and_hooks():
    """Uninitialized parameters and hook ordering have clear behavior."""
    module = PassThrough()
    assert module.missing_parameters() == ["value"]
    with pytest.raises(gm.errors.MissingValueError, match="uninitialized"):
        module(inlet=Stream(m_dot=1, T=300, p=1e5))
    module.value = 2
    calls = []
    before = module.register_forward_pre_hook(lambda module, inlets: calls.append("before"))
    after = module.register_forward_hook(lambda module, inlets, outlets: calls.append("after"))
    module(inlet=Stream(m_dot=1, T=300, p=1e5))
    assert calls == ["before", "after"]
    before.remove()
    after.remove()


class RequiredInputs(Module):
    """Fixture with required unit-bearing control and boundary values."""

    def __init__(self):
        """Declare one inlet, required control, required boundary and result."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency, gt=0, le=60)

        # Boundaries
        self.grid_frequency = Boundary(Frequency)

        # Outputs
        self.total = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Read applied values through ordinary attributes."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.total = self.frequency + self.grid_frequency


def test_input_resolution_units_bounds_and_metadata():
    """Per-call, persistent and default values resolve in order and validate as SI."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = RequiredInputs()
    module.frequency = "40 Hz"
    module.grid_frequency = 50
    assert module.get_control("frequency").unit == "Hz"
    assert module.get_boundary("grid_frequency").unit == "Hz"
    assert module(inlet=stream).outputs.total == 90
    assert module(inlet=stream, frequency="45 Hz").outputs.total == 95
    assert module.frequency == 40
    with pytest.raises(TypeError, match="frequency.*invalid control.*Hz"):
        module.frequency = "61 Hz"


def test_missing_input_and_unknown_keyword_errors_are_complete():
    """Missing and unknown values report path, kind, unit and valid names before forward."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = RequiredInputs()
    with pytest.raises(gm.errors.MissingValueError, match="required_inputs.frequency.*control.*Hz"):
        module(inlet=stream)
    module.frequency = 50
    with pytest.raises(
        gm.errors.MissingValueError, match="required_inputs.grid_frequency.*boundary.*Hz"
    ):
        module(inlet=stream)
    with pytest.raises(gm.errors.CallError, match="valid names"):
        module(inlet=stream, typo=1)


def test_call_inputs_and_hook_assignments_do_not_leak():
    """Context-local values survive nesting and pre-hook changes last for one call only."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = RequiredInputs()
    module.set_inputs({"frequency": 50, "grid_frequency": 50})
    seen = []

    def clamp(module, inlets):
        current = module
        seen.append(current.frequency)
        current.frequency = min(current.frequency, 45)

    handle = module.register_forward_pre_hook(clamp)
    assert module(inlet=stream).outputs.total == 95
    handle.remove()
    assert module.frequency == 50
    assert module(inlet=stream).outputs.total == 100
    assert seen == [50]

    class AssignInForward(RequiredInputs):
        """Fixture changing a control from inside its active forward context."""

        def forward(self, inlets):
            """Override frequency for only the current call."""

            # Outlets
            inlet = inlets.inlet
            outlet = inlet

            outlets = dict(outlet=outlet)
            return outlets

        def _compute_outputs(self, inlets, outlets):
            self.frequency = 10
            self.total = self.frequency + self.grid_frequency

    assigned = AssignInForward()
    assigned.set_inputs({"frequency": 50, "grid_frequency": 50})
    assert assigned(inlet=stream).outputs.total == 60
    assert assigned.frequency == 50


def test_hooks_are_ordered_removable_and_observe_named_ports():
    """Hooks use named ports, preserve outlets and ignore their return value."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    replacement = stream.with_(p=2e5)
    module = PassThrough().update_params(value=2)
    calls = []

    def first_hook(module, inlets):
        calls.append(("first", module))

    def second_hook(module, inlets):
        calls.append(("second", module))

    first = module.register_forward_pre_hook(first_hook)
    second = module.register_forward_pre_hook(second_hook)

    def observe(module, inlets, outlets):
        calls.append(("post", module))
        return {"outlet": replacement}

    post = module.register_forward_hook(observe)
    result = module(inlet=stream)
    assert [name for name, _ in calls] == ["first", "second", "post"]
    assert result.outlets.outlet is stream
    second.remove()
    post.remove()
    first.remove()
    assert module(inlet=stream).outlets.outlet is stream
    state = module.state_dict()
    restored = PassThrough().update_params(value=1).load_state_dict(state)
    assert not restored._pre_hooks and not restored._hooks


def test_set_inputs_uses_recursive_paths_and_suggests_mistakes():
    """Plant-wide input setting addresses leaf declarations and validates atomically."""

    class ParentInputs(Module):
        """Own one child solely to test relative input paths."""

        def __init__(self):
            """Register the child input fixture."""
            super().__init__()

            # Modules
            self.child = RequiredInputs()

        def forward(self, inlets):
            """Return no outlets for the structural fixture."""

            # Modules
            self.child(
                inlet=Stream(m_dot=1, T=300, p=1e5),
            )

            outlets = dict()
            return outlets

    parent = ParentInputs()
    parent.set_inputs({"child.frequency": "50 Hz", "child.grid_frequency": 50})
    assert parent().children["child"].outputs.total == 100
    with pytest.raises(gm.errors.UnknownNameError, match="did you mean 'child.frequency'"):
        parent.set_inputs({"child.frequncy": 40})


def test_hooks_require_the_fixed_signatures():
    """Hook registration rejects old by-name, variadic and defaulted signatures."""
    module = PassThrough().update_params(value=1)

    with pytest.raises(gm.errors.DeclarationError, match="forward hook.*module, inlets, outlets"):
        module.register_forward_hook(lambda module, inlet, outlet: None)
    with pytest.raises(gm.errors.DeclarationError, match="forward pre-hook.*module, inlets"):
        module.register_forward_pre_hook(lambda module: None)

    def defaulted(module, inlets, outlets=None):
        pass

    with pytest.raises(gm.errors.DeclarationError, match="forward hook.*module, inlets, outlets"):
        module.register_forward_hook(defaulted)


def test_missing_output_and_named_hook_ordering():
    """Checks run after output computation and named hooks observe completed values."""

    class MissingOutput(Module):
        """Leave one declared output unset."""

        def __init__(self):
            super().__init__()
            self.inlet = Inlet(Stream)
            self.value = Output(float)
            self.outlet = Outlet(Stream)

        def forward(self, inlets):
            outlets = dict(outlet=inlets.inlet)
            return outlets

        def _compute_outputs(self, inlets, outlets):
            pass

    stream = Stream(m_dot=1, T=300, p=1e5)
    module = MissingOutput()
    with pytest.raises(gm.errors.OutputError, match="missing_output.*value"):
        module(inlet=stream)

    good = PassThrough().update_params(value=3)
    seen = []

    def observe(module, inlets, outlets):
        seen.append((module.result, inlets.inlet, outlets.outlet))

    good.register_forward_hook(observe)
    good(inlet=stream, multiplier=2)
    assert seen == [(6, stream, stream)]


def test_no_outputs_is_nested_thread_local_context_and_decorator():
    """The fast path skips output callbacks, formulas, hooks and output checks."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)
    calls = []

    def observe(module, inlets, outlets):
        calls.append(module)

    module.register_forward_hook(observe)
    with gm.no_outputs():
        assert not module(inlet=stream).outputs
        with gm.no_outputs():
            assert not module(inlet=stream).outputs
        assert not module(inlet=stream).outputs
    assert module(inlet=stream).outputs.result == 2
    assert calls == [module]

    @gm.no_outputs()
    def fast_call():
        return module(inlet=stream)

    assert not fast_call().outputs


STREAM = Stream(m_dot=1, T=300, p=1e5)


class EnergyLeaf(Module):
    """Emit a fixed electrical output while preserving a stream."""

    def __init__(self):
        """Declare one stream path and an electricity output."""
        super().__init__()
        self.inlet = Inlet(Stream)
        self.electricity = Output(Electricity)
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Return the inlet stream."""
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.electricity = 2


class FormulaParent(Module):
    """Exercise copy, total, ratio and outlet-field formulas."""

    calls = 1

    def __init__(self):
        """Declare one child and every formula kind."""
        super().__init__()
        self.child = EnergyLeaf()
        self.inlet = Inlet(Stream)
        self.copied = Output.of("child.electricity")
        self.total = Output.total("electricity")
        self.ratio = Output.ratio("copied", "total")
        self.mass = Output.of("child.outlet.m_dot")
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Call the child ``calls`` times."""
        for _ in range(self.calls):
            child = self.child(inlet=inlets.inlet)
        outlets = dict(outlet=child.outlets.outlet)
        return outlets


class RepeatedParent(FormulaParent):
    """Call one leaf twice."""

    calls = 2


def test_formula_outputs_copy_sum_divide_and_read_outlet_fields():
    """Formula outputs use this call's exact descendant records in declaration order."""
    result = FormulaParent()(inlet=STREAM)
    assert dict(result.outputs) == {"copied": 2, "total": 2, "ratio": 1, "mass": 1}


class RepeatedTotal(Module):
    """Sum the output of one leaf called twice."""

    def __init__(self):
        """Declare one child and a total."""
        super().__init__()
        self.child = EnergyLeaf()
        self.total = Output.total("electricity")

    def forward(self, inlets):
        """Call the child twice."""
        self.child(inlet=STREAM)
        self.child(inlet=STREAM)
        outlets = dict()
        return outlets


def test_total_counts_every_call():
    """A leaf called twice contributes twice to a total."""
    assert RepeatedTotal()().outputs.total == 4


class SummedParent(Module):
    """Declare an additive output without a formula over one leaf called ``calls`` times."""

    calls = 1

    def __init__(self):
        """Declare one child and the summed output."""
        super().__init__()

        # Modules
        self.child = EnergyLeaf()

        # Outputs
        self.electricity = Output(Electricity)

    def forward(self, inlets):
        """Call the child ``calls`` times."""

        # Modules
        for _ in range(self.calls):
            self.child(inlet=STREAM)

        outlets = dict()
        return outlets


class NestedSum(Module):
    """Sum over a leaf and two composites that sum their own leaves."""

    def __init__(self):
        """Declare one leaf, two summing composites and the summed output."""
        super().__init__()

        # Modules
        self.leaf = EnergyLeaf()
        self.first = SummedParent()
        self.second = SummedParent()

        # Outputs
        self.electricity = Output(Electricity)

    def forward(self, inlets):
        """Call every child once."""

        # Modules
        self.leaf(inlet=STREAM)
        self.first()
        self.second()

        outlets = dict()
        return outlets


def test_additive_output_without_formula_sums_descendant_leaf_calls():
    """A summed output counts every leaf call once, including leaves of nested composites."""

    class Twice(SummedParent):
        calls = 2

    assert SummedParent()().outputs.electricity == 2
    assert Twice()().outputs.electricity == 4
    assert NestedSum()().outputs.electricity == 6


class PowerLeaf(EnergyLeaf):
    """Declare ``electricity`` as plain power instead of the additive quantity."""

    def __init__(self):
        """Declare the same name with another quantity."""
        Module.__init__(self)
        self.inlet = Inlet(Stream)
        self.electricity = Output(Power)
        self.outlet = Outlet(Stream)


def test_summed_output_rejects_the_same_name_with_another_quantity():
    """A descendant output of the same name but another quantity cannot be summed."""

    class Mixed(SummedParent):
        def __init__(self):
            super().__init__()
            self.other = PowerLeaf()

    with pytest.raises(gm.errors.FormulaError, match="other.electricity = power.*expected electr"):
        Mixed()()


def test_summed_output_without_descendant_suggests_a_close_name():
    """A summed name that no descendant leaf declares names the closest leaf output."""

    class Typo(SummedParent):
        def __init__(self):
            super().__init__()
            self.electricty = Output(Electricity)

    with pytest.raises(gm.errors.FormulaError, match="did you mean 'electricity'"):
        Typo()()


def test_composite_own_value_replaces_the_automatic_sum():
    """A composite that records its own additive value is not summed."""

    class Own(SummedParent):
        def _compute_outputs(self, inlets, outlets):
            self.electricity = 7

    assert Own()().outputs.electricity == 7


def test_forward_hook_sees_the_automatic_sum():
    """Forward hooks run after automatic sums and read them like any output."""
    module = SummedParent()
    seen = []
    module.register_forward_hook(lambda module, inlets, outlets: seen.append(module.electricity))
    module()
    assert seen == [2]


def test_copy_needs_exactly_one_call():
    """``Output.of`` refuses a descendant that was called twice."""
    with pytest.raises(gm.errors.OutputError, match="child.*called 2 times"):
        RepeatedParent()(inlet=STREAM)


class PowerUse(Module):
    """Power-valued additive leaf."""

    def __init__(self):
        """Declare a power output."""
        super().__init__()
        self.use = Output(Power)

    def forward(self, inlets):
        """Produce no stream."""
        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.use = 0


class MassUse(PowerUse):
    """Mass-valued additive leaf."""

    def __init__(self):
        """Declare a mass-flow output."""
        Module.__init__(self)
        self.use = Output(MassFlow)

    def _compute_outputs(self, inlets, outlets):
        self.use = 1


class FormulaOf(Module):
    """Composite over power and mass leaves with one configurable formula output."""

    def __init__(self, formula):
        """Declare both leaves and the formula under test."""
        super().__init__()
        self.power = PowerUse()
        self.mass = MassUse()
        self.value = formula

    def forward(self, inlets):
        """Call both leaves once."""
        self.power()
        self.mass()
        outlets = dict()
        return outlets


def test_total_requires_one_unit():
    """Summing power and mass flow is rejected."""
    with pytest.raises(gm.errors.FormulaError, match="differing units"):
        FormulaOf(Output.total("use"))()


def test_zero_denominator_ratio_is_none():
    """A ratio with a zero divisor records ``None``."""
    module = FormulaOf(Output.of("power.use"))
    module.ratio = Output.ratio("value", "value")
    assert module().outputs.ratio is None


def test_formula_typo_suggests_the_close_path():
    """A misspelled formula path names the closest valid one."""
    with pytest.raises(gm.errors.FormulaError, match="did you mean 'power.use'"):
        FormulaOf(Output.of("power.ues"))()


def test_listings_recurse_by_default_and_ports_stay_local(fresh_plant):
    """Declaration listings use dotted paths below the module; ports are the module's own."""
    doublet = fresh_plant.doublet
    assert "esp.frequency" in doublet.controls()
    assert "reservoir.production_rate" in doublet.inputs()
    assert "esp.head" in doublet.outputs()
    assert "esp.head" in doublet.soft_sensors()
    assert "esp.no_stages" in dict(doublet.named_parameters())
    assert list(doublet.controls(recurse=False)) == []
    assert list(doublet.outputs(recurse=False)) == ["electricity", "heat_loss"]
    assert list(doublet.inlets()) == ["return_in"]
    assert list(doublet.outlets()) == ["supply_out"]

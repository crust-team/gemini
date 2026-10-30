"""Registration, calls, state and output-recording contracts."""

import math
import pickle
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

import gemini as gm
from gemini import backends, ops
from gemini.modules import Module, ModuleDict
from gemini.types import (
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
from tests.fixtures.errors import raises


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
    with pytest.raises(gm.errors.ValidationError):
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


def test_a_wrong_call_names_the_inlets():
    """Missing, misspelled, mixed, invalid and repeated inlets each say what is valid."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)
    with raises(
        gm.errors.ValidationError,
        "invalid_call",
        match="pass_through.*missing.*inlet.*valid names: inlet",
    ):
        module()
    with raises(
        gm.errors.ValidationError,
        "invalid_call",
        match="pass_through.*inlett.*valid names.*did you mean 'inlet'",
    ):
        module(inlett=stream)
    with raises(
        gm.errors.ValidationError,
        "invalid_call",
        match="pass_through.*cannot mix.*inlet.*valid names: inlet",
    ):
        module({"inlet": stream}, inlet=stream)
    with raises(
        gm.errors.ValidationError,
        "invalid_call",
        match="pass_through.*invalid inlet 'inlet'.*valid names: inlet",
    ):
        module(inlet=1)
    with raises(
        gm.errors.ValidationError,
        "invalid_call",
        match="pass_through.*multiple values.*inlet.*valid names",
    ):
        module(stream, inlet=stream)


def test_outlet_dict_names_and_flow_types_are_checked(monkeypatch):
    """Forward returns exactly one declared, correctly typed outlet dictionary."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough().update_params(value=2)

    def scalar_forward(inlets):
        return inlets.inlet

    monkeypatch.setattr(module, "forward", scalar_forward)
    with pytest.raises(gm.errors.DefinitionError, match="outlet dict"):
        module(inlet=stream)

    monkeypatch.setattr(module, "forward", lambda inlets: {})
    with pytest.raises(gm.errors.DefinitionError, match=r"pass_through.*missing=\['outlet'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": stream, "extra": stream})
    with pytest.raises(gm.errors.DefinitionError, match=r"pass_through.*extra=\['extra'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": 1})
    with pytest.raises(
        gm.errors.DefinitionError, match="pass_through.*invalid outlet 'outlet'.*valid names"
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
        self.child_value = Output.of(self.children_by_name.child.result)

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
    with raises(gm.errors.ValidationError, "missing_value", match="uninitialized"):
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
    with pytest.raises(gm.errors.ValidationError, match="frequency.*invalid control.*Hz"):
        module.frequency = "61 Hz"


def test_missing_input_and_unknown_keyword_errors_are_complete():
    """Missing and unknown values report path, kind, unit and valid names before forward."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = RequiredInputs()
    with raises(
        gm.errors.ValidationError, "missing_value", match="required_inputs.frequency.*control.*Hz"
    ):
        module(inlet=stream)
    module.frequency = 50
    with raises(
        gm.errors.ValidationError,
        "missing_value",
        match="required_inputs.grid_frequency.*boundary.*Hz",
    ):
        module(inlet=stream)
    with raises(gm.errors.ValidationError, "invalid_call", match="valid names"):
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
    with raises(gm.errors.ValidationError, "unknown_name", match="did you mean 'child.frequency'"):
        parent.set_inputs({"child.frequncy": 40})


def test_hooks_require_the_fixed_signatures():
    """Hook registration rejects old by-name, variadic and defaulted signatures."""
    module = PassThrough().update_params(value=1)

    with pytest.raises(gm.errors.DefinitionError, match="forward hook.*module, inlets, outlets"):
        module.register_forward_hook(lambda module, inlet, outlet: None)
    with pytest.raises(gm.errors.DefinitionError, match="forward pre-hook.*module, inlets"):
        module.register_forward_pre_hook(lambda module: None)

    def defaulted(module, inlets, outlets=None):
        pass

    with pytest.raises(gm.errors.DefinitionError, match="forward hook.*module, inlets, outlets"):
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
    with pytest.raises(gm.errors.DefinitionError, match="missing_output.*value"):
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
    """Exercise copy, automatic-sum, ratio and outlet-field formulas."""

    calls = 1

    def __init__(self):
        """Declare one child and every formula kind."""
        super().__init__()
        self.child = EnergyLeaf()
        self.inlet = Inlet(Stream)
        self.copied = Output.of(self.child.electricity)
        self.electricity = Output(Electricity)
        self.ratio = Output.ratio(self.copied, self.electricity)
        self.mass = Output.of(self.child.outlet.field("m_dot"))
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
    module = FormulaParent()
    result = module(inlet=STREAM)
    assert dict(result.outputs) == {"copied": 2, "electricity": 2, "ratio": 1, "mass": 1}
    assert module.outputs()["copied"].quantity == "electricity"


class RepeatedTotal(Module):
    """Sum the output of one leaf called twice."""

    def __init__(self):
        """Declare one child and a summed output."""
        super().__init__()
        self.child = EnergyLeaf()
        self.electricity = Output(Electricity)

    def forward(self, inlets):
        """Call the child twice."""
        self.child(inlet=STREAM)
        self.child(inlet=STREAM)
        outlets = dict()
        return outlets


def test_reference_formulas_survive_deep_copy_and_nesting():
    """A copied or nested composite resolves its references to its own descendants."""
    copy = deepcopy(FormulaParent())
    holder = ModuleDict({"inner": FormulaParent()})
    assert copy(inlet=STREAM).outputs.copied == 2
    assert holder.inner(inlet=STREAM).outputs.mass == 1


def test_wrong_references_fail_when_the_class_is_built():
    """References outside the descendant tree or to later outputs fail in ``__init__``."""
    stranger = EnergyLeaf()

    class Foreign(Module):
        def __init__(self):
            super().__init__()
            self.child = EnergyLeaf()
            self.copied = Output.of(stranger.electricity)

    class OwnOutput(Module):
        def __init__(self):
            super().__init__()
            self.child = EnergyLeaf()
            self.own = Output.of(self.child.electricity)
            self.copied = Output.of(self.own)

    class ChildOperand(Module):
        def __init__(self):
            super().__init__()
            self.child = EnergyLeaf()
            self.copied = Output.of(self.child.electricity)
            self.ratio = Output.ratio(self.copied, self.child.electricity)

    for cls in (Foreign, OwnOutput):
        with pytest.raises(gm.errors.DefinitionError, match="not an output or outlet field"):
            cls()
    with pytest.raises(gm.errors.DefinitionError, match="not an earlier output of this module"):
        ChildOperand()
    with pytest.raises(gm.errors.DefinitionError, match="did you mean 'm_dot'"):
        EnergyLeaf().outlet.field("mdot")


def test_total_counts_every_call():
    """A leaf called twice contributes twice to a total."""
    assert RepeatedTotal()().outputs.electricity == 4


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

    with pytest.raises(
        gm.errors.DefinitionError, match="other.electricity = power.*expected electr"
    ):
        Mixed()()


def test_summed_output_without_descendant_suggests_a_close_name():
    """A summed name that no descendant leaf declares names the closest leaf output."""

    class Typo(SummedParent):
        def __init__(self):
            super().__init__()
            self.electricty = Output(Electricity)

    with pytest.raises(gm.errors.DefinitionError, match="did you mean 'electricity'"):
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
    with pytest.raises(gm.errors.DefinitionError, match="child.*called 2 times"):
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

    def __init__(self, build):
        """Declare both leaves, then the outputs that ``build(self)`` returns by name."""
        super().__init__()

        # Modules
        self.power = PowerUse()
        self.mass = MassUse()

        # Outputs
        for name, declaration in build(self).items():
            setattr(self, name, declaration)

    def forward(self, inlets):
        """Call both leaves once."""
        self.power()
        self.mass()
        outlets = dict()
        return outlets


def test_sum_requires_one_unit():
    """Summing power and mass flow is rejected."""
    with pytest.raises(gm.errors.DefinitionError, match="power.use = power \\[W\\]; expected mass"):
        FormulaOf(lambda module: {"use": Output(MassFlow)})()


def test_zero_denominator_ratio_is_none():
    """A ratio with a zero divisor records ``None``."""
    module = FormulaOf(lambda module: {"value": Output.of(module.power.use)})
    module.ratio = Output.ratio(module.value, module.value)
    assert module().outputs.ratio is None


def test_formula_typo_fails_when_the_class_is_built():
    """A misspelled reference fails in ``__init__``, before any call."""
    with pytest.raises(AttributeError, match="ues"):
        FormulaOf(lambda module: {"value": Output.of(module.power.ues)})


def test_misspelled_child_names_path_and_suggestion():
    """A misspelled child fails with the module path and the closest child."""
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        FormulaOf(lambda module: {"value": Output.of(module.powerr.use)})
    message = str(caught.value)
    assert message.startswith("formula_of: unknown member 'powerr'")
    assert "did you mean 'power'?" in message


def test_misspelled_output_on_a_child_names_the_child_path():
    """A misspelled output on a real child names that child and suggests the output."""
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        FormulaOf(lambda module: {"value": Output.of(module.power.ues)})
    assert "power: unknown member 'ues'" in str(caught.value)
    assert "did you mean 'use'?" in str(caught.value)


class OutletFormula(Module):
    """Composite referencing a named attribute of a child."""

    def __init__(self, reference):
        """Copy the output named by ``reference`` on the pass-through child."""
        super().__init__()

        # Modules
        self.pass_through = PassThrough()

        # Outputs
        self.copied = Output.of(getattr(self.pass_through, reference))


def test_misspelled_outlet_suggests_the_outlet():
    """A misspelled outlet is suggested from the ports of the child."""
    with raises(gm.errors.ValidationError, "unknown_name", match="did you mean 'outlet'"):
        OutletFormula("outlett")


class RatioTypo(Module):
    """Composite whose ratio misspells an earlier output."""

    def __init__(self):
        """Declare a copied output, then a ratio that misspells it."""
        super().__init__()

        # Modules
        self.power = PowerUse()

        # Outputs
        self.value = Output.of(self.power.use)
        self.ratio = Output.ratio(self.valuee, self.value)


def test_ratio_operand_typo_is_reported():
    """A misspelled ``Output.ratio`` operand fails the same way."""
    with raises(gm.errors.ValidationError, "unknown_name", match="did you mean 'value'"):
        RatioTypo()


def test_unknown_member_stays_an_attribute_error():
    """``hasattr`` and ``getattr`` with a default treat the miss as before."""
    module = FormulaOf(lambda module: {"value": Output.of(module.power.use)})
    assert not hasattr(module, "missing")
    assert getattr(module, "missing", None) is None
    with pytest.raises(AttributeError):
        module.missing


def test_unknown_member_before_super_init_has_no_registries():
    """Reading a name before ``super().__init__()`` still raises ``AttributeError``."""

    class Early(Module):
        """Reads an attribute before the base initializer."""

        def __init__(self):
            """Probe a missing name first."""
            self.probe = getattr(self, "missing", "absent")
            super().__init__()

    assert Early().probe == "absent"


def test_unknown_member_survives_pickle_and_copy():
    """The error round-trips with its message intact."""
    module = FormulaOf(lambda module: {"value": Output.of(module.power.use)})
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        module.powerr
    for clone in (pickle.loads(pickle.dumps(caught.value)), deepcopy(caught.value)):
        assert str(clone) == str(caught.value)
        assert "did you mean 'power'?" in str(clone)


def test_formula_strings_are_rejected():
    """Formulas take declaration references; path strings and ``Output.total`` are gone."""
    assert not hasattr(Output, "total")
    with pytest.raises(gm.errors.DefinitionError, match="expected a descendant output declaration"):
        FormulaOf(lambda module: {"value": Output.of("power.use")})
    with pytest.raises(gm.errors.DefinitionError, match="'value' is not an earlier output"):
        FormulaOf(lambda module: {"value": Output.ratio("value", "value")})


def test_listings_recurse_by_default_and_ports_stay_local(fresh_plant):
    """Declaration listings use dotted paths below the module; ports are the module's own."""
    doublet = fresh_plant.doublet
    assert "esp.frequency" in doublet.controls()
    assert "reservoir.production_rate" in doublet.inputs()
    assert "esp.head" in doublet.outputs()
    assert "esp.head" in doublet.soft_sensors()
    assert "esp.stage_count" in dict(doublet.named_parameters())
    assert list(doublet.controls(recurse=False)) == []
    assert list(doublet.outputs(recurse=False)) == ["electricity", "heat_loss"]
    assert list(doublet.inlets()) == ["return_in"]
    assert list(doublet.outlets()) == ["supply_out"]


class Quotient(Module):
    """Divide a parameter, a control and an inlet field with plain operators."""

    def __init__(self):
        """Declare the operands of the plain divisions."""
        super().__init__()

        # Parameters
        self.numerator = Parameter(float, default=2.0)
        self.coefficients = Parameter(list[float], default=[1.0, 2.0], shape=(2,))

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.divisor = Control(float, default=0.0)

        # Outputs
        self.ratio = Output(float)
        self.finite = Output(bool)
        self.seen = Output(list[float])
        self.again = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Divide the inlet flow by the control and raise the pressure by one pascal."""
        stream = inlets.inlet
        self.kinds = (type(stream.m_dot), type(self.numerator), type(self.divisor))
        self.quotient = stream.m_dot / self.divisor
        return dict(outlet=stream.with_(p=stream.p + 1.0))

    def _compute_outputs(self, inlets, outlets):
        self.ratio = self.numerator / self.divisor
        self.finite = self.ratio < 1e300
        self.seen = [coefficient / self.divisor for coefficient in self.coefficients]
        self.again = self.ratio / self.divisor


def test_an_eager_call_divides_silently_and_returns_plain_python_values():
    """Parameters, controls and inlet fields are NumPy scalars inside; results are Python."""
    module = Quotient()
    stream = Stream(m_dot=0.0, T=300.0, p=1e5)
    result = module(inlet=stream)
    assert [kind.__name__ for kind in module.kinds] == ["float64"] * 3
    assert math.isinf(result.outputs.ratio) and type(result.outputs.ratio) is float
    assert type(result.outputs.finite) is bool and result.outputs.finite is False
    assert result.outputs.seen == [math.inf, math.inf]
    assert result.outputs.again == math.inf and type(result.outputs.again) is float
    assert all(type(item) is float for item in result.outputs.seen)
    assert math.isnan(module.quotient) and type(result.outlets.outlet.p) is float
    assert result.inlets.inlet is stream and type(stream.m_dot) is float
    assert type(result.inputs["divisor"]) is float
    assert "np.float64" not in str(result.outlets.outlet) and "np.float64" not in str(stream)


def test_a_forced_numpy_backend_keeps_plain_division_silent():
    """Ops give 0-d arrays under a forced NumPy backend; a call on them still wraps its scalars."""

    class Divider(Module):
        def __init__(self):
            super().__init__()
            self.gain = Parameter(float, default=1.0)
            self.ratio = Output(float)

        def forward(self, inlets):
            outlets = dict()
            return outlets

        def _compute_outputs(self, inlets, outlets):
            self.ratio = ops.where(self.gain > 2.0, self.gain / 0.0, ops.add(self.gain, 1.0))

    with backends.settings(backend="numpy"):
        assert Divider()().outputs.ratio == 2.0

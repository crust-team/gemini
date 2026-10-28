"""Registration, calls, state and output-recording contracts."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import gemini as gm
from gemini.core.modules import Module, ModuleDict
from gemini.core.types import (
    Boundary,
    Control,
    Frequency,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
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

    def forward(self, inlet):
        """Record the scalar product and return the stream."""

        # Outlets
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlet, outlet):
        self.result = self.value * self.multiplier


def test_registration_construction_and_state():
    """Keyword values fill registered declarations and state reload is atomic."""
    module = PassThrough(value=2)
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
    """Calls validate arguments, required outputs and outlet names."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)
    result = module(inlet=stream, multiplier=4)
    assert result.outputs.result == 8
    assert result.outlets.outlet is stream
    assert module.result.soft_sensor
    with pytest.raises(TypeError, match="missing required inlet"):
        module()
    with pytest.raises(TypeError):
        module(inlet=stream, unexpected=1)


def test_single_outlet_scalar_return_is_rejected(monkeypatch):
    """A one-outlet module must return the same explicit dictionary shape as every module."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)

    def scalar_forward(inlet):
        return inlet

    monkeypatch.setattr(module, "forward", scalar_forward)
    with pytest.raises(TypeError, match="outlet dict"):
        module(inlet=stream)

    class WrongSignature(Module):
        """Fixture with a declaration/signature mismatch."""

        def __init__(self):
            super().__init__()

            # Controls
            self.command = Control(float)

        def forward(self, other):
            """Use the deliberately wrong name."""

            outlets = dict()
            return outlets

    with pytest.raises(TypeError, match="signature mismatch"):
        WrongSignature()(command=1)


def test_output_records_are_nested_and_thread_local():
    """Concurrent and nested evaluations never share output records."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda value: module(inlet=stream, multiplier=value), range(1, 9)))
    assert [result.outputs.result for result in values] == [2 * value for value in range(1, 9)]
    assert module.result.soft_sensor

    class Parent(Module):
        """Nested-call fixture."""

        def __init__(self):
            super().__init__()

            # Modules
            self.children_by_name = ModuleDict({"child": PassThrough(value=3)})

            # Inlets
            self.inlet = Inlet(Stream)

            # Outputs
            self.child_value = Output.of("children_by_name.child.result")

            # Outlets
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            """Call the child and copy its recorded output."""

            # Modules
            child = self.children_by_name.child(inlet=inlet, multiplier=2)

            # Outlets
            outlet = child.outlets.outlet

            outlets = dict(outlet=outlet)
            return outlets

    result = Parent()(inlet=stream)
    assert result.outputs.child_value == 6
    assert result.children["children_by_name.child"].outputs.result == 6
    assert Parent().children_by_name.child(inlet=stream).outputs.result == 3


def test_uninitialized_and_hooks():
    """Uninitialized parameters and hook ordering have clear behavior."""
    module = PassThrough()
    assert module.missing_parameters() == ["value"]
    with pytest.raises(RuntimeError, match="uninitialized"):
        module(inlet=Stream(m_dot=1, T=300, p=1e5))
    module.value = 2
    calls = []
    before = module.register_forward_pre_hook(lambda *args: calls.append("before"))
    after = module.register_forward_hook(lambda module: calls.append("after"))
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

    def forward(self, inlet):
        """Read applied values through ordinary attributes."""

        # Outlets
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlet, outlet):
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
    with pytest.raises(TypeError, match="required_inputs.frequency.*control.*Hz"):
        module(inlet=stream)
    module.frequency = 50
    with pytest.raises(TypeError, match="required_inputs.grid_frequency.*boundary.*Hz"):
        module(inlet=stream)
    with pytest.raises(TypeError, match="valid inlets, controls and boundaries"):
        module(inlet=stream, typo=1)


def test_call_inputs_and_hook_assignments_do_not_leak():
    """Context-local values survive nesting and pre-hook changes last for one call only."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = RequiredInputs()
    module.set_inputs({"frequency": 50, "grid_frequency": 50})
    seen = []

    def clamp(current):
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

        def forward(self, inlet):
            """Override frequency for only the current call."""

            # Outlets
            outlet = inlet

            outlets = dict(outlet=outlet)
            return outlets

        def _compute_outputs(self, inlet, outlet):
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
    module = PassThrough(value=2)
    calls = []
    first = module.register_forward_pre_hook(lambda current: calls.append(("first", current)))
    second = module.register_forward_pre_hook(lambda current: calls.append(("second", current)))

    def observe(module, inlet, outlet):
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
    restored = PassThrough(value=1).load_state_dict(state)
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

        def forward(self):
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
    with pytest.raises(ValueError, match="did you mean 'child.frequency'"):
        parent.set_inputs({"child.frequncy": 40})


def test_compute_output_signature_is_checked_at_class_definition():
    """Output callbacks can request only declared inlet and outlet names."""
    with pytest.raises(TypeError, match="BadOutputName.*typo.*inlet.*outlet"):

        class BadOutputName(Module):
            """Deliberately invalid output callback fixture."""

            def __init__(self):
                super().__init__()
                self.inlet = Inlet(Stream)
                self.value = Output(float)
                self.outlet = Outlet(Stream)

            def forward(self, inlet):
                outlets = dict(outlet=inlet)
                return outlets

            def _compute_outputs(self, typo):
                self.value = 1


def test_missing_output_and_named_hook_ordering():
    """Checks run after output computation and named hooks observe completed values."""

    class MissingOutput(Module):
        """Leave one declared output unset."""

        def __init__(self):
            super().__init__()
            self.inlet = Inlet(Stream)
            self.value = Output(float)
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            outlets = dict(outlet=inlet)
            return outlets

        def _compute_outputs(self, inlet, outlet):
            pass

    stream = Stream(m_dot=1, T=300, p=1e5)
    module = MissingOutput()
    with pytest.raises(RuntimeError, match="missing_output.*value"):
        module(inlet=stream)

    good = PassThrough(value=3)
    seen = []

    def observe(module, inlet, outlet):
        seen.append((module.result, inlet, outlet))

    good.register_forward_hook(observe)
    good(inlet=stream, multiplier=2)
    assert seen == [(6, stream, stream)]
    with pytest.raises(TypeError, match="unknown inlet/outlet 'typo'"):
        good.register_forward_hook(lambda module, typo: None)


def test_no_outputs_is_nested_thread_local_context_and_decorator():
    """The fast path skips output callbacks, formulas, hooks and output checks."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)
    calls = []

    def observe(module):
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


def test_formula_outputs_count_calls_sum_leaves_and_read_outlet_fields():
    """Formula outputs use this call's exact descendant records in declaration order."""
    stream = Stream(m_dot=1, T=300, p=1e5)

    class EnergyLeaf(Module):
        """Emit a fixed electrical output while preserving a stream."""

        def __init__(self):
            super().__init__()
            self.inlet = Inlet(Stream)
            self.electricity = Output(Power)
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            outlets = dict(outlet=inlet)
            return outlets

        def _compute_outputs(self, inlet, outlet):
            self.electricity = 2

    class FormulaParent(Module):
        """Exercise copy, total, ratio and outlet-field formulas."""

        def __init__(self):
            super().__init__()
            self.child = EnergyLeaf()
            self.inlet = Inlet(Stream)
            self.copied = Output.of("child.electricity")
            self.total = Output.total("electricity")
            self.ratio = Output.ratio("copied", "total")
            self.mass = Output.of("child.outlet.m_dot")
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            child = self.child(inlet=inlet)
            outlet = child.outlets.outlet
            outlets = dict(outlet=outlet)
            return outlets

    result = FormulaParent()(inlet=stream)
    assert dict(result.outputs) == {"copied": 2, "total": 2, "ratio": 1, "mass": 1}

    class RepeatedParent(Module):
        """Call one leaf twice so totals include both evaluations."""

        def __init__(self):
            super().__init__()
            self.child = EnergyLeaf()
            self.inlet = Inlet(Stream)
            self.total = Output.total("electricity")
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            self.child(inlet=inlet)
            child = self.child(inlet=inlet)
            outlet = child.outlets.outlet
            outlets = dict(outlet=outlet)
            return outlets

    assert RepeatedParent()(inlet=stream).outputs.total == 4

    class ExactlyOnceParent(Module):
        """Copy an output from a child that is deliberately called twice."""

        def __init__(self):
            Module.__init__(self)
            self.child = EnergyLeaf()
            self.inlet = Inlet(Stream)
            self.copied = Output.of("child.electricity")
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            self.child(inlet=inlet)
            child = self.child(inlet=inlet)
            outlet = child.outlets.outlet
            outlets = dict(outlet=outlet)
            return outlets

    with pytest.raises(RuntimeError, match="child.*called 2 times"):
        ExactlyOnceParent()(inlet=stream)


def test_formula_validation_units_zero_ratio_and_typo_suggestion():
    """Totals require matching additive units and formula mistakes are actionable."""

    class PowerUse(Module):
        """Power-valued additive leaf."""

        def __init__(self):
            super().__init__()
            self.use = Output(Power)

        def forward(self):
            outlets = dict()
            return outlets

        def _compute_outputs(self):
            self.use = 0

    class MassUse(Module):
        """Mass-valued additive leaf."""

        def __init__(self):
            super().__init__()
            self.use = Output(MassFlow)

        def forward(self):
            outlets = dict()
            return outlets

        def _compute_outputs(self):
            self.use = 1

    class BadTotal(Module):
        """Combine incompatible additive units."""

        def __init__(self):
            super().__init__()
            self.power = PowerUse()
            self.mass = MassUse()
            self.use = Output.total("use")

        def forward(self):
            self.power()
            self.mass()
            outlets = dict()
            return outlets

    with pytest.raises(TypeError, match="differing units"):
        BadTotal()()

    class ZeroRatio(Module):
        """Produce a zero-denominator ratio."""

        def __init__(self):
            super().__init__()
            self.child = PowerUse()
            self.value = Output.of("child.use")
            self.ratio = Output.ratio("value", "value")

        def forward(self):
            self.child()
            outlets = dict()
            return outlets

    assert ZeroRatio()().outputs.ratio is None

    class TypoFormula(Module):
        """Misspell a known descendant output."""

        def __init__(self):
            super().__init__()
            self.child = PowerUse()
            self.value = Output.of("child.ues")

        def forward(self):
            self.child()
            outlets = dict()
            return outlets

    with pytest.raises(ValueError, match="did you mean 'child.use'"):
        TypoFormula()()

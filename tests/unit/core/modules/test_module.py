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
    """All supported inlet call forms resolve to the same fixed Ports shape."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)
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

    with pytest.raises(TypeError, match="pass_through.*missing.*inlet.*valid names: inlet"):
        module()
    with pytest.raises(TypeError, match="pass_through.*inlett.*did you mean 'inlet'.*valid names"):
        module(inlett=stream)
    with pytest.raises(TypeError, match="pass_through.*cannot mix.*inlet.*valid names: inlet"):
        module({"inlet": stream}, inlet=stream)
    with pytest.raises(TypeError, match="pass_through.*invalid inlet 'inlet'.*valid names: inlet"):
        module(inlet=1)
    with pytest.raises(TypeError, match="pass_through.*multiple values.*inlet.*valid names"):
        module(stream, inlet=stream)


def test_outlet_dict_names_and_flow_types_are_checked(monkeypatch):
    """Forward returns exactly one declared, correctly typed outlet dictionary."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)

    def scalar_forward(inlets):
        return inlets.inlet

    monkeypatch.setattr(module, "forward", scalar_forward)
    with pytest.raises(TypeError, match="outlet dict"):
        module(inlet=stream)

    monkeypatch.setattr(module, "forward", lambda inlets: {})
    with pytest.raises(ValueError, match=r"pass_through.*missing=\['outlet'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": stream, "extra": stream})
    with pytest.raises(ValueError, match=r"pass_through.*extra=\['extra'\]"):
        module(inlet=stream)
    monkeypatch.setattr(module, "forward", lambda inlets: {"outlet": 1})
    with pytest.raises(TypeError, match="pass_through.*invalid outlet 'outlet'.*valid names"):
        module(inlet=stream)


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

        def forward(self, inlets):
            """Call the child and copy its recorded output."""

            # Modules
            inlet = inlets.inlet
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
    with pytest.raises(TypeError, match="required_inputs.frequency.*control.*Hz"):
        module(inlet=stream)
    module.frequency = 50
    with pytest.raises(TypeError, match="required_inputs.grid_frequency.*boundary.*Hz"):
        module(inlet=stream)
    with pytest.raises(TypeError, match="valid names"):
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
    module = PassThrough(value=2)
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
    with pytest.raises(ValueError, match="did you mean 'child.frequency'"):
        parent.set_inputs({"child.frequncy": 40})


def test_hooks_require_the_fixed_signatures():
    """Hook registration rejects old by-name, variadic and defaulted signatures."""
    module = PassThrough(value=1)

    with pytest.raises(TypeError, match="forward hook.*module, inlets, outlets"):
        module.register_forward_hook(lambda module, inlet, outlet: None)
    with pytest.raises(TypeError, match="forward pre-hook.*module, inlets"):
        module.register_forward_pre_hook(lambda module: None)

    def defaulted(module, inlets, outlets=None):
        pass

    with pytest.raises(TypeError, match="forward hook.*module, inlets, outlets"):
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
    with pytest.raises(RuntimeError, match="missing_output.*value"):
        module(inlet=stream)

    good = PassThrough(value=3)
    seen = []

    def observe(module, inlets, outlets):
        seen.append((module.result, inlets.inlet, outlets.outlet))

    good.register_forward_hook(observe)
    good(inlet=stream, multiplier=2)
    assert seen == [(6, stream, stream)]


def test_no_outputs_is_nested_thread_local_context_and_decorator():
    """The fast path skips output callbacks, formulas, hooks and output checks."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)
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

        def forward(self, inlets):
            outlets = dict(outlet=inlets.inlet)
            return outlets

        def _compute_outputs(self, inlets, outlets):
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

        def forward(self, inlets):
            inlet = inlets.inlet
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

        def forward(self, inlets):
            inlet = inlets.inlet
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

        def forward(self, inlets):
            inlet = inlets.inlet
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

        def forward(self, inlets):
            outlets = dict()
            return outlets

        def _compute_outputs(self, inlets, outlets):
            self.use = 0

    class MassUse(Module):
        """Mass-valued additive leaf."""

        def __init__(self):
            super().__init__()
            self.use = Output(MassFlow)

        def forward(self, inlets):
            outlets = dict()
            return outlets

        def _compute_outputs(self, inlets, outlets):
            self.use = 1

    class BadTotal(Module):
        """Combine incompatible additive units."""

        def __init__(self):
            super().__init__()
            self.power = PowerUse()
            self.mass = MassUse()
            self.use = Output.total("use")

        def forward(self, inlets):
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

        def forward(self, inlets):
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

        def forward(self, inlets):
            self.child()
            outlets = dict()
            return outlets

    with pytest.raises(ValueError, match="did you mean 'child.use'"):
        TypoFormula()()

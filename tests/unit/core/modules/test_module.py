"""Registration, calls, state and output-recording contracts."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from gemini.core.modules import Module, ModuleDict
from gemini.core.types import Boundary, Control, Frequency, Inlet, Outlet, Output, Parameter, Stream


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

        # Outputs
        self.result = self.value * self.multiplier

        # Outlets
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets


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
        module.result = module.value * module.multiplier
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
            self.child_value = Output(float)

            # Outlets
            self.outlet = Outlet(Stream)

        def forward(self, inlet):
            """Call the child and copy its recorded output."""

            # Modules
            child = self.children_by_name.child(inlet=inlet, multiplier=2)

            # Outputs
            self.child_value = child.outputs.result

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
    after = module.register_forward_hook(lambda *args: calls.append("after"))
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

        # Outputs
        self.total = self.frequency + self.grid_frequency

        # Outlets
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets


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
            self.frequency = 10

            # Outputs
            self.total = self.frequency + self.grid_frequency

            # Outlets
            outlet = inlet

            outlets = dict(outlet=outlet)
            return outlets

    assigned = AssignInForward()
    assigned.set_inputs({"frequency": 50, "grid_frequency": 50})
    assert assigned(inlet=stream).outputs.total == 60
    assert assigned.frequency == 50


def test_hooks_are_ordered_removable_and_can_replace_outlets():
    """Hooks use PyTorch-style arguments and a post-hook may replace the outlet mapping."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    replacement = stream.with_(p=2e5)
    module = PassThrough(value=2)
    calls = []
    first = module.register_forward_pre_hook(lambda current: calls.append(("first", current)))
    second = module.register_forward_pre_hook(lambda current: calls.append(("second", current)))
    post = module.register_forward_hook(
        lambda current, outlets: calls.append(("post", current)) or {"outlet": replacement}
    )
    result = module(inlet=stream)
    assert [name for name, _ in calls] == ["first", "second", "post"]
    assert result.outlets.outlet is replacement
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

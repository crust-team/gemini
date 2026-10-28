"""Registration, calls, state and output-recording contracts."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from gemini.core.modules import Module, ModuleDict
from gemini.core.types import Control, Inlet, Outlet, Output, Parameter, Stream


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

    def forward(self, inlet, multiplier):
        """Record the scalar product and return the stream."""

        # Outputs
        self.result = self.value * multiplier

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
    with pytest.raises(TypeError, match="missing required argument"):
        module()
    with pytest.raises(TypeError):
        module(inlet=stream, unexpected=1)


def test_single_outlet_scalar_return_is_rejected(monkeypatch):
    """A one-outlet module must return the same explicit dictionary shape as every module."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    module = PassThrough(value=2)

    def scalar_forward(inlet, multiplier):
        module.result = module.value * multiplier
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
            child = self.children_by_name.child(inlet=inlet)

            # Outputs
            self.child_value = child.outputs.result

            # Outlets
            outlet = child.outlets.outlet

            outlets = dict(outlet=outlet)
            return outlets

    result = Parent()(inlet=stream)
    assert result.outputs.child_value == 3
    assert result.children["children_by_name.child"].outputs.result == 3


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

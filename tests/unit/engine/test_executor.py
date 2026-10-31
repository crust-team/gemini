"""Executors are registered by name; an engine takes the compiled one when asked and present."""

import pytest

import gemini as gm
from gemini.engine import Executor, executor, register_executor
from gemini.engine.eager import EagerExecutor
from tests.fixtures.engine_plants import Booster


@pytest.fixture
def factories(monkeypatch):
    """Return an empty registry for the test, with the eager executor in it."""
    registry = {executor.EAGER: lambda plant: EagerExecutor()}
    monkeypatch.setattr(executor, "_FACTORIES", registry)
    return registry


def test_a_registered_factory_is_used_for_compiled_engines_only(factories):
    """``compile=True`` picks the compiled executor, ``compile=False`` the eager one."""

    class Marked(Executor):
        pass

    register_executor(executor.COMPILED, lambda plant: Marked())
    assert isinstance(executor.executor_for(Booster(), compile=True), Marked)
    assert isinstance(executor.executor_for(Booster(), compile=False), EagerExecutor)
    assert isinstance(gm.Engine(Booster(), compile=True)._executor, Marked)
    assert isinstance(gm.Engine(Booster(), compile=False)._executor, EagerExecutor)


def test_without_a_compiled_executor_the_engine_runs_eager(factories):
    """Nothing registered under ``compiled`` is no error."""
    assert isinstance(gm.Engine(Booster())._executor, EagerExecutor)


def test_without_any_executor_the_error_names_the_valid_ones(factories):
    """An empty registry cannot run and says which names exist."""
    factories.clear()
    with pytest.raises(gm.errors.ValidationError, match="executor = 'eager'") as raised:
        executor.executor_for(Booster())
    assert raised.value.code == "unknown_name"


def test_the_base_executor_defines_the_interface():
    """A subclass has to define both steps."""
    with pytest.raises(NotImplementedError):
        Executor().prepare(None, {}, {}, False)
    with pytest.raises(NotImplementedError):
        Executor().evaluate(None, 1, {})

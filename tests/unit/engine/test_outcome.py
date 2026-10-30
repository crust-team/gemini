"""One twin evaluated over a block: columns, errors, states and the tick's result tree."""

import numpy as np

from gemini.engine.columns import read
from gemini.engine.outcome import UNCHANGED, StepResults, evaluate_twin
from gemini.engine.step import BindingPlan
from gemini.graph import GraphCache
from gemini.utils.data.loader import Aligned
from tests.fixtures.engine_tank import ROW, TIME, dataset, tank


def _outcome(module, **changes):
    """Evaluate the first twin of a plan over the columns of ``ROW`` with some replaced."""
    plan = BindingPlan(module, dataset(**ROW), "replay")
    columns = {name: np.asarray(changes.get(name, [value]), float) for name, value in ROW.items()}
    count = len(columns["rate"])
    aligned = Aligned([TIME] * count, np.full(count, 900.0), columns)
    block = read(plan.twins[0], aligned, 0, count)
    return evaluate_twin(plan.twins[0], block, GraphCache(), aligned.durations, None)


def test_rows_that_work_give_columns_and_the_others_an_error_each():
    """A failing row has its exception; the table is absent for it and present for the others."""
    outcome = _outcome(tank(), rate=[2.0, -1.0, 3.0], flow=[10.0] * 3, p=[3e5] * 3, T=[330.0] * 3)
    assert list(outcome.errors) == [1] and str(outcome.errors[1]) == "negative flow"
    table = outcome.tables[""]
    assert table.present.tolist() == [True, False, True]
    assert table.columns["flow"][[0, 2]].tolist() == [2.0, 3.0]
    assert outcome.state is UNCHANGED


def test_the_result_tree_of_a_tick_is_plain_values():
    """``result`` takes the row of the array tree, children included."""
    outcome = _outcome(tank(), rate=[2.0, 3.0], flow=[10.0] * 2, p=[3e5] * 2, T=[330.0] * 2)
    result = outcome.result(1)
    assert result.outputs.flow == 3.0 and result.inputs["m_dot"] == 3.0
    assert isinstance(result.outlets["outlet"].m_dot, float)


def test_step_results_build_a_tick_lazily_and_leave_out_the_failed():
    """The mapping holds the twins that gave a result at the tick."""
    outcome = _outcome(tank(), rate=[2.0, -1.0], flow=[10.0] * 2, p=[3e5] * 2, T=[330.0] * 2)
    assert list(StepResults([outcome], 0)) == [""] and len(StepResults([outcome], 1)) == 0
    assert StepResults([outcome], 0)[""].outputs.flow == 2.0


def test_skipped_ticks_are_not_evaluated():
    """Without any tick to evaluate there is no evaluation and no table."""
    outcome = _outcome(tank(), rate=[np.nan])
    assert outcome.evaluation is None and outcome.tables == {} and outcome.errors == {}

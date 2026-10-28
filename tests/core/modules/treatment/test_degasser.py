"""Explicit placeholder behavior for Degasser."""

import pytest

from gemini.core.base.stream import Stream
from gemini.core.modules.treatment import Degasser


def test_unmodelled_equipment():
    """Valid ports still report that equipment physics is not modelled."""
    c = Degasser({"heat_transfer_coeff": 100000})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["inlet"]}
    with pytest.raises(NotImplementedError, match="degasser is not modelled yet"):
        c({}, streams)

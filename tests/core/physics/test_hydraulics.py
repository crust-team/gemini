"""Well profile limiting cases supplement the full phase-0 golden fixtures."""

import pytest

from gemini.core.base.stream import Stream
from gemini.core.physics import fluid, geometry, hydraulics


def test_zero_flow_and_unknown_correlation():
    """Preserve DPDT zero-flow behavior, and reject unknown correlation names."""
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100, inclination=1.57, inner_diameter=0.18, roughness=0.00002
            )
        ]
    )
    stream = Stream(m_dot=0, p=1e6, T=350)
    result = hydraulics.pipe_path_profile(path, stream, fluid.ConstantWater(), "up", 10, 290)
    assert result.p_out == stream.p and result.T_out == stream.T
    assert result.dp_fric == result.dp_grav == 0
    with pytest.raises(ValueError, match="Unknown correlations"):
        hydraulics.pipe_path_profile(
            path, stream, fluid.ConstantWater(), "up", 10, 290, correlation="unknown"
        )

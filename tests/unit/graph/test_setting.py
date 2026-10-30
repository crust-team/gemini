"""The traced-replay setting nests, restores and decorates like the other context settings."""

from gemini import graph


def test_traced_is_on_by_default_and_restored():
    """The setting is a context manager; ``None`` keeps the current choice."""
    assert graph.traced_enabled()
    with graph.settings(traced=False):
        assert not graph.traced_enabled()
        with graph.settings():
            assert not graph.traced_enabled()
        with graph.settings(traced=True):
            assert graph.traced_enabled()
        assert not graph.traced_enabled()
    assert graph.traced_enabled()


def test_traced_decorates_a_function():
    """A decorated call runs with the setting and restores it afterwards."""

    @graph.settings(traced=False)
    def enabled():
        return graph.traced_enabled()

    assert enabled() is False and graph.traced_enabled()

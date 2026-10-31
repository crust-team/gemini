"""String, dotted-path and message helpers."""

from gemini._utils.strings import (
    close_matches,
    did_you_mean,
    first_paragraph,
    join_names,
    join_path,
    snake_case,
    split_path,
)


def test_snake_case_keeps_acronyms_together():
    """Class names become registry-style names."""
    assert snake_case("HeatExchanger") == "heat_exchanger"
    assert snake_case("ESP") == "esp"
    assert snake_case("DoubletHeatPlant") == "doublet_heat_plant"
    assert snake_case("CO2Sensor") == "co2_sensor"


def test_dotted_paths_join_and_split_at_the_root():
    """An empty prefix is the root; splitting returns the parent and the final name."""
    assert join_path("", "esp") == "esp"
    assert join_path("doublet", "esp") == "doublet.esp"
    assert split_path("doublet.esp.frequency") == ("doublet.esp", "frequency")
    assert split_path("frequency") == ("", "frequency")


def test_message_fragments():
    """Name lists and suggestions read the same in every error message."""
    assert join_names(["a", "b"]) == "a, b"
    assert join_names([]) == "<none>"
    assert did_you_mean("suctoin", ["suction", "discharge"]) == "; did you mean 'suction'?"
    assert did_you_mean("zzz", ["suction"]) == ""
    assert did_you_mean(3, {"3a": 1}) == "; did you mean '3a'?"


def test_first_paragraph_is_one_line():
    """Docstring summaries join wrapped lines and stop at the first blank line."""
    assert (
        first_paragraph("Pump that\nraises pressure.\n\nDetails.") == "Pump that raises pressure."
    )


def test_close_matches_lists_the_closest_first():
    """Spec problems carry the close names as data."""
    assert close_matches("Boilr", ["Boiler", "Pipe"]) == ["Boiler"]
    assert close_matches("xyz", ["Boiler"]) == []

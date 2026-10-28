"""List, dictionary and traversal behavior for module containers."""

from gemini.core.modules import Filter, ModuleDict, ModuleList


def test_module_list_and_dict_registration():
    """Containers keep stable child paths and common collection operations."""
    modules = ModuleList([Filter(), Filter()])
    modules.append(Filter())
    modules.insert(1, Filter())
    assert len(modules) == 4
    assert [name for name, _ in modules.named_children()] == ["0", "1", "2", "3"]
    assert len(modules[1:3]) == 2
    mapping = ModuleDict({"hot": Filter()})
    mapping["cold"] = Filter()
    assert list(mapping) == ["hot", "cold"]
    assert mapping.hot is mapping["hot"]

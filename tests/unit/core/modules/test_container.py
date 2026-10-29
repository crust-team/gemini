"""List, dictionary and traversal behavior for module containers."""

import pytest

import gemini as gm
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


def test_slicing_keeps_the_original_child_paths():
    """E-modules-006: a slice is a plain list and does not re-path the children."""
    plant = gm.modules.Module()
    plant.filters = ModuleList([Filter(), Filter(), Filter()])
    part = plant.filters[1:3]
    assert isinstance(part, list)
    assert [module.path for module in part] == ["filters.1", "filters.2"]


def test_deleting_renumbers_without_stale_attributes():
    """E-modules-007: after ``del`` the last numeric attribute no longer exists."""
    modules = ModuleList([Filter(), Filter(), Filter()])
    del modules[0]
    assert [name for name, _ in modules.named_children()] == ["0", "1"]
    assert not hasattr(modules, "2")


def test_module_dict_hashes_by_identity_and_rejects_shadowing_keys():
    """E-modules-008: containers are hashable and keys cannot hide methods like ``step``."""
    first, second = ModuleDict(), ModuleDict()
    assert first != second and len({first, second}) == 2
    with pytest.raises(gm.errors.DeclarationError, match="shadows"):
        ModuleDict({"step": Filter()})

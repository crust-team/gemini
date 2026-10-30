"""Development-profile test selection follows changed files and their importers."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[3] / "scripts/test_changed.py"
SPEC = importlib.util.spec_from_file_location("test_changed", SCRIPT)
test_changed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(test_changed)

FILES = {
    "gemini/__init__.py": "",
    "gemini/core/__init__.py": "",
    "gemini/core/base.py": "",
    "gemini/core/user.py": "from .base import thing\n",
    "gemini/core/other.py": "",
    "tests/__init__.py": "",
    "tests/conftest.py": "import gemini.core.other\n",
    "tests/unit/conftest.py": "DATA = 'examples/shared/data.csv'\n",
    "tests/unit/core/test_base.py": "",
    "tests/unit/core/test_user.py": "",
    "tests/unit/core/test_other.py": "",
    "tests/integration/test_flow.py": "from gemini.core import user\n",
    "tests/e2e/test_examples.py": "",
    "examples/__init__.py": "",
    "examples/area/01_demo.py": "import gemini\n",
    "examples/shared/data.csv": "time\n",
}


@pytest.fixture
def repository(tmp_path):
    """Write a small repository tree and return its root."""
    for path, text in FILES.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    return tmp_path


def select(repository, *changed):
    """Return the selected test paths for some changed files."""
    graph = test_changed.import_graph(repository)
    return test_changed.select_tests(list(changed), graph, repository)


def test_module_names_and_parent_packages():
    """Paths map to dotted names, and importing a module imports its packages."""
    assert test_changed.module_name("gemini/core/user.py") == "gemini.core.user"
    assert test_changed.module_name("gemini/core/__init__.py") == "gemini.core"
    assert test_changed.module_name("docs/index.rst") is None
    assert test_changed.with_parents("a.b.c") == {"a", "a.b", "a.b.c"}


def test_relative_and_from_imports_resolve():
    """Relative imports resolve against the importing package."""
    names = test_changed.imported_names("from .base import thing\n", "gemini.core.user", False)
    assert {"gemini.core.base", "gemini.core.base.thing", "gemini"} <= names
    names = test_changed.imported_names("from . import base\n", "gemini.core", True)
    assert "gemini.core.base" in names


def test_changed_module_selects_mirror_and_transitive_importers(repository):
    """A base change reaches its mirror, the importing module's mirror and importing tests."""
    selected = select(repository, "gemini/core/base.py")
    assert set(selected) == {
        "tests/unit/core/test_base.py",
        "tests/unit/core/test_user.py",
        "tests/integration/test_flow.py",
    }
    assert "gemini/core/base.py" in selected["tests/integration/test_flow.py"]


def test_conftest_imports_are_not_followed(repository):
    """A module imported only by a conftest selects its own mirror, not the whole suite."""
    assert set(select(repository, "gemini/core/other.py")) == {"tests/unit/core/test_other.py"}


def test_package_init_change_selects_everything_importing_it(repository):
    """Every import of a subpackage also imports the root package."""
    selected = select(repository, "gemini/__init__.py")
    assert "tests/integration/test_flow.py" in selected
    assert "tests/unit/core/test_user.py" in selected


def test_configuration_and_conftest_scopes(repository):
    """Root configuration selects all tests; a nested conftest selects its directory."""
    every_test = {path for path in FILES if test_changed.is_test_file(path)}
    assert set(select(repository, "pyproject.toml")) == every_test
    assert set(select(repository, "tests/unit/conftest.py")) == {
        path for path in every_test if path.startswith("tests/unit/")
    }


def test_test_files_examples_and_data_files(repository):
    """Changed tests run themselves, examples run the example test, data selects its readers."""
    assert set(select(repository, "tests/unit/core/test_base.py")) == {
        "tests/unit/core/test_base.py"
    }
    assert "tests/e2e/test_examples.py" in select(repository, "examples/area/01_demo.py")
    assert set(select(repository, "examples/shared/data.csv")) == {
        path for path in FILES if test_changed.is_test_file(path) and "tests/unit/" in path
    }
    assert select(repository, "docs/index.rst") == {}


def test_code_quality_tests_always_run(repository):
    """The code-quality test is selected with its reason, also when nothing else is."""
    quality = test_changed.QUALITY_TEST
    (repository / quality).parent.mkdir(parents=True, exist_ok=True)
    (repository / quality).write_text("")
    assert select(repository, "docs/index.rst") == {quality: test_changed.QUALITY_REASON}
    assert select(repository) == {quality: test_changed.QUALITY_REASON}
    chosen = select(repository, "gemini/core/other.py")
    assert chosen[quality] == test_changed.QUALITY_REASON
    assert "tests/unit/core/test_other.py" in chosen
    assert select(repository, quality)[quality] == "changed test file"


def test_deleted_module_still_selects_its_importers(repository):
    """Importers of a deleted module are selected so their failures show up."""
    (repository / "gemini/core/base.py").unlink()
    assert "tests/integration/test_flow.py" in select(repository, "gemini/core/base.py")


def test_import_graph_cache_is_reused_and_refreshed(repository):
    """Unchanged files reuse the cache; edited files are parsed again."""
    cache = repository / ".tmp/imports.json"
    first = test_changed.import_graph(repository, cache)
    assert cache.exists()
    (repository / "gemini/core/other.py").write_text("import gemini.core.base\n")
    second = test_changed.import_graph(repository, cache)
    assert "gemini.core.base" not in first["gemini/core/other.py"]
    assert "gemini.core.base" in second["gemini/core/other.py"]


def test_pytest_command_uses_development_profile():
    """The selection runs in parallel on fast data and leaves slow tests to release."""
    command = test_changed.pytest_command(["tests/unit/core/test_base.py"], ["-x"])
    assert command[1:] == [
        "-m",
        "pytest",
        "-n",
        "auto",
        "-m",
        "not slow",
        "--dataset=fast",
        "--profile=development",
        "-x",
        "tests/unit/core/test_base.py",
    ]

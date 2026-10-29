"""Metadata every module class derives from its class name and docstring."""

from gemini.core.modules import HeatExchanger, Module


def test_metadata_is_derived():
    """Names come from the class name and help text from the docstring."""
    assert HeatExchanger().name == "heat_exchanger"
    assert HeatExchanger().path == "heat_exchanger"
    assert HeatExchanger.help().startswith("Two-stream heat exchanger")
    assert "ua: W/K, calibratable" in HeatExchanger.help()


def test_every_module_class_is_documented(module_class):
    """Each shipped module explains itself in its class docstring."""
    cls = module_class
    assert issubclass(cls, Module)
    assert cls.__doc__ and cls.__doc__.strip(), cls.__name__

"""PA inspection types config default and parsing."""

from carro.config import resolve_pa_inspection_types


def test_pa_inspection_types_default_on():
    assert resolve_pa_inspection_types({}) is True
    assert resolve_pa_inspection_types({"pa_inspection_types": True}) is True
    assert resolve_pa_inspection_types({"pa_inspection_types": False}) is False
    assert resolve_pa_inspection_types({"pa_inspection_types": "off"}) is False
    assert resolve_pa_inspection_types({"pa_inspection_types": "yes"}) is True

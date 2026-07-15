import pytest

from main import resolve_mode

pytestmark = pytest.mark.unit


def test_routing_matrix():
    assert resolve_mode(fixture=True, full_data=False, strict_gate=False) == "fixture_strict"
    assert resolve_mode(fixture=True, full_data=False, strict_gate=True) == "fixture_strict"
    assert resolve_mode(fixture=False, full_data=True, strict_gate=True) == "full_data_strict"
    assert resolve_mode(fixture=False, full_data=True, strict_gate=False) == "full_data_benchmark"

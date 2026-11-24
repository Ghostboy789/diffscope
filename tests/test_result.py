from pathlib import Path

from diffscope.result import DiffResult


def test_fixture_round_trips():
    text = (Path(__file__).parent / "fixtures" / "example_result.json").read_text()
    assert DiffResult.from_json(text).to_json() == text

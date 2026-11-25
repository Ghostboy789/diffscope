from pathlib import Path

from diffscope.result import DiffResult


def test_fixture_round_trips():
    text = (Path(__file__).parent / "fixtures" / "example_result.json").read_text()
    assert DiffResult.from_json(text).to_json() == text


def test_json_is_strict_with_nonfinite_values_and_typed_map_keys():
    import json
    import math
    from datetime import date

    def reject(token):
        raise AssertionError(f"invalid JSON token {token}")

    result = DiffResult.from_json((Path(__file__).parent / "fixtures/example_result.json").read_text())
    result.numeric_shifts[0].after_sum = math.inf
    result.samples["added"][0]["map_column"] = {date(2025, 1, 1): [math.nan, -math.inf]}

    raw = result.to_json()
    payload = json.loads(raw, parse_constant=reject)
    assert payload["samples"]["added"][0]["map_column"] == {"2025-01-01": ["NaN", "-Infinity"]}
    assert payload["numeric_shifts"][0]["after_sum"] == "Infinity"
    assert DiffResult.from_json(raw).numeric_shifts[0].after_sum == math.inf

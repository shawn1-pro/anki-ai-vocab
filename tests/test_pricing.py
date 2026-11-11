from decimal import Decimal

import pytest

from anki_ai_vocab.cache import Cache
from anki_ai_vocab.pricing import estimate_cost, read_cost


def usage(model="deepseek-flash", prompt=1_000_000, completion=200_000, cached=100_000):
    return {
        "model": model,
        "requests": 1,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "total_tokens": prompt + completion,
    }


def test_off_peak_and_peak_range_separates_cached_input():
    result = estimate_cost([usage()])
    assert result.minimum_cny == Decimal("1.702")
    assert result.maximum_cny == Decimal("3.404")
    assert result.requests == 1 and result.unpriced_requests == 0


def test_cached_input_is_not_charged_again_as_uncached():
    result = estimate_cost([usage(completion=0, cached=1_000_000)])
    assert result.minimum_cny == Decimal("0.02")
    assert result.maximum_cny == Decimal("0.04")


def test_multiple_models_accumulate_at_their_respective_prices():
    rows = [usage(), usage("deepseek-v4-pro", completion=1_000_000, cached=0)]
    result = estimate_cost(rows)
    assert result.minimum_cny == Decimal("19.702")
    assert result.maximum_cny == Decimal("39.404")
    assert result.requests == 2


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "deepseek-v4-flash-vision-exp"])
def test_official_legacy_flash_aliases_use_flash_price(model):
    assert estimate_cost([usage(model)]) == estimate_cost([usage()])


def test_unknown_model_is_explicitly_excluded():
    result = estimate_cost([usage("unknown_model")])
    assert result.unpriced_requests == 1
    assert "暂无法估算" in result.display()
    assert "¥0.000000" not in result.display()


def test_partial_pricing_does_not_claim_complete_total():
    result = estimate_cost([usage(), usage("unknown_model")])
    assert result.minimum_cny == Decimal("1.702")
    assert result.requests == 2 and result.unpriced_requests == 1
    assert "1 次未计价" in result.display()


def test_no_history_displays_zero_without_creating_files(tmp_path):
    path = tmp_path / "data/vocabulary.sqlite3"
    result = read_cost(path)
    assert result.minimum_cny == result.maximum_cny == 0
    assert "¥0.000000" in result.display()
    assert "0 次请求" in result.display()
    assert not path.parent.exists()


def test_existing_token_ledger_is_used_without_a_schema_migration(tmp_path):
    path = tmp_path / "vocabulary.sqlite3"
    with Cache(path) as cache:
        cache.record_usage("deepseek-flash", 100, 60, 160, 10)
        cache.record_usage("deepseek-flash", 50, 20, 70)
    modified_before = path.stat().st_mtime_ns
    result = read_cost(path)
    assert result.minimum_cny == Decimal("0.0004602")
    assert result.maximum_cny == Decimal("0.0009204")
    assert result.requests == 2
    assert path.stat().st_mtime_ns == modified_before


def test_reading_cost_or_using_cached_content_does_not_add_usage(tmp_path, entry):
    path = tmp_path / "vocabulary.sqlite3"
    with Cache(path) as cache:
        cache.put(entry)
        cache.record_usage("deepseek-flash", 100, 20, 120)
    before = read_cost(path)
    with Cache(path) as cache:
        assert cache.get(entry.word, entry.topic) == entry
    assert read_cost(path) == before

import pytest

from scripts.benchmark_realtime_cache import _percentile


def test_percentile_uses_conservative_rank_for_small_persistent_samples():
    values = [1751.94, 1876.16]

    # Nearest-rank p50 for two observations is the upper observation; the
    # benchmark itself reports the exact median separately.
    assert _percentile(values, 0.50) == pytest.approx(1876.16)
    assert _percentile(values, 0.95) == pytest.approx(1876.16)
    assert _percentile(values, 0.99) == pytest.approx(1876.16)
    assert _percentile(values, 0.50) <= _percentile(values, 0.95)
    assert _percentile(values, 0.95) <= _percentile(values, 0.99)


def test_percentile_rejects_empty_or_invalid_inputs():
    with pytest.raises(ValueError):
        _percentile([], 0.95)
    with pytest.raises(ValueError):
        _percentile([1.0], -0.1)
    with pytest.raises(ValueError):
        _percentile([1.0], 1.1)

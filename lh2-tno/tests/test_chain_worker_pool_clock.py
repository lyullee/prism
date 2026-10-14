import pytest

from lh2_tno.chain_worker import _normalise_pool_clock_interval


def test_pool_clock_normalization_moves_binary_change_points_early():
    start, end = _normalise_pool_clock_interval(
        0.060000000000000005,
        0.07000000000000001,
    )

    assert start == pytest.approx(0.059999999)
    assert end == pytest.approx(0.069999999)
    assert end > start


def test_pool_clock_normalization_rejects_collapsed_interval():
    with pytest.raises(ValueError, match="collapsed"):
        _normalise_pool_clock_interval(0.0, 0.0)

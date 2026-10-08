import pytest

from lh2_tno.source_termination import effective_source_duration


def test_declared_duration_requires_all_intervals():
    assert effective_source_duration(1.0, 0.2, [0.0, 0.2, 0.4, 0.6, 0.8]) == 1.0
    with pytest.raises(ValueError, match='declared horizon'):
        effective_source_duration(1.0, 0.2, [0.0, 0.2], 'declared')


def test_natural_duration_ends_at_final_left_held_interval_without_padding():
    assert effective_source_duration(1.0, 0.2, [0.0, 0.2, 0.4], 'model_natural') == pytest.approx(0.6)


def test_natural_duration_at_horizon_is_not_shortened():
    assert effective_source_duration(1.0, 0.2, [0.0, 0.2, 0.4, 0.6, 0.8], 'model_natural') == 1.0


@pytest.mark.parametrize('times', [[], [0.1, 0.2], [0.0, 0.2, 0.1]])
def test_invalid_history_is_rejected(times):
    with pytest.raises(ValueError):
        effective_source_duration(1.0, 0.2, times, 'model_natural')

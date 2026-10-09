import pytest

from lh2_tno.two_sided_interaction import combine_endpoint_harm


def _endpoint(low, high):
    return {
        "worker": [
            {
                "direct_fire": low,
                "delayed_flash_fire": low / 2,
                "delayed_explosion": low / 4,
                "no_ignition": 0.0,
            },
            {
                "direct_fire": high,
                "delayed_flash_fire": high / 2,
                "delayed_explosion": high / 4,
                "no_ignition": 0.0,
            },
        ]
    }


def test_two_sided_interaction_keeps_union_upper_bound_and_frechet_interval():
    result = combine_endpoint_harm([_endpoint(0.4, 0.6), _endpoint(0.3, 0.5)], ["worker"])

    row = result["receptors"]["worker"]
    assert row["branch_harm_low_high"][0]["direct_fire"] == pytest.approx(0.7)
    assert row["branch_harm_low_high"][1]["direct_fire"] == pytest.approx(1.0)
    interval = row["intersection_interval_low_high"]["direct_fire"]
    assert interval[0] == pytest.approx([0.0, 0.3])
    assert interval[1] == pytest.approx([0.1, 0.5])
    assert result["joint_interaction_resolved"] is False
    assert result["frequency_application"].startswith("one shared")


def test_two_sided_interaction_rejects_missing_receptor_or_nonzero_no_ignition_harm():
    bad = _endpoint(0.1, 0.2)
    bad["worker"][0]["no_ignition"] = 0.1
    bad["worker"][1]["no_ignition"] = 0.1
    with pytest.raises(ValueError, match="no-ignition"):
        combine_endpoint_harm([bad, _endpoint(0.1, 0.2)], ["worker"])

    with pytest.raises(ValueError, match="every facility receptor"):
        combine_endpoint_harm([_endpoint(0.1, 0.2), _endpoint(0.1, 0.2)], ["worker", "public"])


def test_two_sided_interaction_requires_two_endpoints():
    with pytest.raises(ValueError, match="exactly two"):
        combine_endpoint_harm([_endpoint(0.1, 0.2)], ["worker"])

from __future__ import annotations

from scripts.run_observed_hazop_provider_consequence_chain import _request_defaults


def test_gas_provider_packet_uses_integrated_transient_operator():
    defaults = _request_defaults(
        {"release_mode": "hole"},
        liquid_defaults={"source_operator": "placeholder"},
        relief_defaults={"source_operator": "relief"},
        packet={"boundary_kind": "resolved_atmospheric_gas_exit"},
    )
    assert defaults["source_operator"] == "integrated_transient"
    assert defaults["release_termination"]["basis"] == "provider_declared"


def test_liquid_provider_packet_keeps_liquid_operator():
    defaults = _request_defaults(
        {"release_mode": "hole"},
        liquid_defaults={"source_operator": "placeholder"},
        relief_defaults={"source_operator": "relief"},
        packet={"boundary_kind": "resolved_atmospheric_liquid_exit"},
    )
    assert defaults["source_operator"] == "equipment_liquid_release"


def test_relief_provider_packet_keeps_relief_operator():
    defaults = _request_defaults(
        {"release_mode": "maximum_relief_discharge"},
        liquid_defaults={"source_operator": "liquid"},
        relief_defaults={"source_operator": "placeholder"},
        packet={"boundary_kind": "resolved_atmospheric_gas_exit"},
    )
    assert defaults["source_operator"] == "equipment_emergency_relief"

import pytest
from pydantic import ValidationError
from lh2_tno.telemetry import Frame, FrameRejected, TagMapping, TelemetryNormalizer, Value


def mapping(**kw):
    values=dict(tag="P",component_id="generic-tank",quantity="pressure",source_unit="MPa",pressure_basis="gauge",sensor_location="vapour-port")
    values.update(kw);return TagMapping(**values)


def frame(**kw):
    d=dict(stream_id="a",sequence=1,source_time_s=10.,arrival_time_s=10.1,origin="reconstructed",values={"P":Value(value=.4,unit="MPa",quality="valid")})
    d.update(kw);return Frame(**d)


def test_gauge_conversion_is_explicit_and_origin_is_retained():
    n=TelemetryNormalizer((mapping(),),2)
    r=n.normalize(frame(),now_s=10.2,ambient_pressure_pa=101325.)
    assert r["values"]["P"]["value_si"]==501325
    assert r["independent_measurement_claim"] is False


def test_rejected_frame_does_not_advance_state():
    n=TelemetryNormalizer((mapping(),),2)
    with pytest.raises(FrameRejected):n.normalize(frame(),now_s=10.2)
    n.normalize(frame(),now_s=10.2,ambient_pressure_pa=101325.)
    with pytest.raises(FrameRejected):n.normalize(frame(),now_s=10.3,ambient_pressure_pa=101325.)


@pytest.mark.parametrize("kwargs",[{"pressure_basis":"unresolved"},{"sensor_location":None},{"source_unit":"unknown"}])
def test_unresolved_metadata_not_inferred(kwargs):
    m=mapping(**kwargs);f=frame(values={"P":Value(value=.4,unit=m.source_unit,quality="valid")})
    with pytest.raises(FrameRejected):TelemetryNormalizer((m,),2).normalize(f,now_s=10.2,ambient_pressure_pa=101325.)


@pytest.mark.parametrize("change",[{"values":{}},{"source_time_s":9.},{"source_time_s":11.},{"values":{"P":Value(value=.4,unit="MPa",quality="suspect")}}])
def test_bad_frame_cannot_update_state(change):
    with pytest.raises(FrameRejected):TelemetryNormalizer((mapping(),),1).normalize(frame(**change),now_s=10.2,ambient_pressure_pa=101325.)


def test_multiple_streams_have_independent_sequences():
    n=TelemetryNormalizer((mapping(),),2)
    n.normalize(frame(),now_s=10.2,ambient_pressure_pa=101325.)
    n.normalize(frame(stream_id="b"),now_s=10.2,ambient_pressure_pa=101325.)


def test_nan_never_enters_a_frame():
    with pytest.raises(ValidationError):Value(value=float("nan"),unit="MPa",quality="valid")

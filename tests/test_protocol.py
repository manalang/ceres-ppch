import pytest

from ceres_ppch.protocol import (
    PPCHProtocolError,
    check_response,
    parse_qprr,
    pressure_to_psi,
    validate_setpoint,
)


def test_parse_qprr_metric_response() -> None:
    reading = parse_qprr(b"R,2.306 MPa a,0.011 MPa/s,97.000 kPa a\r\n")
    assert reading.ready == "R"
    assert reading.pressure == pytest.approx(2.306)
    assert reading.pressure_unit == "MPa"
    assert reading.measurement_mode == "a"
    assert reading.rate == pytest.approx(0.011)
    assert reading.atmosphere == pytest.approx(97.0)
    assert reading.atmosphere_unit == "kPa"


def test_parse_qprr_not_ready_gauge_response() -> None:
    reading = parse_qprr("NR,23.0626 MPa g,-0.011 MPa/s,0.097001 MPa a")
    assert reading.ready == "NR"
    assert reading.measurement_mode == "g"
    assert reading.rate == pytest.approx(-0.011)


def test_error_response_raises() -> None:
    with pytest.raises(PPCHProtocolError, match="ERR#06"):
        check_response("ERR# 6")


def test_malformed_qprr_raises() -> None:
    with pytest.raises(PPCHProtocolError, match="Malformed QPRR"):
        parse_qprr("not a reading")


def test_pressure_conversion() -> None:
    assert pressure_to_psi(1, "MPA") == pytest.approx(145.0377377302)


def test_setpoint_limit() -> None:
    validate_setpoint(39.0, "MPA", 5700)
    with pytest.raises(ValueError, match="above the configured"):
        validate_setpoint(40.0, "MPA", 5700)


def test_negative_setpoint_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_setpoint(-1, "PSI", 5700)

"""PPCH command validation and response parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class PPCHProtocolError(RuntimeError):
    """Raised for an error or malformed response from the PPCH."""


class PressureUnit(StrEnum):
    PA = "Pa"
    HPA = "hPa"
    KPA = "kPa"
    MPA = "MPa"
    MBAR = "mbar"
    BAR = "bar"
    MMHG = "mmHg"
    MMWA = "mmWa"
    PSI = "psi"
    PSF = "psf"
    INHG = "inHg"
    INWA = "inWa"
    KCM2 = "kcm2"
    TORR = "Torr"
    MTOR = "mTor"


# Multipliers convert a value in the named unit to psi. Values use conventional
# pressure-unit definitions; PPCH user-defined units are intentionally excluded.
TO_PSI: dict[str, float] = {
    "PSI": 1.0,
    "PA": 0.00014503773773020923,
    "KPA": 0.14503773773020923,
    "MPA": 145.03773773020923,
    "BAR": 14.503773773020923,
    "MBAR": 0.014503773773020923,
    "HPA": 0.014503773773020923,
    "PSF": 1.0 / 144.0,
    "KCM2": 14.223343307,
    "INHG": 0.49115415223,
    "INWA": 0.036091190656,
    "MMHG": 0.0193367747,
    "MMWA": 0.0014223343307,
    "TORR": 0.0193367747,
    "MTOR": 0.0000193367747,
}

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_QPRR = re.compile(
    rf"^\s*(?P<ready>[^,]+),\s*"
    rf"(?P<pressure>{_NUMBER})\s+(?P<pressure_unit>\S+)\s+(?P<measurement_mode>[aAgG]),\s*"
    rf"(?P<rate>{_NUMBER})\s+(?P<rate_unit>\S+)/s,\s*"
    rf"(?P<atmosphere>{_NUMBER})\s+(?P<atmosphere_unit>\S+)\s+[aA]\s*$"
)
_ERROR = re.compile(r"^\s*ERR#\s*(?P<code>\d{1,2})\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class QPRRReading:
    ready: str
    pressure: float
    pressure_unit: str
    measurement_mode: str
    rate: float
    rate_unit: str
    atmosphere: float
    atmosphere_unit: str


def clean_response(response: bytes | str) -> str:
    if isinstance(response, bytes):
        try:
            response = response.decode("ascii")
        except UnicodeDecodeError as exception:
            raise PPCHProtocolError("PPCH response is not ASCII.") from exception
    return response.strip("\x00\r\n ")


def check_response(response: bytes | str) -> str:
    """Return a clean response or raise for a PPCH ERR# reply."""
    text = clean_response(response)
    if not text:
        raise PPCHProtocolError("PPCH returned an empty response.")
    if match := _ERROR.fullmatch(text):
        raise PPCHProtocolError(f"PPCH command failed with ERR#{int(match['code']):02d}.")
    return text


def parse_qprr(response: bytes | str) -> QPRRReading:
    text = check_response(response)
    match = _QPRR.fullmatch(text)
    if match is None:
        raise PPCHProtocolError(f"Malformed QPRR response: {text!r}")
    values = match.groupdict()
    return QPRRReading(
        ready=values["ready"].strip().upper(),
        pressure=float(values["pressure"]),
        pressure_unit=values["pressure_unit"],
        measurement_mode=values["measurement_mode"].lower(),
        rate=float(values["rate"]),
        rate_unit=values["rate_unit"],
        atmosphere=float(values["atmosphere"]),
        atmosphere_unit=values["atmosphere_unit"],
    )


def pressure_to_psi(value: float, unit: str) -> float:
    try:
        multiplier = TO_PSI[unit.upper()]
    except KeyError as exception:
        raise ValueError(
            f"Unsupported pressure unit for safety validation: {unit!r}"
        ) from exception
    return value * multiplier


def validate_setpoint(value: float, unit: str, maximum_psi: float) -> None:
    if value < 0:
        raise ValueError("Pressure setpoint cannot be negative.")
    value_psi = pressure_to_psi(value, unit)
    if value_psi > maximum_psi:
        raise ValueError(
            f"Requested pressure is {value_psi:.3f} psi, above the configured "
            f"{maximum_psi:.3f} psi limit."
        )


def format_number(value: float) -> str:
    """Format without exponent notation or unnecessary zeroes for PPCH commands."""
    return f"{value:.12f}".rstrip("0").rstrip(".")

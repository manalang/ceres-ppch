"""CERES component driver for a Fluke/DHI PPCH controller."""

from __future__ import annotations

import asyncio
from dataclasses import field
from datetime import timedelta
from re import compile
from typing import Annotated, Literal, override

from ceres import (
    Bound,
    Component,
    Connection,
    GroupedRegexParticle,
    Level,
    Message,
    ParseFailed,
    ParticleData,
    SplitByLine,
    action,
    query,
    routine,
    sieve,
)
from ceres.concurrency import sleep
from ceres.data import PositiveTimeDelta
from pydantic import Field as PydanticField

from .protocol import (
    PPCHProtocolError,
    PressureUnit,
    check_response,
    format_number,
    validate_setpoint,
)


class PPCHParticleData(ParticleData):
    ready: str
    pressure: float
    pressure_unit: str
    measurement_mode: str
    rate: float
    rate_unit: str
    atmosphere: float
    atmosphere_unit: str


class PPCHParticle(GroupedRegexParticle[PPCHParticleData]):
    type: Literal["fluke-ppch/qprr"] = "fluke-ppch/qprr"
    regex = compile(
        rb"^\s*(?P<ready>[^,]+),\s*"
        rb"(?P<pressure>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)\s+"
        rb"(?P<pressure_unit>\S+)\s+(?P<measurement_mode>[aAgG]),\s*"
        rb"(?P<rate>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)\s+"
        rb"(?P<rate_unit>\S+)/s,\s*"
        rb"(?P<atmosphere>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)\s+"
        rb"(?P<atmosphere_unit>\S+)\s+[aA]\s*$"
    )


class PPCHDriver(Component):
    """Poll, control, and log a PPCH over its COM1 RS-232 interface."""

    connection: Bound[Connection] | None = Connection.Field(
        splitter=SplitByLine(),
        suffix=b"\r\n",
        receive_timeout=None,
    )
    poll_interval: Annotated[
        PositiveTimeDelta,
        PydanticField(ge=timedelta(seconds=1), le=timedelta(minutes=10)),
    ] = timedelta(seconds=5)
    response_timeout: PositiveTimeDelta = timedelta(seconds=3)
    maximum_pressure_psi: Annotated[float, PydanticField(gt=0)] = 5700.0
    _command_lock: asyncio.Lock = field(init=False)
    _latest: PPCHParticleData | None = field(init=False, default=None)
    _unit: str | None = field(init=False, default=None)

    @override
    def __setup__(self) -> None:
        self._command_lock = asyncio.Lock()

    def _connection(self) -> Connection:
        connection = self.system.connections.get("connection")
        if connection is None or not connection.connected:
            raise RuntimeError("PPCH serial connection is not active.")
        return connection

    async def _command(self, command: str) -> str:
        """Perform one indivisible PPCH COM1 request/reply transaction."""
        async with self._command_lock:
            connection = self._connection()
            await connection.send(command.encode("ascii"))
            message = await connection.receive(
                direction="receive",
                timeout=self.response_timeout,
            )
            response = check_response(message.data)
            self.system.log.info(f"PPCH command {command!r} replied {response!r}.")
            return response

    @sieve(connection)
    async def parse_poll(self, message: Message) -> PPCHParticle | None:
        try:
            particle = PPCHParticle.from_message(message)
        except ParseFailed, PPCHProtocolError:
            return None
        self._latest = particle.data
        self._unit = particle.data.pressure_unit.upper()
        return particle

    @routine(restart="always", restart_delay=5)
    async def poll(self) -> None:
        while True:
            try:
                await self._command("QPRR")
            except RuntimeError, TimeoutError, PPCHProtocolError as exception:
                self.system.log.warning(f"PPCH poll failed: {exception}")
                self.system.alerts.emit(
                    Level.WARNING,
                    "fluke-ppch/poll-failed",
                    {"message": str(exception)},
                )
            await sleep(self.poll_interval)

    @query(poll=5)
    async def status(self) -> dict:
        if self._latest is None:
            return {
                "connected": bool(self.connection and self.connection.connected),
                "reading": None,
            }
        return {
            "connected": bool(self.connection and self.connection.connected),
            "reading": {
                "ready": self._latest.ready,
                "pressure": self._latest.pressure,
                "pressure_unit": self._latest.pressure_unit,
                "measurement_mode": self._latest.measurement_mode,
                "rate": self._latest.rate,
                "rate_unit": self._latest.rate_unit,
                "atmosphere": self._latest.atmosphere,
                "atmosphere_unit": self._latest.atmosphere_unit,
            },
        }

    @query
    async def instrument_status(self) -> dict:
        return {"status": await self._command("STAT")}

    @query
    async def target_pressure(self) -> dict:
        return {"target": await self._command("TP")}

    @query
    async def identify(self) -> dict:
        return {
            "serial_number": await self._command("SN"),
            "firmware": await self._command("VER"),
            "range": await self._command("RANGE"),
            "units": await self._command("UNIT"),
        }

    @action(permit="operate")
    async def set_pressure(self, pressure: float, unit: str | None = None) -> dict:
        selected_unit = (unit or self._unit or "PSI").upper()
        if self._unit is not None and selected_unit != self._unit:
            raise ValueError(
                f"Setpoint unit {selected_unit!r} does not match the PPCH unit {self._unit!r}. "
                "Change units first or omit the unit argument."
            )
        validate_setpoint(pressure, selected_unit, self.maximum_pressure_psi)
        response = await self._command(f"PS {format_number(pressure)}")
        return {"status": "ok", "target": pressure, "unit": selected_unit, "reply": response}

    @action(permit="operate")
    async def abort(self) -> dict:
        return {"status": "ok", "reply": await self._command("ABORT")}

    @action(permit="operate")
    async def vent(self) -> dict:
        return {"status": "ok", "reply": await self._command("VENT 1")}

    @action(permit="operate")
    async def stop_vent(self) -> dict:
        return {"status": "ok", "reply": await self._command("VENT 0")}

    @action(permit="operate")
    async def return_to_target(self) -> dict:
        return {"status": "ok", "reply": await self._command("RETURN")}

    @action(permit="operate")
    async def local_control(self) -> dict:
        return {"status": "ok", "reply": await self._command("LOCAL")}

    @action(permit="manage")
    async def set_units(self, unit: PressureUnit) -> dict:
        response = await self._command(f"UNIT {unit.value}")
        self._unit = unit.value.upper()
        return {"status": "ok", "unit": unit.value, "reply": response}

    @action(permit="manage")
    async def set_measurement_mode(self, mode: Literal["A", "G"]) -> dict:
        return {"status": "ok", "reply": await self._command(f"MMODE {mode}")}

    @action(permit="manage")
    async def set_control_mode(self, mode: Literal["0", "1", "1,0", "1,1", "2", "3"]) -> dict:
        return {"status": "ok", "reply": await self._command(f"MODE {mode}")}

    @action(permit="manage")
    async def set_stability(self, pressure_per_second: float) -> dict:
        if pressure_per_second <= 0:
            raise ValueError("Stability must be greater than zero.")
        reply = await self._command(f"SS {format_number(pressure_per_second)}")
        return {"status": "ok", "reply": reply}

    @action(permit="manage")
    async def set_ready_limit_percent(self, percent: float) -> dict:
        if not 0 < percent <= 100:
            raise ValueError("Ready limit must be greater than 0 and at most 100 percent.")
        reply = await self._command(f"RL% {format_number(percent)}")
        return {"status": "ok", "reply": reply}

    @action(permit="manage")
    async def set_upper_limit(self, pressure: float, unit: str | None = None) -> dict:
        selected_unit = (unit or self._unit or "PSI").upper()
        if self._unit is not None and selected_unit != self._unit:
            raise ValueError(
                f"Upper-limit unit {selected_unit!r} does not match the PPCH unit "
                f"{self._unit!r}. Change units first or omit the unit argument."
            )
        validate_setpoint(pressure, selected_unit, self.maximum_pressure_psi)
        reply = await self._command(f"UL {format_number(pressure)}")
        return {"status": "ok", "upper_limit": pressure, "unit": selected_unit, "reply": reply}

    @action(permit="manage")
    async def clear_errors(self) -> dict:
        return {"status": "ok", "reply": await self._command("*CLS")}

    @action(permit="manage")
    async def set_hold_limit(self, pressure: float) -> dict:
        if pressure <= 0:
            raise ValueError("Hold limit must be greater than zero.")
        reply = await self._command(f"HS {format_number(pressure)}")
        return {"status": "ok", "reply": reply}

    @action(permit="manage")
    async def set_autozero(self, enabled: bool) -> dict:
        reply = await self._command(f"AUTOZERO {int(enabled)}")
        return {"status": "ok", "enabled": enabled, "reply": reply}

    @action(permit="manage")
    async def set_range(self, range_name: Literal["IH", "IL", "X1H", "X1L", "X2H", "X2L"]) -> dict:
        """Select a range; the PPCH itself rejects this unless the system is vented."""
        reply = await self._command(f"RANGE {range_name}")
        return {"status": "ok", "range": range_name, "reply": reply}

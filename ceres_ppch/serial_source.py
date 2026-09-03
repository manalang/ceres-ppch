"""Asynchronous CERES Source adapter for a pyserial port."""

from __future__ import annotations

import asyncio
from dataclasses import field
from typing import Literal, override

import serial
from ceres.connection import Source
from ceres.data import NonBlankStr
from pydantic import Field as PydanticField


class SerialSource(Source):
    """A CERES byte source backed by pyserial.

    Blocking pyserial calls run in worker threads. Short pyserial read timeouts are
    hidden from CERES so an idle, request/reply instrument is not treated as disconnected.
    """

    port: NonBlankStr
    baudrate: int = PydanticField(default=2400, gt=0)
    bytesize: Literal[7, 8] = 7
    parity: Literal["N", "E", "O"] = "E"
    stopbits: Literal[1, 2] = 1
    read_timeout: float = PydanticField(default=0.25, gt=0)
    write_timeout: float = PydanticField(default=2.0, gt=0)
    _serial: serial.Serial | None = field(init=False, default=None)
    _closing: bool = field(init=False, default=False)

    @property
    @override
    def uri(self) -> str:
        return f"serial://{self.port}"

    @override
    async def connect(self) -> bool:
        if self._serial is not None and self._serial.is_open:
            return True
        self._closing = False
        try:
            self._serial = await asyncio.to_thread(
                serial.Serial,
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.read_timeout,
                write_timeout=self.write_timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except OSError, serial.SerialException:
            self._serial = None
            return False
        return True

    @override
    async def disconnect(self) -> None:
        port, self._serial = self._serial, None
        self._closing = True
        if port is None:
            return
        try:
            port.cancel_read()
        except AttributeError, OSError, serial.SerialException:
            pass
        try:
            await asyncio.to_thread(port.close)
        except OSError, serial.SerialException:
            pass

    @override
    async def send(self, data: bytes) -> bytes | None:
        port = self._serial
        if port is None or not port.is_open:
            return None
        try:
            written = await asyncio.to_thread(port.write, data)
            await asyncio.to_thread(port.flush)
        except OSError, serial.SerialException, serial.SerialTimeoutException:
            return None
        return data if written == len(data) else None

    @override
    async def receive(self, count: int) -> bytes | None:
        # CERES interprets b"" as a lost connection. A PPCH is normally silent
        # between commands, so keep reading across pyserial timeouts.
        while not self._closing:
            port = self._serial
            if port is None or not port.is_open:
                return None
            try:
                data = await asyncio.to_thread(port.read, count)
            except OSError, serial.SerialException:
                return None
            if data:
                return data
        return None

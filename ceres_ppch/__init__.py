"""CERES driver for Fluke/DHI PPCH pressure controllers."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .driver import PPCHDriver, PPCHParticle, PPCHParticleData
    from .serial_source import SerialSource

__all__ = ["PPCHDriver", "PPCHParticle", "PPCHParticleData", "SerialSource"]


def __getattr__(name: str):
    """Load CERES-dependent classes only when requested."""
    if name in {"PPCHDriver", "PPCHParticle", "PPCHParticleData"}:
        from . import driver

        return getattr(driver, name)
    if name == "SerialSource":
        from .serial_source import SerialSource

        return SerialSource
    raise AttributeError(name)

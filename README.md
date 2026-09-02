# CERES PPCH Driver

A CERES driver for monitoring and controlling a Fluke/DHI PPCH pressure controller through
the COM1 RS-232 interface. The initial hardware target is a PPCH SI A40M with a site safety
limit of 5,700 psi.

## Features

- Native configurable serial transport for Windows, Linux, and macOS.
- Configurable polling from 1 second through 10 minutes; default 5 seconds.
- `QPRR` polling records ready state, pressure, pressure rate, measurement mode, and
  atmospheric pressure as structured CERES particles.
- All transmitted commands and received replies remain in CERES's raw message log.
- A single transaction lock enforces the PPCH rule that every COM1 reply must be read before
  another command is sent.
- Local setpoint and upper-limit validation against the configured maximum pressure.
- CERES queries and permission-gated operating/configuration actions.

## Safety

This software does not replace rated pressure hardware, relief devices, PPCH internal limits,
or an operator following the PPCH manual. Confirm the configured port, serial format, active
pressure unit, measurement mode, range, test assembly rating, and pressure limit before
enabling remote control.

The driver defaults to a 5,700 psi software ceiling. Set-pressure and upper-limit requests are
converted to psi and rejected if they exceed that ceiling. User-defined PPCH pressure units are
not accepted for safety validation.

## Install

Python 3.13 or newer and a working CERES installation are required.

```sh
git clone https://github.com/manalang/ceres-ppch.git
cd ceres-ppch
python -m venv .venv
```

Activate the environment, then install:

```sh
python -m pip install -e .
```

On Linux, ensure the service account can open the serial device (often by joining the
`dialout` group). Do not run CERES as root solely to access a serial port.

## Configure

Copy the example and edit the port name and authentication secret:

```sh
cp ceres.yaml.example ceres.yaml
```

Typical port names:

- Windows: `COM4`
- Linux: `/dev/ttyUSB0` or a stable `/dev/serial/by-id/...` path
- macOS: `/dev/cu.usbserial-...`

The example uses the documented PPCH COM1 default `2400,E,7,1`. Match these values to the
actual front-panel COM1 configuration. Hardware flow control is disabled because the PPCH does
not support or require it.

`poll-interval` accepts any duration from `1s` to `10m`.

## Run

```sh
ceres run all
```

Open `http://localhost:8080` for the CERES console. The SQLite database stores structured
particles, raw messages, events, alerts, and procedure history.

## Exposed procedures

Read-only queries:

- `status`: latest polled values and connection state
- `instrument_status`: `STAT`
- `target_pressure`: `TP`
- `identify`: `SN`, `VER`, `RANGE`, and `UNIT`

Operator actions:

- `set_pressure`: validated `PS`
- `abort`: `ABORT`
- `vent` / `stop_vent`: start or stop `VENT`
- `return_to_target`: `RETURN`
- `local_control`: `LOCAL`

Manager-only configuration actions:

- `set_units`: `UNIT`
- `set_measurement_mode`: `MMODE`
- `set_control_mode`: `MODE`
- `set_stability`: `SS`
- `set_hold_limit`: `HS`
- `set_ready_limit_percent`: `RL%`
- `set_upper_limit`: validated `UL`
- `set_autozero`: `AUTOZERO`
- `set_range`: `RANGE` (the PPCH requires the system to be vented)
- `clear_errors`: `*CLS`

The PPCH enters remote mode when it receives a command. Returning to local control aborts active
pressure generation, as documented by the manufacturer.

## Development

```sh
python -m pip install -e '.[test]'
pytest
ruff check .
ruff format --check .
```

Tests intentionally exercise parsing and safety validation without requiring a pressure
controller. Hardware-in-the-loop tests should start with the PPCH disconnected from a test
volume or otherwise placed in a verified safe configuration.

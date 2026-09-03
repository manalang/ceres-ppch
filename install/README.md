# Easy installers

These installers create a self-contained, per-user CERES PPCH installation. They do not rely
on or modify an existing system-wide CERES installation.

Both installers:

1. Install `uv` when it is not already available.
2. Install an isolated Python 3.14 runtime.
3. Create a fresh virtual environment, replacing an older installer-managed environment.
4. Install the current public `manalang/ceres-ppch` source and its compatible CERES release.
5. Preserve an existing database and, by default, an existing `ceres.yaml` configuration.
6. Interactively configure direct serial or raw TCP serial-server operation.
7. Create start and update launchers.

## Windows

Open PowerShell and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
Invoke-WebRequest `
  https://raw.githubusercontent.com/manalang/ceres-ppch/main/install/install.ps1 `
  -OutFile "$env:TEMP\install-ceres-ppch.ps1"
& "$env:TEMP\install-ceres-ppch.ps1"
```

The default installation directory is `%LOCALAPPDATA%\CeresPPCH`. Start it afterward with
`Start-CeresPPCH.cmd` in that directory.

For an unattended TCP installation:

```powershell
& "$env:TEMP\install-ceres-ppch.ps1" `
  -NonInteractive -Transport tcp -TcpHost 192.168.1.50 -TcpPort 4001
```

## macOS or Linux

Open Terminal and run:

```sh
curl -LsSf \
  https://raw.githubusercontent.com/manalang/ceres-ppch/main/install/install.sh \
  -o /tmp/install-ceres-ppch.sh
sh /tmp/install-ceres-ppch.sh
```

The default installation directory is `~/.local/share/ceres-ppch`. Start it afterward with:

```sh
~/.local/share/ceres-ppch/start.sh
```

An unattended TCP installation can use environment variables:

```sh
CERES_PPCH_NONINTERACTIVE=1 \
CERES_PPCH_TRANSPORT=tcp \
CERES_PPCH_TCP_HOST=192.168.1.50 \
CERES_PPCH_TCP_PORT=4001 \
sh /tmp/install-ceres-ppch.sh
```

The following optional environment variables are also recognized:
`CERES_PPCH_HOME`, `CERES_PPCH_POLL_INTERVAL`, `CERES_PPCH_MAX_PRESSURE_PSI`,
`CERES_PPCH_SERIAL_PORT`, `CERES_PPCH_BAUDRATE`, `CERES_PPCH_BYTESIZE`,
`CERES_PPCH_PARITY`, and `CERES_PPCH_STOPBITS`.

## Existing or old CERES installations

The installer-managed virtual environment contains the exact CERES dependency range declared
by `ceres-ppch`. An absent, older, or newer system-wide CERES installation is ignored. Rerunning
the installer recreates that environment and upgrades the driver while preserving configuration
and the SQLite database.


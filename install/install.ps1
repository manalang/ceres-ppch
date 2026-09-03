# Interactive per-user installer for Windows PowerShell 5.1 and newer.
[CmdletBinding()]
param(
    [ValidateSet("tcp", "serial")]
    [string]$Transport,
    [string]$TcpHost,
    [int]$TcpPort = 4001,
    [string]$SerialPort = "COM4",
    [int]$BaudRate = 2400,
    [ValidateSet(7, 8)]
    [int]$ByteSize = 7,
    [ValidateSet("N", "E", "O")]
    [string]$Parity = "E",
    [ValidateSet(1, 2)]
    [int]$StopBits = 1,
    [string]$PollInterval = "5s",
    [double]$MaximumPressurePsi = 5700,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepositoryArchive = "https://github.com/manalang/ceres-ppch/archive/refs/heads/main.zip"
$UvInstaller = "https://astral.sh/uv/install.ps1"
$InstallDir = if ($env:CERES_PPCH_HOME) {
    $env:CERES_PPCH_HOME
} else {
    Join-Path $env:LOCALAPPDATA "CeresPPCH"
}
$VenvDir = Join-Path $InstallDir "venv"
$ConfigFile = Join-Path $InstallDir "ceres.yaml"

function Read-Default([string]$Prompt, [string]$Default) {
    if ($NonInteractive) { return $Default }
    $Value = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
    return $Value
}

function Quote-Yaml([string]$Value) {
    return ConvertTo-Json $Value -Compress
}

Write-Host "Installing CERES PPCH into $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $Uv) {
    $KnownUv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $KnownUv) { $Uv = Get-Item $KnownUv }
}
if (-not $Uv) {
    Write-Host "Installing uv..."
    $UvScript = Join-Path $env:TEMP "ceres-ppch-install-uv.ps1"
    Invoke-WebRequest -UseBasicParsing -Uri $UvInstaller -OutFile $UvScript
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UvScript
    Remove-Item -Force $UvScript
    $KnownUv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $KnownUv) { $Uv = Get-Item $KnownUv }
}
if (-not $Uv) { throw "uv installation completed, but uv.exe could not be found." }
$UvExe = $Uv.Source
if (-not $UvExe) { $UvExe = $Uv.FullName }

Write-Host "Installing an isolated Python 3.14 runtime..."
& $UvExe python install 3.14
if ($LASTEXITCODE -ne 0) { throw "Python 3.14 installation failed." }
& $UvExe venv --python 3.14 --clear $VenvDir
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "Installing the current CERES PPCH driver and compatible CERES version..."
& $UvExe pip install --python $PythonExe --upgrade $RepositoryArchive
if ($LASTEXITCODE -ne 0) { throw "CERES PPCH installation failed." }

$Configure = $true
if (Test-Path $ConfigFile) {
    $Keep = Read-Default "Keep the existing configuration? (yes/no)" "yes"
    if ($Keep -match "^(y|yes)$") { $Configure = $false }
}

if ($Configure) {
    if (-not $Transport) { $Transport = Read-Default "Connection type: tcp or serial" "tcp" }
    if (-not $NonInteractive) {
        $PollInterval = Read-Default "Polling interval (1s to 10m)" $PollInterval
        $MaximumPressurePsi = [double](Read-Default "Maximum pressure in psi" "$MaximumPressurePsi")
    }
    $SecretBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($SecretBytes)
    $Secret = [Convert]::ToBase64String($SecretBytes)
    $DatabasePath = Join-Path $InstallDir "database.sqlite"

    if ($Transport -eq "tcp") {
        if (-not $TcpHost) { $TcpHost = Read-Default "Serial server hostname or IP" "192.168.1.50" }
        if (-not $NonInteractive) {
            $TcpPort = [int](Read-Default "Serial server raw TCP port" "$TcpPort")
        }
        $Connection = @"
        source:
          class: ceres.connection.TCPSource
          arguments:
            host: $(Quote-Yaml $TcpHost)
            port: $TcpPort
        reconnect-schedule:
          type: interval
          interval: 2s
          multiplier: 2
          max: 1m
"@
    } else {
        if (-not $NonInteractive) {
            $SerialPort = Read-Default "Serial device" $SerialPort
            $BaudRate = [int](Read-Default "Baud rate" "$BaudRate")
            $ByteSize = [int](Read-Default "Data bits" "$ByteSize")
            $Parity = Read-Default "Parity (N, E, or O)" $Parity
            $StopBits = [int](Read-Default "Stop bits" "$StopBits")
        }
        $Connection = @"
        source:
          class: ceres_ppch.SerialSource
          arguments:
            port: $(Quote-Yaml $SerialPort)
            baudrate: $BaudRate
            bytesize: $ByteSize
            parity: $(Quote-Yaml $Parity)
            stopbits: $StopBits
            read-timeout: 0.25
            write-timeout: 2
"@
    }

    $Configuration = @"
service:
  name: ceres-ppch
server:
  port: 8080
  authentication:
    secret: $(Quote-Yaml $Secret)
database:
  type: sqlite
  path: $(Quote-Yaml $DatabasePath)
logging:
  output: info
  events: true
components:
  - name: ppch
    class: ceres_ppch.PPCHDriver
    arguments:
      poll-interval: $(Quote-Yaml $PollInterval)
      response-timeout: 3s
      maximum-pressure-psi: $MaximumPressurePsi
      connection:
$Connection
"@
    [System.IO.File]::WriteAllText($ConfigFile, $Configuration, [System.Text.UTF8Encoding]::new($false))
}

$StartScript = @"
Set-Location $(Quote-Yaml $InstallDir)
`$env:CERES_PYTHON = $(Quote-Yaml $PythonExe)
`$env:VIRTUAL_ENV = $(Quote-Yaml $VenvDir)
& $(Quote-Yaml $PythonExe) -m ceres run all
"@
[System.IO.File]::WriteAllText(
    (Join-Path $InstallDir "Start-CeresPPCH.ps1"),
    $StartScript,
    [System.Text.UTF8Encoding]::new($false)
)
$StartCmd = "@powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\Start-CeresPPCH.ps1`"`r`n"
[System.IO.File]::WriteAllText((Join-Path $InstallDir "Start-CeresPPCH.cmd"), $StartCmd)

$UpdateScript = @"
& $(Quote-Yaml $UvExe) pip install --python $(Quote-Yaml $PythonExe) --upgrade $(Quote-Yaml $RepositoryArchive)
if (`$LASTEXITCODE -ne 0) { throw "CERES PPCH update failed." }
"@
[System.IO.File]::WriteAllText(
    (Join-Path $InstallDir "Update-CeresPPCH.ps1"),
    $UpdateScript,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "Installation complete."
Write-Host "Configuration: $ConfigFile"
Write-Host "Start CERES PPCH: $InstallDir\Start-CeresPPCH.cmd"
Write-Host "Update later:       $InstallDir\Update-CeresPPCH.ps1"
Write-Host "Web console:        http://localhost:8080"

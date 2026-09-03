#!/bin/sh
# Interactive per-user installer for macOS and Linux.
set -eu

REPOSITORY_ARCHIVE="https://github.com/manalang/ceres-ppch/archive/refs/heads/main.zip"
UV_INSTALLER="https://astral.sh/uv/install.sh"
INSTALL_DIR="${CERES_PPCH_HOME:-${HOME}/.local/share/ceres-ppch}"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_FILE="${INSTALL_DIR}/ceres.yaml"

say() {
    printf '%s\n' "$*"
}

prompt() {
    prompt_text=$1
    default_value=$2
    if [ -n "${CERES_PPCH_NONINTERACTIVE:-}" ]; then
        printf '%s' "$default_value"
        return
    fi
    printf '%s [%s]: ' "$prompt_text" "$default_value" >&2
    IFS= read -r entered || entered=""
    if [ -n "$entered" ]; then
        printf '%s' "$entered"
    else
        printf '%s' "$default_value"
    fi
}

quote_yaml() {
    "$PYTHON_BIN" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
    elif [ -x "${HOME}/.local/bin/uv" ]; then
        printf '%s' "${HOME}/.local/bin/uv"
    elif [ -x "${HOME}/.cargo/bin/uv" ]; then
        printf '%s' "${HOME}/.cargo/bin/uv"
    fi
}

case "$(uname -s)" in
    Darwin|Linux) ;;
    *)
        say "This installer supports macOS and Linux. Use install.ps1 on Windows."
        exit 1
        ;;
esac

say "Installing CERES PPCH into ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"

UV_BIN=$(find_uv || true)
if [ -z "$UV_BIN" ]; then
    say "Installing uv..."
    UV_SCRIPT=$(mktemp "${TMPDIR:-/tmp}/ceres-ppch-uv.XXXXXX")
    trap 'rm -f "$UV_SCRIPT"' EXIT HUP INT TERM
    curl -LsSf "$UV_INSTALLER" -o "$UV_SCRIPT"
    sh "$UV_SCRIPT"
    rm -f "$UV_SCRIPT"
    trap - EXIT HUP INT TERM
    UV_BIN=$(find_uv || true)
fi
if [ -z "$UV_BIN" ]; then
    say "uv installation completed, but the uv executable could not be found."
    exit 1
fi

say "Installing an isolated Python 3.14 runtime..."
"$UV_BIN" python install 3.14
"$UV_BIN" venv --python 3.14 --clear "$VENV_DIR"
PYTHON_BIN="${VENV_DIR}/bin/python"

say "Installing the current CERES PPCH driver and compatible CERES version..."
"$UV_BIN" pip install --python "$PYTHON_BIN" --upgrade "$REPOSITORY_ARCHIVE"

RECONFIGURE="yes"
if [ -f "$CONFIG_FILE" ]; then
    RECONFIGURE=$(prompt "Keep the existing configuration? (yes/no)" "yes")
    case "$RECONFIGURE" in
        y|Y|yes|YES|Yes) RECONFIGURE="no" ;;
        *) RECONFIGURE="yes" ;;
    esac
fi

if [ "$RECONFIGURE" = "yes" ]; then
    TRANSPORT=${CERES_PPCH_TRANSPORT:-$(prompt "Connection type: tcp or serial" "tcp")}
    POLL_INTERVAL=${CERES_PPCH_POLL_INTERVAL:-$(prompt "Polling interval (1s to 10m)" "5s")}
    MAX_PRESSURE=${CERES_PPCH_MAX_PRESSURE_PSI:-$(prompt "Maximum pressure in psi" "5700")}
    SECRET=$($PYTHON_BIN -c 'import secrets; print(secrets.token_urlsafe(32))')

    case "$TRANSPORT" in
        tcp|TCP)
            TCP_HOST=${CERES_PPCH_TCP_HOST:-$(prompt "Serial server hostname or IP" "192.168.1.50")}
            TCP_PORT=${CERES_PPCH_TCP_PORT:-$(prompt "Serial server raw TCP port" "4001")}
            cat >"$CONFIG_FILE" <<EOF
service:
  name: ceres-ppch
server:
  port: 8080
  authentication:
    secret: $(quote_yaml "$SECRET")
database:
  type: sqlite
  path: $(quote_yaml "${INSTALL_DIR}/database.sqlite")
logging:
  output: info
  events: true
components:
  - name: ppch
    class: ceres_ppch.PPCHDriver
    arguments:
      poll-interval: $(quote_yaml "$POLL_INTERVAL")
      response-timeout: 3s
      maximum-pressure-psi: $MAX_PRESSURE
      connection:
        source:
          class: ceres.connection.TCPSource
          arguments:
            host: $(quote_yaml "$TCP_HOST")
            port: $TCP_PORT
        reconnect-schedule:
          type: interval
          interval: 2s
          multiplier: 2
          max: 1m
EOF
            ;;
        serial|SERIAL)
            SERIAL_PORT=${CERES_PPCH_SERIAL_PORT:-$(prompt "Serial device" "/dev/ttyUSB0")}
            BAUDRATE=${CERES_PPCH_BAUDRATE:-$(prompt "Baud rate" "2400")}
            BYTESIZE=${CERES_PPCH_BYTESIZE:-$(prompt "Data bits" "7")}
            PARITY=${CERES_PPCH_PARITY:-$(prompt "Parity (N, E, or O)" "E")}
            STOPBITS=${CERES_PPCH_STOPBITS:-$(prompt "Stop bits" "1")}
            cat >"$CONFIG_FILE" <<EOF
service:
  name: ceres-ppch
server:
  port: 8080
  authentication:
    secret: $(quote_yaml "$SECRET")
database:
  type: sqlite
  path: $(quote_yaml "${INSTALL_DIR}/database.sqlite")
logging:
  output: info
  events: true
components:
  - name: ppch
    class: ceres_ppch.PPCHDriver
    arguments:
      poll-interval: $(quote_yaml "$POLL_INTERVAL")
      response-timeout: 3s
      maximum-pressure-psi: $MAX_PRESSURE
      connection:
        source:
          class: ceres_ppch.SerialSource
          arguments:
            port: $(quote_yaml "$SERIAL_PORT")
            baudrate: $BAUDRATE
            bytesize: $BYTESIZE
            parity: $(quote_yaml "$PARITY")
            stopbits: $STOPBITS
            read-timeout: 0.25
            write-timeout: 2
EOF
            ;;
        *)
            say "Connection type must be tcp or serial."
            exit 1
            ;;
    esac
    chmod 600 "$CONFIG_FILE"
fi

cat >"${INSTALL_DIR}/start.sh" <<EOF
#!/bin/sh
set -eu
cd $(quote_yaml "$INSTALL_DIR")
export CERES_PYTHON=$(quote_yaml "$PYTHON_BIN")
export VIRTUAL_ENV=$(quote_yaml "$VENV_DIR")
exec $(quote_yaml "$PYTHON_BIN") -m ceres run all
EOF
chmod +x "${INSTALL_DIR}/start.sh"

cat >"${INSTALL_DIR}/update.sh" <<EOF
#!/bin/sh
set -eu
exec $(quote_yaml "$UV_BIN") pip install --python $(quote_yaml "$PYTHON_BIN") --upgrade $(quote_yaml "$REPOSITORY_ARCHIVE")
EOF
chmod +x "${INSTALL_DIR}/update.sh"

say ""
say "Installation complete."
say "Configuration: ${CONFIG_FILE}"
say "Start CERES PPCH: ${INSTALL_DIR}/start.sh"
say "Update later:       ${INSTALL_DIR}/update.sh"
say "Web console:        http://localhost:8080"

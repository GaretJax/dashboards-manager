#!/usr/bin/env bash
set -Eeuo pipefail

MANAGER_URL={{ manager_url | safe }}
SCREEN_TOKEN={{ screen_token | safe }}
WHEEL_URL={{ wheel_url | safe }}
INSTALL_URL={{ install_url | safe }}
DEFAULT_CONFIG_NAME={{ default_config_name | safe }}

fail() {
    printf 'kiosk-agent install failed: %s\n' "$1" >&2
    exit 1
}

print_command() {
    printf '+'
    printf ' %q' "$@"
    printf '\n'
}

run_command() {
    print_command "$@"
    "$@"
}

if [[ -z "${BASH_VERSION:-}" ]]; then
    fail "run this installer with bash"
fi

if [[ "$(id -u)" -eq 0 ]]; then
    TARGET_USER="${KIOSK_AGENT_USER:-${SUDO_USER:-}}"
    [[ -n "$TARGET_USER" ]] || fail "set KIOSK_AGENT_USER when running as root"
else
    TARGET_USER="${KIOSK_AGENT_USER:-${USER:-}}"
fi

id "$TARGET_USER" >/dev/null 2>&1 || fail "unknown target user: $TARGET_USER"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || fail "target home unavailable"

CONFIG_NAME="${KIOSK_AGENT_CONFIG_NAME:-}"
if [[ -z "$CONFIG_NAME" && -r /dev/tty ]]; then
    read -r -p "Config name [${DEFAULT_CONFIG_NAME}]: " CONFIG_NAME </dev/tty
fi
CONFIG_NAME="${CONFIG_NAME:-$DEFAULT_CONFIG_NAME}"
[[ "$CONFIG_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] ||
    fail "invalid config name: $CONFIG_NAME"
CONFIG_PATH="$TARGET_HOME/.config/kiosk-agent/${CONFIG_NAME}.toml"

if [[ ! -r /etc/os-release ]]; then
    fail "/etc/os-release is unavailable"
fi
# shellcheck disable=SC1091
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
*" debian "* | *" ubuntu "* | *" linuxmint "*) ;;
*) fail "only Debian-family systems are supported" ;;
esac

if ! command -v apt-get >/dev/null 2>&1; then
    fail "apt-get is required"
fi
if [[ "$(id -u)" -eq 0 ]]; then
    APT=(apt-get)
else
    command -v sudo >/dev/null 2>&1 || fail "sudo is required"
    APT=(sudo apt-get)
fi
run_command "${APT[@]}" update

APT_PACKAGES=(ca-certificates curl python3 labwc wtype cec-utils)
if dpkg-query -W -f='${Status}' chromium 2>/dev/null |
    grep -q 'install ok installed'; then
    :
elif ! apt-cache policy chromium 2>/dev/null |
    grep -q '^  Candidate: [^ (]'; then
    fail "an apt Chromium package is required; snap Chromium is unsupported"
else
    APT_PACKAGES+=(chromium)
fi
run_command "${APT[@]}" install -y "${APT_PACKAGES[@]}"

if getent group video >/dev/null 2>&1 && [[ "$(id -u)" -eq 0 ]]; then
    usermod -aG video "$TARGET_USER" || true
fi

run_target() {
    print_command "$@"
    if [[ "$(id -u)" -eq 0 ]]; then
        runuser -u "$TARGET_USER" -- env HOME="$TARGET_HOME" \
            PATH="$TARGET_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" "$@"
    else
        env HOME="$TARGET_HOME" \
            PATH="$TARGET_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" "$@"
    fi
}

if ! run_target bash -lc 'command -v uv' >/dev/null 2>&1; then
    run_target bash -c 'curl --fail --silent --show-error --location \
        https://astral.sh/uv/install.sh | sh'
fi
run_target uv tool install --force "$WHEEL_URL"
run_target kiosk-agent --version

BOOTSTRAP=(
    kiosk-agent bootstrap
    --manager "$MANAGER_URL"
    --screen "$SCREEN_TOKEN"
    --config "$CONFIG_PATH"
)
status=0
if [[ -r /dev/tty ]]; then
    run_target "${BOOTSTRAP[@]}" </dev/tty || status=$?
else
    run_target "${BOOTSTRAP[@]}" --non-interactive || status=$?
fi
if ((status != 0)); then
    printf '\nBootstrap failed. Check agent logs:\n' >&2
    printf '  ' >&2
    printf '%q ' "$TARGET_HOME/.local/bin/kiosk-agent" service logs \
        --config "$CONFIG_PATH" --scope user --lines 200 >&2
    printf '\n' >&2
    printf 'Retry bootstrap with:\n' >&2
    printf '  curl -fsSL %q | bash\n' "$INSTALL_URL" >&2
    printf 'Or retry directly with:\n' >&2
    printf '  ' >&2
    printf '%q ' "$TARGET_HOME/.local/bin/kiosk-agent" bootstrap \
        --manager "$MANAGER_URL" --screen "$SCREEN_TOKEN" \
        --config "$CONFIG_PATH" --force >&2
    printf '\n' >&2
    exit "$status"
fi

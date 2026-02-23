#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="pixeldock32"
REPO_DIR_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_TEMPLATE_REL="systemd/pixeldock32.service"
HEALTHCHECK_SERVICE_TEMPLATE_REL="systemd/pixeldock32-healthcheck.service"
HEALTHCHECK_TIMER_TEMPLATE_REL="systemd/pixeldock32-healthcheck.timer"
TARGET_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
HEALTHCHECK_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}-healthcheck.service"
HEALTHCHECK_TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}-healthcheck.timer"

usage() {
  cat <<USAGE
Verwendung:
  sudo ./scripts/manage-autostart.sh enable [--repo-dir /pfad/zu/PixelDock32] [--user <linux-user>] [--group <linux-group>]
  sudo ./scripts/manage-autostart.sh disable
  ./scripts/manage-autostart.sh status
  ./scripts/manage-autostart.sh logs

Aktionen:
  enable   Installiert/aktualisiert den systemd-Service und aktiviert den Autostart.
  disable  Deaktiviert den Autostart und stoppt den Service.
  status   Zeigt den aktuellen Service-Status.
  logs     Zeigt die letzten 100 Journal-Logs des Services.
USAGE
}

require_root_for_mutation() {
  local action="$1"
  if [[ "${action}" == "enable" || "${action}" == "disable" ]]; then
    if [[ "${EUID}" -ne 0 ]]; then
      echo "Fehler: '${action}' muss mit sudo ausgeführt werden." >&2
      exit 1
    fi
  fi
}

make_service_file() {
  local repo_dir="$1"
  local user="$2"
  local group="$3"

  local source_template="${repo_dir}/${SERVICE_TEMPLATE_REL}"
  if [[ ! -f "${source_template}" ]]; then
    echo "Fehler: Service-Template nicht gefunden: ${source_template}" >&2
    exit 1
  fi

  sed \
    -e "s|^User=.*|User=${user}|" \
    -e "s|^Group=.*|Group=${group}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${repo_dir}|" \
    -e "s|^EnvironmentFile=.*|EnvironmentFile=${repo_dir}/.env|" \
    -e "s|^ExecStart=.*|ExecStart=${repo_dir}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000|" \
    "${source_template}" > "${TARGET_SERVICE_FILE}"
}


make_healthcheck_files() {
  local repo_dir="$1"

  local health_service_template="${repo_dir}/${HEALTHCHECK_SERVICE_TEMPLATE_REL}"
  local health_timer_template="${repo_dir}/${HEALTHCHECK_TIMER_TEMPLATE_REL}"

  if [[ ! -f "${health_service_template}" || ! -f "${health_timer_template}" ]]; then
    echo "Fehler: Healthcheck-Templates fehlen im Repo." >&2
    exit 1
  fi

  sed \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${repo_dir}|" \
    -e "s|^ExecStart=.*|ExecStart=${repo_dir}/scripts/pixeldock32-healthcheck.sh|" \
    "${health_service_template}" > "${HEALTHCHECK_SERVICE_FILE}"

  cp "${health_timer_template}" "${HEALTHCHECK_TIMER_FILE}"
}
enable_autostart() {
  local repo_dir="$1"
  local user="$2"
  local group="$3"

  if [[ ! -d "${repo_dir}" ]]; then
    echo "Fehler: Repo-Verzeichnis existiert nicht: ${repo_dir}" >&2
    exit 1
  fi

  make_service_file "${repo_dir}" "${user}" "${group}"
  make_healthcheck_files "${repo_dir}"

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
  systemctl enable --now "${SERVICE_NAME}-healthcheck.timer"

  echo "Autostart wurde aktiviert, Service neu gestartet und Healthcheck-Timer aktiviert."
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
}

disable_autostart() {
  systemctl disable --now "${SERVICE_NAME}-healthcheck.timer" || true
  systemctl disable --now "${SERVICE_NAME}"
  echo "Autostart wurde deaktiviert, Timer beendet und Service gestoppt."
}

show_status() {
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
}

show_logs() {
  journalctl -u "${SERVICE_NAME}" -n 100 --no-pager
}

ACTION="${1:-}"
shift || true

REPO_DIR="${REPO_DIR_DEFAULT}"
SERVICE_USER="${SUDO_USER:-$(id -un)}"
SERVICE_GROUP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="$2"
      shift 2
      ;;
    --user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --group)
      SERVICE_GROUP="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unbekannte Option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  echo "Fehler: Benutzer '${SERVICE_USER}' existiert nicht." >&2
  exit 1
fi

if [[ -z "${SERVICE_GROUP}" ]]; then
  SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"
fi

case "${ACTION}" in
  enable)
    require_root_for_mutation "enable"
    enable_autostart "${REPO_DIR}" "${SERVICE_USER}" "${SERVICE_GROUP}"
    ;;
  disable)
    require_root_for_mutation "disable"
    disable_autostart
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    echo "Unbekannte Aktion: ${ACTION}" >&2
    usage
    exit 1
    ;;
esac

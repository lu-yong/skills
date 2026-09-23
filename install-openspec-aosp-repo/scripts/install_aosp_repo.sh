#!/usr/bin/env bash
set -euo pipefail

MODE="install"
PROJECT_ROOT=""
SOURCE_DIR=""
REPO_URL="https://github.com/lu-yong/openspec-schemas"
SCHEMA_NAME="aosp-repo"
SET_SCHEMA=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  install_aosp_repo.sh --project-root <path> [options]

Options:
  --mode install|upgrade
  --project-root <path>
  --source-dir <path>
  --repo-url <url>
  --no-set-schema
  --help
EOF
}

log() {
  printf '[aosp-repo-installer] %s\n' "$*"
}

fail() {
  printf '[aosp-repo-installer] ERROR: %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --project-root)
      PROJECT_ROOT="${2:-}"
      shift 2
      ;;
    --source-dir)
      SOURCE_DIR="${2:-}"
      shift 2
      ;;
    --repo-url)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --no-set-schema)
      SET_SCHEMA=0
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

[[ -n "${PROJECT_ROOT}" ]] || fail "--project-root is required"
[[ "${MODE}" == "install" || "${MODE}" == "upgrade" ]] || fail "--mode must be install or upgrade"

PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"
OPENSPEC_DIR="${PROJECT_ROOT}/openspec"
SCHEMAS_DIR="${OPENSPEC_DIR}/schemas"
TARGET_DIR="${SCHEMAS_DIR}/${SCHEMA_NAME}"
CONFIG_FILE="${OPENSPEC_DIR}/config.yaml"

[[ -d "${OPENSPEC_DIR}" ]] || fail "Missing ${OPENSPEC_DIR}. Run 'openspec init' first."

TEMP_DIR=""
cleanup() {
  if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT

if [[ -n "${SOURCE_DIR}" ]]; then
  SOURCE_DIR="$(cd "${SOURCE_DIR}" && pwd)"
else
  command_exists git || fail "git is required when --source-dir is not provided"
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openspec-schemas.XXXXXX")"
  log "Cloning ${REPO_URL} into ${TEMP_DIR}"
  git clone --depth 1 "${REPO_URL}" "${TEMP_DIR}" >/dev/null
  SOURCE_DIR="${TEMP_DIR}"
fi

UPSTREAM_DIR="${SOURCE_DIR}/${SCHEMA_NAME}"
[[ -d "${UPSTREAM_DIR}" ]] || fail "Missing upstream schema directory: ${UPSTREAM_DIR}"

mkdir -p "${SCHEMAS_DIR}"

if [[ "${MODE}" == "install" && -e "${TARGET_DIR}" ]]; then
  fail "${TARGET_DIR} already exists. Use --mode upgrade to replace it."
fi

if [[ "${MODE}" == "upgrade" && ! -e "${TARGET_DIR}" ]]; then
  fail "${TARGET_DIR} does not exist. Use --mode install first."
fi

if [[ "${MODE}" == "upgrade" ]]; then
  if command_exists diff; then
    log "Showing diff between installed and upstream schema"
    diff -ruN "${TARGET_DIR}" "${UPSTREAM_DIR}" || true
  else
    log "diff command not available; skipping schema diff output"
  fi
fi

if [[ "${SET_SCHEMA}" -eq 1 && -f "${CONFIG_FILE}" ]]; then
  EARLY_SCHEMA="$(grep -E '^schema:' "${CONFIG_FILE}" | head -1 | sed 's/^schema:[[:space:]]*//' || true)"
  if [[ -n "${EARLY_SCHEMA}" && "${EARLY_SCHEMA}" != "${SCHEMA_NAME}" && "${EARLY_SCHEMA}" != "spec-driven" ]]; then
    fail "config.yaml uses custom schema '${EARLY_SCHEMA}'. Refusing to install: rerun with --no-set-schema to install without switching config, or edit ${CONFIG_FILE} to 'schema: ${SCHEMA_NAME}' first."
  fi
fi

rm -rf "${TARGET_DIR}"
cp -R "${UPSTREAM_DIR}" "${TARGET_DIR}"
log "Installed schema to ${TARGET_DIR}"

if [[ "${SET_SCHEMA}" -eq 1 && -f "${CONFIG_FILE}" ]]; then
  CURRENT_SCHEMA="$(grep -E '^schema:' "${CONFIG_FILE}" | head -1 | sed 's/^schema:[[:space:]]*//' || true)"
  if [[ "${CURRENT_SCHEMA}" == "${SCHEMA_NAME}" ]]; then
    log "config.yaml already uses schema '${SCHEMA_NAME}'"
  elif [[ -z "${CURRENT_SCHEMA}" || "${CURRENT_SCHEMA}" == "spec-driven" ]]; then
    # Empty or the openspec init default: safe to switch.
    if grep -qE '^schema:' "${CONFIG_FILE}"; then
      sed -i.bak "s|^schema:.*|schema: ${SCHEMA_NAME}|" "${CONFIG_FILE}" && rm -f "${CONFIG_FILE}.bak"
    else
      printf 'schema: %s\n' "${SCHEMA_NAME}" | cat - "${CONFIG_FILE}" > "${CONFIG_FILE}.tmp"
      mv "${CONFIG_FILE}.tmp" "${CONFIG_FILE}"
    fi
    log "Set schema: ${SCHEMA_NAME} in ${CONFIG_FILE}"
  fi
elif [[ "${SET_SCHEMA}" -eq 1 ]]; then
  log "No ${CONFIG_FILE} found; create it with 'schema: ${SCHEMA_NAME}'"
fi

if command_exists openspec; then
  (
    cd "${PROJECT_ROOT}"
    log "Validating schema"
    openspec schema validate "${SCHEMA_NAME}"
    log "Listing schemas"
    openspec schemas
  )
else
  log "openspec command not found; install completed without validation"
fi

log "Done"

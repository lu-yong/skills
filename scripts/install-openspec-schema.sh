#!/usr/bin/env bash
set -euo pipefail

MODE="install"
PROJECT_ROOT=""
SOURCE_DIR=""
REPO_URL="https://github.com/lu-yong/openspec-schemas"
SCHEMA_NAME="${1:-}"
SET_SCHEMA=1

case "${SCHEMA_NAME}" in
  aosp-repo|tdd-spec) shift ;;
  *) printf 'Expected aosp-repo or tdd-spec as the first argument.\n' >&2; exit 1 ;;
esac

usage() {
  cat <<EOF
Usage:
  Install ${SCHEMA_NAME}: --project-root <path> [options]

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
  printf '[%s-installer] %s\n' "${SCHEMA_NAME}" "$*"
}

fail() {
  printf '[%s-installer] ERROR: %s\n' "${SCHEMA_NAME}" "$*" >&2
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
INSTALL_DIR=""
CONFIG_TMP=""
SCHEMA_PUBLISHED=0
INSTALL_COMPLETE=0

cleanup() {
  if [[ -n "${CONFIG_TMP}" ]]; then
    rm -f "${CONFIG_TMP}"
  fi
  if [[ -n "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
  if [[ -n "${INSTALL_DIR}" ]]; then
    if [[ "${INSTALL_COMPLETE}" -eq 0 ]]; then
      if [[ "${SCHEMA_PUBLISHED}" -eq 1 ]]; then
        rm -rf "${TARGET_DIR}"
      fi
      if [[ -e "${INSTALL_DIR}/previous" || -L "${INSTALL_DIR}/previous" ]]; then
        mv "${INSTALL_DIR}/previous" "${TARGET_DIR}" || {
          printf 'Previous schema retained in %s\n' "${INSTALL_DIR}/previous" >&2
          return
        }
      fi
    fi
    rm -rf "${INSTALL_DIR}"
  fi
}
trap cleanup EXIT

if [[ -n "${SOURCE_DIR}" ]]; then
  SOURCE_DIR="$(cd "${SOURCE_DIR}" && pwd)"
else
  command_exists git || fail "git is required when --source-dir is not provided"
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openspec-schemas.XXXXXX")"
  log "Cloning upstream into ${TEMP_DIR}"
  git clone --depth 1 -- "${REPO_URL}" "${TEMP_DIR}" >/dev/null
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
  command_exists diff || fail "diff is required to show changes before upgrading."
  log "Showing diff between installed and upstream schema"
  diff -ruN "${TARGET_DIR}" "${UPSTREAM_DIR}" || [[ "$?" -eq 1 ]] || fail "Could not compare schema directories."
fi

INSTALL_DIR="$(mktemp -d "${SCHEMAS_DIR}/.${SCHEMA_NAME}.XXXXXX")"
if [[ "${SET_SCHEMA}" -eq 1 ]]; then
  CONFIG_ORIGINAL="${INSTALL_DIR}/config.original"
  if [[ -e "${CONFIG_FILE}" || -L "${CONFIG_FILE}" ]]; then
    [[ -f "${CONFIG_FILE}" ]] || fail "${CONFIG_FILE} is not a file."
    cp -p "${CONFIG_FILE}" "${CONFIG_ORIGINAL}"
    config_indent="$(awk '
      /^[ ]*($|#|%|---([ ]|$)|\.\.\.([ ]|$))/ { next }
      { match($0, /[^ ]/); if (!leftmost || RSTART < leftmost) leftmost = RSTART }
      END { if (leftmost) printf "%*s", leftmost - 1, "" }
    ' "${CONFIG_ORIGINAL}")"
    schema_key="^${config_indent}(schema|\"schema\"|'schema')[[:blank:]]*:"
    schema_count="$(awk -v key="${schema_key}" '$0 ~ key { count++ } END { print count+0 }' "${CONFIG_ORIGINAL}")"
    [[ "${schema_count}" -le 1 ]] || fail "Multiple schema entries in ${CONFIG_FILE}."
    current_schema="$(
      sed -nE \
        -e "/${schema_key}/!d" \
        -e "s#${schema_key}[[:blank:]]*##" \
        -e 's/(^|[[:blank:]]+)#.*//' \
        -e 's/[[:space:]]+$//' \
        -e 's/^"(.*)"$/\1/' \
        -e "s/^'(.*)'$/\1/" \
        -e p "${CONFIG_ORIGINAL}"
    )"
    case "${current_schema}" in
      "${SCHEMA_NAME}") log "config.yaml already uses schema '${SCHEMA_NAME}'" ;;
      ""|spec-driven)
        CONFIG_TMP="$(mktemp "${CONFIG_FILE}.XXXXXX")"
        cp -p "${CONFIG_ORIGINAL}" "${CONFIG_TMP}"
        if [[ "${schema_count}" -eq 1 ]]; then
          sed -E "s/${schema_key}.*/${config_indent}schema: ${SCHEMA_NAME}/" "${CONFIG_ORIGINAL}" > "${CONFIG_TMP}"
        else
          printf '%sschema: %s\n' "${config_indent}" "${SCHEMA_NAME}" | cat - "${CONFIG_ORIGINAL}" > "${CONFIG_TMP}"
        fi
        ;;
      *) fail "config.yaml uses custom schema '${current_schema}'. Use --no-set-schema or select '${SCHEMA_NAME}' in ${CONFIG_FILE} first." ;;
    esac
  else
    CONFIG_TMP="$(mktemp "${CONFIG_FILE}.XXXXXX")"
    printf 'schema: %s\n' "${SCHEMA_NAME}" > "${CONFIG_TMP}"
  fi
fi

cp -R "${UPSTREAM_DIR}" "${INSTALL_DIR}/candidate"
if [[ "${MODE}" == "upgrade" ]]; then
  mv "${TARGET_DIR}" "${INSTALL_DIR}/previous"
fi
mv "${INSTALL_DIR}/candidate" "${TARGET_DIR}"
SCHEMA_PUBLISHED=1
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

if [[ -n "${CONFIG_TMP}" ]]; then
  if [[ -f "${CONFIG_ORIGINAL}" ]]; then
    cmp -s "${CONFIG_ORIGINAL}" "${CONFIG_FILE}" || fail "${CONFIG_FILE} changed during installation."
  else
    [[ ! -e "${CONFIG_FILE}" && ! -L "${CONFIG_FILE}" ]] || fail "${CONFIG_FILE} appeared during installation."
  fi
  mv "${CONFIG_TMP}" "${CONFIG_FILE}"
fi
INSTALL_COMPLETE=1
if [[ -n "${CONFIG_TMP}" ]]; then
  log "Set schema: ${SCHEMA_NAME} in ${CONFIG_FILE}"
fi
log "Installed schema to ${TARGET_DIR}"
log "Done"

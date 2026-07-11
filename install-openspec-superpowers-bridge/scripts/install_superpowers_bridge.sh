#!/usr/bin/env bash
set -euo pipefail

MODE="install"
PROJECT_ROOT=""
SOURCE_DIR=""
REPO_URL="https://github.com/JiangWay/openspec-schemas"
SCHEMA_NAME="superpowers-bridge"
LOCALE="auto"
SKIP_ROUTING=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REFERENCES_DIR="${SKILL_DIR}/references"

usage() {
  cat <<'EOF'
Usage:
  install_superpowers_bridge.sh --project-root <path> [options]

Options:
  --mode install|upgrade
  --project-root <path>
  --source-dir <path>
  --repo-url <url>
  --locale auto|en|zh-CN|zh-TW
  --skip-routing
  --help
EOF
}

log() {
  printf '[bridge-installer] %s\n' "$*"
}

fail() {
  printf '[bridge-installer] ERROR: %s\n' "$*" >&2
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
    --locale)
      LOCALE="${2:-}"
      shift 2
      ;;
    --skip-routing)
      SKIP_ROUTING=1
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
[[ "${LOCALE}" == "auto" || "${LOCALE}" == "en" || "${LOCALE}" == "zh-CN" || "${LOCALE}" == "zh-TW" ]] || fail "--locale must be auto, en, zh-CN, or zh-TW"

PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"
OPENSPEC_DIR="${PROJECT_ROOT}/openspec"
SCHEMAS_DIR="${OPENSPEC_DIR}/schemas"
TARGET_DIR="${SCHEMAS_DIR}/${SCHEMA_NAME}"
AGENTS_FILE="${PROJECT_ROOT}/AGENTS.md"

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

rm -rf "${TARGET_DIR}"
cp -R "${UPSTREAM_DIR}" "${TARGET_DIR}"
log "Installed schema to ${TARGET_DIR}"

detect_locale() {
  if [[ "${LOCALE}" != "auto" ]]; then
    printf '%s\n' "${LOCALE}"
    return
  fi

  if [[ -f "${AGENTS_FILE}" ]]; then
    if grep -q '[臺灣萬與為這個變更設計驗證]' "${AGENTS_FILE}"; then
      printf 'zh-TW\n'
      return
    fi
    if grep -q '[这们为变更设计验证流程仓库脑]' "${AGENTS_FILE}"; then
      printf 'zh-CN\n'
      return
    fi
  fi

  printf 'en\n'
}

FRAGMENT_LOCALE="$(detect_locale)"
case "${FRAGMENT_LOCALE}" in
  en)
    FRAGMENT_PATH="${REFERENCES_DIR}/AGENTS.fragment.md"
    ;;
  zh-CN)
    FRAGMENT_PATH="${REFERENCES_DIR}/AGENTS.fragment.zh-CN.md"
    ;;
  zh-TW)
    FRAGMENT_PATH="${REFERENCES_DIR}/AGENTS.fragment.zh-TW.md"
    ;;
  *)
    fail "Unsupported routing locale: ${FRAGMENT_LOCALE}"
    ;;
esac

if [[ "${SKIP_ROUTING}" -eq 0 ]]; then
  [[ -f "${FRAGMENT_PATH}" ]] || fail "Missing routing fragment: ${FRAGMENT_PATH}"
  BEGIN_MARKER="<!-- BEGIN OPENSPEC SUPERPOWERS BRIDGE -->"
  END_MARKER="<!-- END OPENSPEC SUPERPOWERS BRIDGE -->"

  if [[ -f "${AGENTS_FILE}" ]] && grep -Fq "${BEGIN_MARKER}" "${AGENTS_FILE}"; then
    if command_exists diff; then
      log "Existing managed AGENTS.md section found; replacement preview:"
      TEMP_FRAGMENT="$(mktemp "${TMPDIR:-/tmp}/bridge-fragment.XXXXXX")"
      awk "
        /${BEGIN_MARKER//\//\\/}/ {capture=1}
        capture {print}
        /${END_MARKER//\//\\/}/ {capture=0}
      " "${AGENTS_FILE}" > "${TEMP_FRAGMENT}"
      diff -u "${TEMP_FRAGMENT}" "${FRAGMENT_PATH}" || true
      rm -f "${TEMP_FRAGMENT}"
    fi
    awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" '
      BEGIN {skip=0}
      $0 == begin {skip=1; next}
      $0 == end {skip=0; next}
      skip == 0 {print}
    ' "${AGENTS_FILE}" > "${AGENTS_FILE}.tmp"
    mv "${AGENTS_FILE}.tmp" "${AGENTS_FILE}"
  fi

  if [[ -f "${AGENTS_FILE}" && -s "${AGENTS_FILE}" ]]; then
    printf '\n' >> "${AGENTS_FILE}"
  fi
  cat "${FRAGMENT_PATH}" >> "${AGENTS_FILE}"
  printf '\n' >> "${AGENTS_FILE}"
  log "Updated ${AGENTS_FILE} with ${FRAGMENT_LOCALE} routing fragment"
else
  log "Skipping AGENTS.md routing update"
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

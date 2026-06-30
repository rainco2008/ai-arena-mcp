#!/usr/bin/env sh
set -eu

ROTATE_SECONDS="${GEMINI_SEARCH_PROFILE_ROTATION_SECONDS:-0}"
BASE_PROFILE_DIR="${GEMINI_SEARCH_USER_DATA_DIR:-/data/chrome-profile}"

case "${ROTATE_SECONDS}" in
  ""|0)
    exec "$@"
    ;;
  *[!0-9]*)
    echo "ERROR: GEMINI_SEARCH_PROFILE_ROTATION_SECONDS must be a positive integer or 0." >&2
    exit 1
    ;;
esac

if [ "${ROTATE_SECONDS}" -lt 60 ]; then
  echo "ERROR: GEMINI_SEARCH_PROFILE_ROTATION_SECONDS must be at least 60 seconds when enabled." >&2
  exit 1
fi

STOP_REQUESTED=0
CURRENT_PID=""

cleanup() {
  STOP_REQUESTED=1
  if [ -n "${CURRENT_PID}" ] && kill -0 "${CURRENT_PID}" 2>/dev/null; then
    kill -TERM "${CURRENT_PID}" 2>/dev/null || true
  fi
}

trap cleanup INT TERM

while [ "${STOP_REQUESTED}" -eq 0 ]; do
  PROFILE_DIR="${BASE_PROFILE_DIR%/}/profile-$(date +%Y%m%d%H%M%S)"
  mkdir -p "${PROFILE_DIR}"
  export GEMINI_SEARCH_USER_DATA_DIR="${PROFILE_DIR}"

  echo "Starting gemini-search with profile: ${GEMINI_SEARCH_USER_DATA_DIR}"
  "$@" &
  CURRENT_PID="$!"

  STARTED_AT="$(date +%s)"
  while kill -0 "${CURRENT_PID}" 2>/dev/null; do
    NOW="$(date +%s)"
    ELAPSED="$((NOW - STARTED_AT))"
    if [ "${ELAPSED}" -ge "${ROTATE_SECONDS}" ]; then
      echo "Profile rotation interval reached; restarting gemini-search."
      kill -TERM "${CURRENT_PID}" 2>/dev/null || true
      break
    fi
    sleep 5
  done

  wait "${CURRENT_PID}" 2>/dev/null || true
  CURRENT_PID=""
done

#!/bin/sh
# Shared by hosted steps, test scripts and image builds.
ci_retry() {
    ci_attempt=1
    while :; do
        if "$@"; then
            return 0
        else
            ci_status=$?
        fi
        printf '%s attempt %s/3 failed (exit %s)\n' "$1" "$ci_attempt" "$ci_status" >&2
        if [ "$ci_attempt" -eq 3 ]; then
            return "$ci_status"
        fi
        sleep "$((ci_attempt * 10))"
        ci_attempt=$((ci_attempt + 1))
    done
}

# $1 is the apt command (possibly a wrapper that supplies options and timeout).
ci_apt_install() {
    ci_apt_command=$1
    shift
    "$ci_apt_command" update &&
        "$ci_apt_command" install -y --no-install-recommends "$@"
}

ci_host_apt() {
    timeout 8m sudo apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 "$@"
}

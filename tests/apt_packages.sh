#!/usr/bin/env bash
# Real APT regression, only in the disposable OS-matrix build container.
set -Eeuo pipefail
[[ ${XUI_APT_TEST:-} == container ]] || { echo 'Requires the disposable APT test container' >&2; exit 1; }
repo=${1:?Repository path required}
state=$(mktemp -d)
sshd_pid=''
trap '[[ -z "$sshd_pid" ]] || kill "$sshd_pid"; rm -rf "$state"' EXIT
python3 - "$repo/x-ui-latest.sh" > "$state/functions" <<'PY'
import pathlib, re, sys
source=pathlib.Path(sys.argv[1]).read_text()
for name in ('apt_system','install_packages','ipv6_available'):
    print(re.search(r'^'+name+r'\(\)\s*\{.*?^\}',source,re.M|re.S).group())
PY
# Only service enablement is outside this container's scope; APT is unmodified.
systemctl() { :; }
msg_err() { echo "$*" >&2; }
# shellcheck disable=SC1091
source "$state/functions"
apt-get update -o APT::Update::Error-Mode=any
apt-get install -y --no-install-recommends mtr-tiny openssh-server
mkdir -p /run/sshd
/usr/sbin/sshd -t
/usr/sbin/sshd -D -e -p 22322 -o ListenAddress=127.0.0.1 -o "PidFile=$state/sshd.pid" > "$state/sshd.log" 2>&1 &
sshd_pid=$!
apt_system -s -y dist-upgrade
apt_system -y dist-upgrade
INSTALL=y install_packages
# Exercise removal through the same wrapper, independently of the MTR choice.
apt_system -y remove mtr-tiny
apt_system -y --no-install-recommends install mtr-tiny
dpkg --audit > "$state/audit"
[[ ! -s "$state/audit" ]]
dpkg-query -W -f='${db:Status-Status} ${binary:Package}\n' > "$state/packages"
if grep -Eq '^installed (mtr|libgtk-[^ ]*)(:.*)?$' "$state/packages"; then
    echo 'Unexpected graphical MTR/GTK dependency' >&2; exit 1
fi
grep -qx 'installed mtr-tiny' "$state/packages"
grep -qx 'installed openssh-server' "$state/packages"
/usr/sbin/sshd -t
kill -0 "$sshd_pid"
python3 - "$repo" <<'PY'
import importlib.util, pathlib, socket, sys
with socket.create_connection(('127.0.0.1',22322),timeout=5) as conn:
    assert conn.recv(255).startswith(b'SSH-2.0-')
path=pathlib.Path(sys.argv[1])/'assets/diagnostics/mtr-backend.py'
spec=importlib.util.spec_from_file_location('mtr_backend',path)
backend=importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
result=backend.run_mtr('127.0.0.1',1)
assert result['success'], result
assert '127.0.0.1' in result['output'], result
print('REAL APT: existing mtr-tiny / full upgrade / installer dependencies / removal / SSH banner / MTR backend / no GTK: PASS')
PY

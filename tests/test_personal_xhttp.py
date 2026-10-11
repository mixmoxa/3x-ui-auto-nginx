"""Validate fresh-install templates without sourcing or running the installer."""

import json
import hashlib
import tarfile
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "x-ui-latest.sh").read_text()
MONTHLY = ('@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" '
           '--post-hook "systemctl start nginx" > /dev/null 2>&1')
FIXTURE = {
    "domain": "deploy.example", "reality_domain": "cover.example",
    "xhttp_path": "Session7AbC", "sub_path": "subscription", "json_path": "jsonsub",
    "panel_path": "panel", "ws_path": "websocket", "trojan_path": "trojan",
    "sub_port": "10001", "panel_port": "10002", "ws_port": "10003",
    "trojan_port": "10004", "mtr_backend_port": "10005",
    "ws_route": "/10003/websocket", "trojan_route": "/10004/trojan",
    "diag_path": "/diagnostics/", "diag_token": "test-token", "emoji_flag": "test",
    "private_key": "test-private", "public_key": "test-public",
    "sub_uri": "https://deploy.example/subscription/",
    "json_uri": "https://deploy.example/jsonsub/",
    "gid_col": "", "gid_reality": "", "gid_ws": "", "gid_xhttp": "", "gid_trojan": "", "gid_hysteria": "",
    "http2_listen": " http2", "http2_on": "",
}


def template(target, source=SOURCE):
    """Extract one original heredoc; never execute its surrounding function."""
    matches = re.findall(r"^\s*" + re.escape(target) + r" <<EOF\n(.*?)^EOF$", source, re.M | re.S)
    if len(matches) != 1:
        raise AssertionError(f"Expected one heredoc for {target}, found {len(matches)}")
    return matches[0]


def render(target, source=SOURCE, **variables):
    script = "shor=(a b c d e f g h)\ncat <<EOF\n" + template(target, source) + "EOF\n"
    return subprocess.check_output(
        ["bash", "-eu", "-c", script], text=True,
        env={**os.environ, **FIXTURE, **variables},
    )


def seed(group_id=False, **variables):
    """Execute generated inbound/Host INSERTs against both supported Host schemas."""
    setup = re.search(r"    local gid_col=.*?^    fi", function("configure_xui_db"), re.M | re.S).group()
    script = (
        'sqlite3() { echo "$HOST_TEST_SCHEMA"; }\n' + function("gen_group_id") +
        '\nemit() {\n' + setup + '\nshor=(a b c d e f g h)\ncat <<EOF\n' +
        template("sqlite3 $XUIDB") + 'EOF\n}\nemit\n'
    )
    sql = subprocess.check_output(["bash", "-u", "-c", script], text=True, env={
        **os.environ, **FIXTURE, **variables, "XUIDB": "/fixture/x-ui.db",
        "HOST_TEST_SCHEMA": "group_id" if group_id else "id",
    })
    blocks = re.findall(r'^INSERT INTO "inbounds"\s.*?^\);', sql, re.M | re.S)
    if len(blocks) != 5:
        raise AssertionError(f"Expected five inbound INSERTs, found {len(blocks)}")
    columns = re.search(r'\(("user_id".*?)\)\s*VALUES', blocks[0], re.S).group(1)
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE inbounds (id INTEGER PRIMARY KEY," + columns + ")")
        db.execute('''CREATE TABLE hosts (
            id INTEGER PRIMARY KEY, inbound_id INTEGER NOT NULL REFERENCES inbounds(id),
            sort_order INTEGER, remark TEXT, address TEXT, port INTEGER, security TEXT,
            fingerprint TEXT, alpn TEXT, is_disabled INTEGER DEFAULT 0,
            sni TEXT DEFAULT '', final_mask TEXT DEFAULT '', mux_params TEXT DEFAULT '',
            sockopt_params TEXT DEFAULT '' ''' + (", group_id TEXT NOT NULL" if group_id else "") + ")")
        for block in blocks:
            db.execute(block)
        db.execute(re.search(r'^INSERT INTO "hosts".*?;', sql, re.M | re.S).group())
        rows = {row["remark"].split()[-1]: dict(row) for row in db.execute("SELECT * FROM inbounds")}
        return rows, [dict(row) for row in db.execute("SELECT * FROM hosts")]


def inbounds(**variables):
    return seed(**variables)[0]


SHARED = "cat > /etc/nginx/snippets/includes.conf"
MAIN = 'cat > "/etc/nginx/sites-available/${domain}"'


def function(name):
    matches = re.findall(r"^" + re.escape(name) + r"\(\)\s*\{.*?^\}", SOURCE, re.M | re.S)
    if len(matches) != 1:
        raise AssertionError(f"Expected one {name} function")
    return matches[0]


class PersonalXHTTP(unittest.TestCase):
    def test_vless_seed_supplies_json_subscription_encryption(self):
        # v3.9.0 genVless reads the outbound encryption from these inbound settings.
        for name in ('reality', 'ws', 'xhttp'):
            with self.subTest(profile=name):
                self.assertEqual(json.loads(inbounds()[name]['settings']).get('encryption'), 'none')

    def test_panel_directory_errors_abort_before_following_operations(self):
        # Run the original function, including its caller's `||` context (no errexit).
        for failed in (1, 2):
            with self.subTest(cd=failed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                calls = root/'calls'
                (root/'archive').write_text('verified fixture')
                panel = function('install_panel').replace('/usr/local', str(root/'local'))
                mock = '''
record() { printf '%s\\n' "$*" >> "$CALLS"; }
cd() { (( CD_COUNT+=1 )); record "cd $CD_COUNT"; [[ "$CD_COUNT" != "$FAIL_CD" ]]; }
apt-get() { :; }
curl() { :; }
_validate_panel_version() { :; }
_arch() { echo amd64; }
mktemp() { echo "$ROOT/archive"; }
_download_panel_archive() { record download; }
rm() { record remove; }
tar() { record extract; }
chmod() { record chmod; }
install() { record install-cli; }
_panel_initial_config() { record initial-config; }
cp() { record copy-service; }
systemctl() { record systemctl; }
msg_ok() { record success; }
CD_COUNT=0
'''
                result = subprocess.run(['bash','-u','-c', mock+panel+'\ninstall_panel || exit 1'],
                                        env={**os.environ,'PANEL_VERSION':'v3.9.0','FAIL_CD':str(failed),
                                             'ROOT':str(root),'CALLS':str(calls),'PANEL_TAG':'v3.9.0','PANEL_ARCHIVE':str(root/'archive')}, text=True, capture_output=True)
                events = calls.read_text().splitlines()
                self.assertIn(f'cd {failed}', events, 'chdir failure must actually be reached')
                self.assertNotEqual(result.returncode, 0, f'continued after failed cd: {events}')
                self.assertEqual(events[-1], f'cd {failed}', 'no operation may follow failed chdir')
                self.assertNotIn('success', events)

    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(ROOT / "x-ui-latest.sh")], check=True)

    def test_installer_branding_and_domain_prompts(self):
        startup = SOURCE[SOURCE.index("msg_ok()"):SOURCE.index("# ─── Pre-flight checks")]
        result = subprocess.run(["bash", "-eu", "-c", startup], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3X-UI AUTO NGINX", result.stdout)
        self.assertIn("Automated 3x-ui / Xray deployment", result.stdout)
        self.assertNotIn("X-UI-PRO", result.stdout.upper())
        self.assertNotIn("X-UI Secure Panel", SOURCE)
        helpers = '\n'.join(re.findall(r'^msg_\w+\(\).*$', SOURCE, re.M))
        script = helpers + '\n' + function("validate_domains") + '\nvalidate_domains\nprintf "%s|%s" "$domain" "$reality_domain"\n'
        for provided in (False, True):
            with self.subTest(cli_domains=provided):
                result = subprocess.run(["bash", "-eu", "-c", script], capture_output=True, text=True,
                                        input="panel.example.com\nreality.example.com\n", env={**os.environ,
                                        "domain": "panel.example.com" if provided else "",
                                        "reality_domain": "reality.example.com" if provided else ""})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.endswith("panel.example.com|reality.example.com"))
                for prompt in ("3x-ui panel domain (panel.example.com):", "REALITY domain (reality.example.com):"):
                    self.assertEqual(prompt in result.stdout, not provided)

    def test_cpu_capabilities_are_advisory_and_fixture_driven(self):
        cpu = function("check_cpu")
        self.assertNotIn("This is required for correct operation of the Xray core.", SOURCE)
        self.assertNotRegex(cpu, r"\b(?:exit|read|sleep|msg_err)\b")
        self.assertNotRegex(SOURCE, r"(?<!-)-(?:ignore_qemu|force_cpu|force)\b")
        helpers = '\n'.join(re.findall(r'^msg_\w+\(\).*$', SOURCE, re.M))
        cases = (
            ("qemu-aes", "x86_64", "model name : QEMU Virtual CPU\nflags : fpu\taes\tsse\n", "ok", False),
            ("qemu-no-aes", "x86_64", "model name : QEMU Virtual CPU\nflags : fpu sse\n", "warn", True),
            ("intel-aes", "x86_64", "model name : Intel CPU\nflags : fpu aes\n", "ok", False),
            ("amd-no-aes", "x86_64", "model name : AMD CPU\nflags : fpu sse\n", "warn", False),
            ("arm-aes", "aarch64", "Features : fp asimd aes pmull\n", "ok", False),
            ("arm-no-aes", "aarch64", "Features : fp asimd\n", "warn", False),
            ("no-model", "i686", "flags : aes\n", "ok", False),
            ("no-flags", "x86_64", "model name : QEMU Virtual CPU\n", "info", False),
            ("empty-flags", "x86_64", "flags :  \t\n", "info", False),
            ("no-features", "arm64", "model name : ARM CPU\n", "info", False),
            ("missing-file", "x86_64", None, "info", False),
            ("unreadable-file", "x86_64", "directory", "info", False),
            ("aes-substrings", "x86_64", "flags : vaes aesni not_aes\n", "warn", False),
            ("wrong-field", "aarch64", "flags : aes\n", "info", False),
            ("unassessed-arch", "riscv64", "Features : aes\n", "info", False),
        )
        for name, arch, content, level, qemu_advice in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "cpuinfo"
                if content == "directory":
                    path.mkdir()
                elif content is not None:
                    path.write_text(content)
                script = helpers + '\n' + cpu + r'''
uname() { [[ "$*" == -m ]] && printf '%s\n' "$CPU_ARCH"; }
check_cpu "$CPUINFO"
printf 'CPU_STATE|%s|%s\n' "$CPU_SUPPORT_LEVEL" "$CPU_SUPPORT_TEXT"
'''
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], capture_output=True, text=True,
                                        env={**os.environ, "CPU_ARCH": arch, "CPUINFO": str(path)})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                lines = result.stdout.splitlines()
                marker = next(line for line in lines if line.startswith("CPU_STATE|"))
                actual_level, text = marker.split("|", 2)[1:]
                self.assertEqual(actual_level, level)
                expected_text = {"ok": "Compatible (hardware AES available)",
                                 "warn": "Compatible — hardware AES unavailable",
                                 "info": "Compatible (acceleration not assessed)"}
                self.assertEqual(text, expected_text[level])
                self.assertEqual("host-passthrough" in result.stdout, qemu_advice)
                warnings = [line for line in lines if not line.startswith("CPU_STATE|")]
                if level == "warn":
                    self.assertTrue(warnings)
                    self.assertTrue(all("\x1b[1;33m" in line for line in warnings))
                    self.assertIn("Xray can run", result.stdout)
                    self.assertIn("Continuing installation.", result.stdout)
                else:
                    self.assertEqual(warnings, [])

    def test_final_summary_is_honest_and_only_follows_health_gate(self):
        summary = function("show_results")
        self.assertNotIn("/root/cert/${reality_domain}", summary)
        self.assertNotRegex(summary, r"\|\s*x-ui\b")
        self.assertNotIn("nginx -t", summary)
        self.assertLess(function("main").index("check_installation"), function("main").index("show_results"))
        helpers = '\n'.join(re.findall(r'^msg_\w+\(\).*$', SOURCE, re.M))
        # Run the actual main ordering/summary on files; installer operations are no-ops.
        mocks = '\n'.join(name + '() { :; }' for name in (
            "select_security", "select_vision", "select_client", "preflight_integrated_features", "select_amneziawg", "preflight_amneziawg", "preflight_panel_release", "select_adguard", "cleanup_adguard", "validate_domains", "clean_previous_install", "install_packages", "setup_firewall", "get_server_ip",
            "get_ssl_certs", "install_panel", "configure_nginx", "configure_xui_db", "install_clash_sub",
            "install_fake_site", "install_diagnostics", "tune_system", "install_backup_tool", "setup_certificate_renewal", "setup_acme_http", "confirm_destructive_reinstall",
        )) + r'''
systemctl() { echo "systemctl $*" >> "$SUMMARY_LOG"; [[ "$*" == 'is-enabled --quiet x-ui' ]]; }
x-ui() { echo "x-ui $*" >> "$SUMMARY_LOG"; [[ "$*" == restart ]]; }
ufw() {
    echo "ufw $*" >> "$SUMMARY_LOG"
    [[ "$*" == status && "$UFW_STATE" != unknown ]] || return 1
    echo "Status: $UFW_STATE"
}
check_installation() { echo health-gate >> "$SUMMARY_LOG"; [[ "$FAIL_GATE" == 0 ]]; }
'''
        certificates = tuple(
            f"etc/letsencrypt/live/{domain}/{name}"
            for domain in (FIXTURE["domain"], FIXTURE["reality_domain"])
            for name in ("fullchain.pem", "privkey.pem")
        ) + tuple(f"root/cert/{FIXTURE['domain']}/{name}" for name in ("fullchain.pem", "privkey.pem"))
        scenarios = (("active", False, False, False, None), ("inactive", False, False, False, None),
                     ("unknown", False, False, False, None), ("active", True, False, False, None),
                     ("active", False, True, False, None), ("active", False, False, True, None))
        scenarios += tuple(("active", False, False, False, path) for path in certificates)
        scenarios = tuple((*scenario, "ok") for scenario in scenarios)
        scenarios += (("active", False, False, False, None, "warn"), ("active", False, False, False, None, "info"))
        for state, missing_assets, failed_version, failed_gate, missing_certificate, cpu_level in scenarios:
            with self.subTest(ufw=state, missing_assets=missing_assets, version_failure=failed_version, gate_failure=failed_gate, missing_certificate=missing_certificate, cpu=cpu_level), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                relocated = summary
                for path in ("/etc/letsencrypt/live", "/root/cert", "/var/www/diagnostics", "/usr/local/lib/3x-ui-pro",
                             "/usr/local/bin/x-ui-backup", "/usr/local/x-ui/x-ui"):
                    relocated = relocated.replace(path, str(root) + path)
                binary = root / "usr/local/x-ui/x-ui"
                binary.parent.mkdir(parents=True)
                binary.write_text('''#!/bin/sh
echo "binary $*" >> "$SUMMARY_LOG"
[ "$FAIL_VERSION" = 0 ] || exit 1
echo 'x-ui 3.9.0'
''')
                binary.chmod(0o755)
                if not missing_assets:
                    for relative in certificates:
                        path = root / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if relative.startswith("root/cert/"):
                            path.symlink_to(root / f"etc/letsencrypt/live/{FIXTURE['domain']}/{path.name}")
                        else:
                            path.write_text("fixture certificate")
                    if missing_certificate:
                        (root / missing_certificate).unlink()
                self.assertFalse((root / f"root/cert/{FIXTURE['reality_domain']}").exists())
                if not missing_assets:
                    for name in ("var/www/diagnostics/index.html", "var/www/diagnostics/speedtest.js",
                                 "var/www/diagnostics/speedtest_worker.js", "usr/local/lib/3x-ui-pro/mtr-backend.py",
                                 "usr/local/bin/x-ui-backup"):
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("fixture file")
                        path.chmod(0o755)
                log = root / "calls"
                cpuinfo = root / "cpuinfo"
                cpuinfo.write_text("model name : QEMU Virtual CPU\n" +
                                   {"ok": "flags : aes\n", "warn": "flags : fpu\n", "info": ""}[cpu_level])
                script = (helpers + '\n' + mocks + '\nuname() { echo x86_64; }\n' + function("check_cpu") +
                          '\ncheck_cpu "$CPUINFO"\n' + relocated + '\n' + function("main") + '\nmain\n')
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], capture_output=True, text=True, env={
                    **os.environ, **FIXTURE, "SUMMARY_LOG": str(log), "UFW_STATE": state,
                    "FAIL_GATE": "1" if failed_gate else "0", "FAIL_VERSION": "1" if failed_version else "0",
                    "CPUINFO": str(cpuinfo), "INSTALL_AGH": "n",
                    "config_username": "fixture-user", "config_password": "fixture-password",
                })
                self.assertEqual(result.returncode, 1 if failed_gate else 0, result.stderr)
                text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
                calls = log.read_text().splitlines()
                self.assertEqual(calls[:3], ["systemctl is-enabled --quiet x-ui", "x-ui restart", "health-gate"])
                if failed_gate:
                    self.assertNotIn("Installation Result", text)
                    self.assertNotIn("fixture-password", text)
                    self.assertEqual(len(calls), 3)
                    continue
                self.assertEqual(calls[3:], ["binary -v", "ufw status"])
                for item in ("3x-ui Auto Nginx — Installation Result", "Panel:", "Diagnostics", "Username: fixture-user",
                             "Password: fixture-password", "Backup:", "x-ui-backup backup", "Certificate renewal",
                             "https://deploy.example/panel/", "https://deploy.example/panel/diag",
                             "Enabled by default: REALITY · XHTTP · Hysteria2", "Optional profiles: WS · Trojan gRPC"):
                    self.assertIn(item, text)
                self.assertEqual("(3x-ui 3.9.0)" in text, not failed_version)
                cpu_line = next(line for line in result.stdout.splitlines() if "CPU support" in line)
                self.assertIn({"ok": "\x1b[1;32m", "warn": "\x1b[1;33m", "info": "\x1b[1;34m"}[cpu_level], cpu_line)
                self.assertIn({"ok": "[✓]", "warn": "[!]", "info": "[i]"}[cpu_level], cpu_line)
                self.assertIn("Compatible", cpu_line)
                self.assertIn({"ok": "hardware AES available", "warn": "hardware AES unavailable",
                               "info": "acceleration not assessed"}[cpu_level], cpu_line)
                self.assertNotRegex(cpu_line, r"Unsupported|Failed|Unsafe")
                self.assertLess(text.index("3x-ui / Xray"), text.index("CPU support"))
                self.assertLess(text.index("CPU support"), text.index("nginx"))
                firewall_line = next(line for line in result.stdout.splitlines() if "Firewall / UFW" in line)
                self.assertIn("\x1b[1;32m" if state == "active" else "\x1b[1;33m", firewall_line)
                self.assertIn("[✓]" if state == "active" else "[!]", firewall_line)
                self.assertIn(state.capitalize(), firewall_line)
                if state != "active":
                    self.assertIn("review firewall settings", firewall_line)
                for label in ("TLS certificates", "Diagnostics", "Backup / Restore"):
                    line = next(line for line in result.stdout.splitlines() if label in line and ("[✓]" in line or "[!]" in line))
                    warning = missing_assets or (label == "TLS certificates" and missing_certificate is not None)
                    self.assertIn("\x1b[1;33m" if warning else "\x1b[1;32m", line)
                    self.assertIn("[!]" if warning else "[✓]", line)
                    if label == "TLS certificates":
                        self.assertIn("Check certificate files" if warning else "Ready", line)

    def firewall(self, status, connection="", sshd="", fail="", sshd_exit="0"):
        # Run only setup_firewall; mock all UFW/sshd operations on private files.
        mock = '''ufw() {
    printf '%s\\n' "$*" >> "$FIREWALL_TEST_ROOT/calls"
    [[ "$*" == "$FAIL_UFW" ]] && return 1
    case "$*" in
        status)
            [[ "$LC_ALL" == C ]] || return 1
            printf 'Status: %s\\n' "$(cat "$FIREWALL_TEST_ROOT/status")" ;;
        allow*)
            grep -qxF "$2" "$FIREWALL_TEST_ROOT/rules" || printf '%s\\n' "$2" >> "$FIREWALL_TEST_ROOT/rules" ;;
        '--force enable') echo active > "$FIREWALL_TEST_ROOT/status" ;;
        *) return 2 ;;
    esac
}
sshd() {
    echo "sshd $*" >> "$FIREWALL_TEST_ROOT/calls"
    printf '%s\\n' "$SSHD_OUTPUT"
    return "$SSHD_EXIT"
}
msg_err() { echo "$1" >&2; }
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "status").write_text(status)
            (root / "rules").write_text("2222/tcp\n")
            result = subprocess.run(
                ["bash", "-u", "-c", mock + function("setup_firewall") + "\nsetup_firewall\n"],
                text=True, capture_output=True, env={
                    **os.environ, "FIREWALL_TEST_ROOT": tmp, "SSH_CONNECTION": connection,
                    "SSHD_OUTPUT": sshd, "SSHD_EXIT": sshd_exit, "FAIL_UFW": fail, "panel_port": FIXTURE["panel_port"],
                },
            )
            return result, (root / "calls").read_text().splitlines(), (root / "rules").read_text().splitlines(), (root / "status").read_text().strip()

    def test_firewall_active_preserves_existing_policy(self):
        result, calls, rules, status = self.firewall("active", sshd="port 22")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["status", "allow 80/tcp", "allow 443/tcp", "allow 443/udp"])
        self.assertEqual(rules, ["2222/tcp", "80/tcp", "443/tcp", "443/udp"])
        self.assertEqual(status, "active")

    def test_firewall_inactive_uses_connection_ssh_port(self):
        for port in ("2222", "22", "00022", "65535"):
            with self.subTest(port=port):
                result, calls, _, status = self.firewall("inactive", f"198.51.100.10 54321 203.0.113.5 {port}", "port 9999")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, ["status", "allow 80/tcp", "allow 443/tcp", "allow 443/udp", f"allow {int(port)}/tcp", "--force enable"])
                self.assertEqual(status, "active")

    def test_firewall_inactive_falls_back_to_effective_sshd_ports(self):
        for connection in ("", "invalid", "a b c 0", "a b c 65536", "a b c 99999999999999999999", "a b c 22 extra"):
            with self.subTest(connection=connection):
                result, calls, rules, status = self.firewall("inactive", connection, "port 2222\nport 2200\nport 2222\nport 0\nport 65536\nport invalid\npermitrootlogin yes")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, ["status", "allow 80/tcp", "allow 443/tcp", "allow 443/udp", "sshd -T", "allow 2200/tcp", "allow 2222/tcp", "--force enable"])
                self.assertNotIn("22/tcp", rules)
                self.assertEqual(status, "active")

    def test_firewall_inactive_unknown_ssh_warns_without_enabling(self):
        for output, code in (("", "0"), ("port 0\nport 65536\nport invalid", "0"), ("port 22", "1")):
            with self.subTest(output=output, code=code):
                result, calls, _, status = self.firewall("inactive", "invalid", output, sshd_exit=code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, ["status", "allow 80/tcp", "allow 443/tcp", "allow 443/udp", "sshd -T"])
                self.assertEqual(status, "inactive")
                self.assertIn("WARNING", result.stderr)
                self.assertIn("SSH port could not be detected", result.stderr)
                self.assertIn("UFW was not enabled automatically", result.stderr)

    def test_firewall_required_operation_failures_are_fatal(self):
        commands = ["status", "allow 80/tcp", "allow 443/tcp", "allow 443/udp", "allow 2200/tcp", "--force enable"]
        for index, command in enumerate(commands):
            with self.subTest(command=command):
                result, calls, _, _ = self.firewall("inactive", "a b c 2200", fail=command)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, commands[:index + 1])
        result, calls, _, _ = self.firewall("unexpected")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ["status"])

    def test_firewall_never_disables_resets_or_hardcodes_ssh(self):
        for line in SOURCE.splitlines():
            if re.search(r"\bufw\b", line):
                executable = " ".join(shlex.split(line, comments=True))
                self.assertNotRegex(executable, r"\bufw\s+(?:disable|reset|default|delete|allow\s+22/tcp)\b")

    def test_firewall_precedes_certbot_and_stops_installer_on_failure(self):
        main = function("main")
        self.assertEqual(len(re.findall(r"^\s*setup_firewall\b", main, re.M)), 1)
        self.assertLess(main.index("install_packages"), main.index("setup_firewall"))
        self.assertLess(main.index("setup_firewall"), main.index("get_ssl_certs"))
        self.assertRegex(main, r"setup_firewall\s*\|\|[^\n]*exit 1")

    def test_panel_and_cli_download_use_the_same_release_tag(self):
        panel = function("install_panel")
        self.assertNotIn("curl", panel)
        self.assertNotIn("_download_panel_archive", panel)
        self.assertIn('install -m 0755 x-ui.sh /usr/bin/x-ui', panel)
        self.assertLess(panel.index("tar zxvf"), panel.index("install -m 0755 x-ui.sh"))
        self.assertIn('${PANEL_ARCHIVE:?Release preflight is required}', panel)
        preflight = function('preflight_panel_release')
        self.assertIn('https://github.com/MHSanaei/3x-ui/releases/download/${PANEL_TAG}/$asset', preflight)
        self.assertLess(preflight.index('_download_panel_archive'),preflight.index('_validate_panel_archive'))


    def test_ws_host_uses_only_http11_alpn(self):
        for grouped in (False, True):
            with self.subTest(group_id=grouped):
                rows, hosts = seed(group_id=grouped)
                ws = [h for h in hosts if h["inbound_id"] == rows["ws"]["id"]]
                self.assertEqual(len(ws), 1)
                self.assertEqual(json.loads(ws[0]["alpn"]), ["http/1.1"])
                for name in ("xhttp", "trojan-grpc"):
                    host = next(h for h in hosts if h["inbound_id"] == rows[name]["id"])
                    self.assertEqual(json.loads(host["alpn"]), ["h2", "http/1.1"])

    def test_installer_dependencies_are_required(self):
        mock = r'''msg_err() { echo "$*" >&2; }
apt() { echo "apt $*" >> "$TEST_LOG"; [[ "$FAIL_DEP" != apt ]]; }
apt-get() { echo "apt-get $*" >> "$TEST_LOG"; [[ "$FAIL_DEP" != apt ]]; }
systemctl() { echo "systemctl $*" >> "$TEST_LOG"; [[ "$FAIL_DEP" != nginx || "$*" != 'enable --now nginx' ]]; }
command() { [[ "$*" != "-v $FAIL_DEP" ]]; }
python3() { echo "python3 $*" >> "$TEST_LOG"; [[ "$FAIL_DEP" != python-import ]]; }
'''
        required = {"openssl", "procps", "iproute2", "tar", "gzip", "tzdata", "ca-certificates",
                    "curl", "wget", "jq", "bash", "sudo", "nginx-full", "certbot",
                    "sqlite3", "ufw", "netcat-openbsd", "mtr", "python3", "python3-configobj", "python3-cryptography", "libcap2-bin"}
        self.assertRegex(function("main"), r"install_packages\s*\|\|.*exit 1")
        for failure in ("", "apt", "sysctl", "ip", "nginx", "python-import"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "calls"
                result = subprocess.run(["bash", "-u", "-c", mock + function("install_packages") + "\ninstall_packages\n"],
                                        capture_output=True, text=True, env={**os.environ, "Pak": "apt", "INSTALL": "y",
                                                                            "TEST_LOG": str(log), "FAIL_DEP": failure})
                self.assertEqual(result.returncode, 1 if failure else 0, result.stderr)
                if not failure:
                    calls = log.read_text().splitlines()
                    packages = next(c.split()[3:] for c in calls if c.startswith("apt -y install "))
                    self.assertTrue(required.issubset(packages))
                    self.assertNotIn("cron", packages)
                    self.assertNotIn("python3-certbot-nginx", packages)
                    self.assertIn('python3 -c import configobj, cryptography', calls)

    def test_installer_final_health_gate_precedes_success_output(self):
        main = function("main")
        self.assertRegex(main, r"check_installation\s*\|\|.*exit 1")
        self.assertLess(main.index("check_installation"), main.index("show_results"))
        mock = r'''msg_err() { echo "$*" >&2; }
systemctl() { [[ "$FAIL_HEALTH" != "$1:$3" ]]; }
nginx() { [[ "$FAIL_HEALTH" != nginx-test ]]; }
check_certificate_renewal() { [[ "$FAIL_HEALTH" != renewal ]]; }
check_xray_runtime() { [[ "$FAIL_HEALTH" != socket ]]; }
sqlite3() { [[ "$FAIL_HEALTH" == panel-bind ]] || echo 127.0.0.1; }
sleep() { :; }
'''
        failures = ("", "is-active:x-ui", "is-active:nginx", "is-active:mtr-backend", "renewal", "nginx-test", "socket", "panel-bind")
        for failure in failures:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "xhttp.sock"
                with socket.socket(socket.AF_UNIX) as uds:
                    if failure != "socket":
                        uds.bind(str(path))
                    script = mock + function("check_installation").replace("/dev/shm/uds2023.sock", str(path))
                    result = subprocess.run(["bash", "-u", "-c", script + "\ncheck_installation || exit 1\necho final-success\n"],
                                            capture_output=True, text=True, env={**os.environ, **FIXTURE, "XUIDB": "/fixture/db", "FAIL_HEALTH": failure})
                    self.assertEqual(result.returncode, 1 if failure else 0, result.stderr)
                    self.assertEqual("final-success" in result.stdout, not bool(failure))

    def test_inbound_and_sniffing(self):
        rows = inbounds()
        self.assertEqual(set(rows), {"reality", "ws", "xhttp", "trojan-grpc", "hysteria2"})
        self.assertEqual(rows["reality"]["enable"], "1")
        self.assertEqual(rows["ws"]["enable"], "0")
        self.assertEqual(rows["trojan-grpc"]["enable"], "0")
        self.assertEqual({name: row["protocol"] for name, row in rows.items()}, {
            "reality": "vless", "ws": "vless", "xhttp": "vless",
            "trojan-grpc": "trojan", "hysteria2": "hysteria",
        })
        for row in rows.values():
            json.loads(row["settings"])
            json.loads(row["stream_settings"])
            self.assertEqual(json.loads(row["sniffing"]), {
                "enabled": True, "destOverride": ["http", "tls", "quic", "fakedns"],
                "metadataOnly": False, "routeOnly": False,
            })
        xhttp = rows["xhttp"]
        self.assertEqual(xhttp["enable"], "1")
        self.assertEqual(xhttp["listen"], "/dev/shm/uds2023.sock,0666")
        self.assertEqual(xhttp["port"], "0")
        self.assertEqual(xhttp["protocol"], "vless")
        # Exact minimal profile also excludes legacy tuning, XMUX and generic Mux.
        self.assertEqual(json.loads(xhttp["stream_settings"]), {
            "network": "xhttp", "security": "none",
            "xhttpSettings": {"path": "/Session7AbC", "mode": "stream-up"},
            "sockopt": {"trustedXForwardedFor": ["X-Forwarded-For"]},
        })

    def test_hysteria2_minimal_server_profile(self):
        row = inbounds()["hysteria2"]
        self.assertEqual({key: row[key] for key in ("enable", "protocol", "listen", "port", "tag")}, {
            "enable": "1", "protocol": "hysteria", "listen": "", "port": "443", "tag": "inbound-443-udp",
        })
        self.assertEqual(json.loads(row["settings"]), {"version": 2, "clients": []})
        # Exact profile excludes auth/useFile/fingerprint, FinalMask and all custom QUIC/mask/hopping tuning.
        self.assertEqual(json.loads(row["stream_settings"]), {
            "network": "hysteria", "security": "tls",
            "hysteriaSettings": {"version": 2, "udpIdleTimeout": 60},
            "tlsSettings": {
                "serverName": "deploy.example", "alpn": ["h3"],
                "certificates": [{
                    "certificateFile": "/root/cert/deploy.example/fullchain.pem",
                    "keyFile": "/root/cert/deploy.example/privkey.pem",
                    "ocspStapling": 0, "oneTimeLoading": False,
                    "usage": "encipherment", "buildChain": False,
                }],
            },
        })
        self.assertNotIn(FIXTURE["reality_domain"], row["stream_settings"])

    def test_hysteria2_host_with_and_without_group_id(self):
        for grouped in (False, True):
            with self.subTest(group_id=grouped):
                rows, hosts = seed(group_id=grouped)
                self.assertEqual(len(hosts), 5)
                matched = [host for host in hosts if host["inbound_id"] == rows["hysteria2"]["id"]]
                self.assertEqual(len(matched), 1)
                host = matched[0]
                self.assertEqual({key: host[key] for key in ("remark", "address", "port", "security", "is_disabled")}, {
                    "remark": "hysteria2", "address": "deploy.example", "port": 443,
                    "security": "same", "is_disabled": 0,
                })
                self.assertEqual(json.loads(host["alpn"]), [])
                for key in ("fingerprint", "sni", "final_mask", "mux_params", "sockopt_params"):
                    self.assertEqual(host[key], "")
                if grouped:
                    self.assertEqual(len({host["group_id"] for host in hosts}), 5)
                    for host in hosts:
                        self.assertRegex(host["group_id"], r"^[a-z0-9]{16}$")
                else:
                    self.assertNotIn("group_id", host)

    def test_reality_profile_is_preserved(self):
        row = inbounds()["reality"]
        self.assertEqual((row["port"], row["listen"], row["tag"]), ("8443", "127.0.0.1", "inbound-8443"))
        self.assertEqual(json.loads(row["settings"]), {"clients": [], "decryption": "none", "encryption": "none", "fallbacks": []})
        self.assertEqual(json.loads(row["stream_settings"]), {
            "network": "tcp", "security": "reality",
            "realitySettings": {
                "show": False, "xver": 0, "target": "127.0.0.1:9443",
                "serverNames": ["cover.example"], "privateKey": "test-private",
                "minClient": "", "maxClient": "", "maxTimediff": 0,
                "shortIds": list("abcdefgh"),
                "settings": {"publicKey": "test-public", "fingerprint": "firefox", "serverName": "", "spiderX": "/"},
            },
            "tcpSettings": {"acceptProxyProtocol": True, "header": {"type": "none"}},
        })

    def test_nginx_prefix_and_headers(self):
        self.assertIn("xhttp_path=$(gen_random_string 10)", SOURCE)
        for path in ("Session7AbC", "1234567890"):
            with self.subTest(path=path):
                shared = render(SHARED, xhttp_path=path)
                location = re.search(r"location \^~ /" + path + r"/ \{([^{}]*)\}", shared)
                self.assertIsNotNone(location, "XHTTP session subpaths need a protected prefix")
                directives = [shlex.split(part.strip()) for part in location[1].split(";") if part.strip()]
                self.assertCountEqual(directives, [
                    ["client_max_body_size", "0"], ["client_body_timeout", "1h"],
                    ["grpc_read_timeout", "1h"], ["grpc_send_timeout", "1h"],
                    ["grpc_set_header", "Connection", ""], ["grpc_set_header", "Host", "$host"],
                    ["grpc_set_header", "X-Real-IP", "$remote_addr"],
                    ["grpc_set_header", "X-Forwarded-For", "$remote_addr"],
                    ["grpc_pass", "unix:/dev/shm/uds2023.sock"],
                ])
                stream = json.loads(inbounds(xhttp_path=path)["xhttp"]["stream_settings"])
                self.assertEqual(stream["xhttpSettings"]["path"] + "/", f"/{path}/")

    def test_http2_and_real_ip_chain(self):
        main = render(MAIN)
        for directive in (
            "http2_max_concurrent_streams 256;", "http2_body_preread_size 128k;",
            "client_body_buffer_size 512k;", "real_ip_header proxy_protocol;",
            "set_real_ip_from 127.0.0.1;", "listen 127.0.0.1:7443 ssl http2 proxy_protocol;",
        ):
            self.assertIn(directive, main)
        stream = render("cat > /etc/nginx/stream-enabled/stream.conf")
        self.assertIn("proxy_protocol on;", stream)
        self.assertIn("cover.example    xray;", stream)
        self.assertIn("deploy.example            www;", stream)

    def test_fixed_transport_routes_and_backend_authorities(self):
        rows = inbounds()
        ws_path = json.loads(rows["ws"]["stream_settings"])["wsSettings"]["path"]
        grpc = json.loads(rows["trojan-grpc"]["stream_settings"])["grpcSettings"]
        self.assertFalse(grpc["multiMode"])
        # Xray 26.9.30 grpc/config.go + encoding/customSeviceName.go:
        # custom /service/method paths are used verbatim, without a /Tun suffix.
        grpc_path, multi_method = grpc["serviceName"].split("|")
        self.assertEqual(multi_method,grpc_path.rsplit("/",1)[1]+"-multi")
        allowed_ports = {FIXTURE[key] for key in ("ws_port", "trojan_port", "panel_port", "sub_port", "mtr_backend_port")}
        source = SOURCE
        shared = render(SHARED, source)
        self.assertNotIn("(?<fwdport>", shared)
        self.assertNotIn("$fwdport", shared)
        fragments = [shared, render(MAIN, source), render('cat > "/etc/nginx/sites-available/${reality_domain}"', source)]
        for fragment in fragments:
            for target in re.findall(r"\b(?:proxy_pass|grpc_pass)\s+([^;]+);", fragment):
                if target.startswith("unix:") or target.startswith("grpc://unix:"):
                    self.assertNotIn("$", target)
                    continue
                authority = re.match(r"^(?:https?|grpc)://127\.0\.0\.1:([0-9]+)(?:/.*)?$", target)
                self.assertIsNotNone(authority, f"Backend authority must be a fixed loopback port: {target}")
                self.assertIn(authority[1], allowed_ports)
        def exact(path):
            matches = re.findall(r"location = " + re.escape(path) + r" \{\n(.*?)\n    \}", shared, re.S)
            self.assertEqual(len(matches), 1)
            return matches[0]
        ws = exact(ws_path)
        for directive in (
            "proxy_pass http://127.0.0.1:10003;", "proxy_http_version 1.1;",
            "proxy_set_header Upgrade $http_upgrade;", 'proxy_set_header Connection "upgrade";',
            "proxy_set_header Host $host;", "proxy_set_header X-Real-IP $remote_addr;",
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "proxy_buffering off;", "proxy_request_buffering off;",
            "proxy_socket_keepalive on;", "proxy_read_timeout 1d;",
        ):
            self.assertIn(directive, ws)
        trojan = exact(grpc_path)
        for directive in (
            "grpc_pass grpc://127.0.0.1:10004;", "grpc_read_timeout 1d;",
            "grpc_socket_keepalive on;", "client_body_timeout 1d;", "grpc_set_header Host $host;",
        ):
            self.assertIn(directive, trojan)
        # The only regex route remains the existing subscription handler.
        self.assertEqual(re.findall(r"location ~[^\n]+", shared), ["location ~ ^/subscription/(?<clash_sub_id>[^/]+)$ {"])


    def test_nginx_runtime_rejects_arbitrary_ports_and_preserves_ws(self):
        nginx = os.environ.get("NGINX_BIN") or shutil.which("nginx")
        if not nginx:
            self.skipTest("nginx unavailable; CI requires this runtime check")

        class Backend(ThreadingHTTPServer):
            def get_request(self):
                result = super().get_request()
                self.connections += 1
                return result

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                self.server.hits.append((self.path, self.request_version, dict(self.headers)))
                upgrade = self.headers.get("Upgrade") == "websocket"
                self.send_response(101 if upgrade else 200)
                if upgrade:
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "upgrade")
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_POST = do_GET

            def log_message(self, *args):
                pass

        allowed = Backend(("127.0.0.1", 0), Handler)
        forbidden = Backend(("127.0.0.1", 0), Handler)
        for backend in (allowed, forbidden):
            backend.hits, backend.connections = [], 0
            threading.Thread(target=backend.serve_forever, daemon=True).start()
        try:
            port = str(allowed.server_port)
            source = SOURCE
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with socket.socket() as reserved:
                    reserved.bind(("127.0.0.1", 0))
                    public_port = reserved.getsockname()[1]
                shared = render(SHARED, source, ws_port=port, ws_path="websocket", ws_route=f"/{port}/websocket")
                (root / "includes.conf").write_text(shared)
                temp_paths = "".join(f"{kind}_temp_path {root}/{kind};\n" for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
                config = root / "nginx.conf"
                config.write_text(
                    f"pid {root}/nginx.pid;\nerror_log stderr;\nevents {{ worker_connections 32; }}\n"
                    "http { access_log off;\n" + temp_paths +
                    f"server {{ listen 127.0.0.1:{public_port}; server_name deploy.example cover.example;\n"
                    f"root {root}; set $hack 0; set $serve_clash_yaml 0; include {root}/includes.conf; }} }}\n"
                )
                with (root / "nginx.log").open("w+") as log:
                    process = subprocess.Popen([nginx, "-p", tmp + "/", "-c", str(config), "-g", "daemon off; master_process off;"], stdout=log, stderr=log)
                    try:
                        for _ in range(60):
                            self.assertIsNone(process.poll(), "nginx exited during startup")
                            try:
                                with socket.create_connection(("127.0.0.1", public_port), timeout=0.1):
                                    break
                            except OSError:
                                time.sleep(0.025)
                        else:
                            self.fail("nginx did not start")
                        def request(host, path, method="GET", **headers):
                            connection = http.client.HTTPConnection("127.0.0.1", public_port, timeout=3)
                            try:
                                connection.request(method, path, headers={"Host": host, **headers})
                                response = connection.getresponse()
                                response.read()
                                return response.status
                            finally:
                                connection.close()
                        before = allowed.connections
                        for host in ("deploy.example", "cover.example"):
                            for path in ("/3000/test", "/9090/api", f"/{forbidden.server_port}/api/mtr", f"/{port}/wrong", f"/{port}/websocket/extra", "/10004/trojan/Tun"):
                                for method, headers in (("GET", {}), ("GET", {"Upgrade": "websocket", "Connection": "upgrade"}), ("POST", {"Content-Type": "application/grpc"})):
                                    self.assertEqual(request(host, path, method, **headers), 404)
                        self.assertEqual(forbidden.connections, 0, "Unmanaged backend must never receive a connection")
                        self.assertEqual(allowed.connections, before, "Wrong paths must not reach the managed backend")
                        for host in ("deploy.example", "cover.example"):
                            self.assertEqual(request(host, f"/{port}/websocket?token=test", Upgrade="websocket", Connection="upgrade"), 101)
                            path, version, headers = allowed.hits[-1]
                            self.assertEqual(path, f"/{port}/websocket?token=test")
                            self.assertEqual(version, "HTTP/1.1")
                            self.assertEqual(headers["Host"], host)
                            self.assertEqual(headers["Upgrade"], "websocket")
                            self.assertEqual(headers["Connection"], "upgrade")
                            self.assertEqual(headers["X-Real-IP"], "127.0.0.1")
                            self.assertEqual(headers["X-Forwarded-For"], "127.0.0.1")
                    finally:
                        process.terminate()
                        process.wait(timeout=5)
        finally:
            for backend in (allowed, forbidden):
                backend.shutdown()
                backend.server_close()

    def test_stack_runtime_source(self):
        self.assertEqual(re.findall(r'^\s*GITHUB_RAW="(.*)"$', SOURCE, re.M), [
            "https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/${PROJECT_REF}",
        ])
        self.assertIn('PROJECT_REF="${XUI_AUTO_REF:-main}"', SOURCE)
        for line in SOURCE.splitlines():
            if "raw.githubusercontent.com/mozaroc/3x-ui-pro" in line:
                self.assertTrue(line.lstrip().startswith("#"), "Unexpected upstream runtime source")

    def test_project_asset_ref_validation_precedes_downloads(self):
        initialization = SOURCE[SOURCE.index('PROJECT_REF='):SOURCE.index('FAKE_SITE_COUNT=')]
        accepted = (None, '', 'main', 'a1' * 20, 'AB' * 20, 'v1.4.1', 'v0.0.0')
        rejected = ('personal', 'feature/path', 'v1.2', 'v1.2.3-rc.1', 'v01.2.3', 'a' * 39,
                    'g' * 40, 'main/../other', ' main', 'main\n', '$(touch forbidden)')
        for ref in (*accepted, *rejected):
            with self.subTest(ref=ref):
                env = {k:v for k,v in os.environ.items() if k != 'XUI_AUTO_REF'}
                if ref is not None: env['XUI_AUTO_REF'] = ref
                script = 'msg_err() { echo "$*" >&2; }\ncurl() { echo downloaded; }\n' + initialization
                script += '\ncurl "$GITHUB_RAW/assets/backup/x-ui-backup.sh"\nprintf "REF|%s|%s\\n" "$PROJECT_REF" "$GITHUB_RAW"\n'
                result = subprocess.run(['bash','-eu','-c',script],env=env,text=True,capture_output=True)
                valid = ref in accepted
                self.assertEqual(result.returncode, 0 if valid else 1, result.stderr)
                self.assertEqual('downloaded' in result.stdout, valid)
                if valid:
                    selected = ref or 'main'
                    self.assertIn(f'REF|{selected}|https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/{selected}', result.stdout)
                else: self.assertIn('Invalid XUI_AUTO_REF', result.stderr)
        self.assertLess(SOURCE.index('configure_project_source || exit 1'), SOURCE.index('clean_previous_install()'))

    def test_all_project_assets_follow_selected_ref(self):
        from certificate_fixtures import relocate
        mock = r'''
msg_err() { echo "$*" >&2; }
msg_ok() { :; }
chown() { :; }
setcap() { :; }
id() { return 0; }
systemctl() { :; }
dd() { local arg; for arg in "$@"; do [[ "$arg" != of=* ]] || : > "${arg#of=}"; done; return 0; }
curl() {
    local url='' output='' previous='' arg
    for arg in "$@"; do
        [[ "$arg" != https://* ]] || url=$arg
        [[ "$previous" != -o ]] || output=$arg
        previous=$arg
    done
    printf '%s\n' "$url" >> "$ASSET_LOG"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$output"
}
'''
        initialization = SOURCE[SOURCE.index('PROJECT_REF='):SOURCE.index('FAKE_SITE_COUNT=')]
        names = ('install_clash_sub','install_fake_site','install_diagnostics','install_backup_tool')
        expected = {'assets/clash/clash.yaml','assets/fake-sites/site-01/index.html',
                    'assets/diagnostics/index.html','assets/diagnostics/librespeed/speedtest.js',
                    'assets/diagnostics/librespeed/speedtest_worker.js','assets/diagnostics/mtr-backend.py',
                    'assets/backup/x-ui-backup.sh'}
        for ref in ('main','a1' * 20,'v1.4.1'):
            with self.subTest(ref=ref), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root/'etc/systemd/system').mkdir(parents=True)
                script = mock + initialization + '\nFAKE_SITE_COUNT=1\n'
                script += '\n'.join(relocate(function(name),root) for name in names)
                script += '\n' + '\n'.join(names)
                log = root/'urls'
                result = subprocess.run(['bash','-eu','-c',script],text=True,capture_output=True,env={
                    **os.environ, **FIXTURE,'XUI_AUTO_REF':ref,'ASSET_LOG':str(log),'IP4':'192.0.2.10'})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertCountEqual(log.read_text().splitlines(),[
                    f'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/{ref}/{path}' for path in expected])

    def test_panel_bootstrap_uses_final_random_config_without_starting_services(self):
        self.assertNotIn("asdfasdf", SOURCE)
        self.assertNotIn('"2096"', SOURCE)
        initial = function("_panel_initial_config")
        for name in ("install_panel", "configure_xui_db"):
            self.assertNotRegex(function(name), r"(?m)^\s*(?:systemctl\s+(?:start|restart)\s+x-ui|x-ui\s+(?:start|restart))\b")
        main = function("main")
        self.assertEqual(len(re.findall(r"(?m)^\s*x-ui restart\b", main)), 1)
        self.assertGreater(main.index("x-ui restart"), main.index("configure_xui_db"))
        self.assertRegex(main, r"install_panel\s*\|\|\s*exit 1")
        self.assertRegex(main, r"configure_xui_db\s*\|\|\s*exit 1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "calls"
            executable = root / "panel"
            executable.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["PANEL_TEST_LOG"], "a") as log: log.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(1 if sys.argv[1] == os.environ["FAIL_PANEL_COMMAND"] else 0)
''')
            executable.chmod(0o755)
            script = 'sqlite3() { [[ "$*" == *SELECT* ]] && echo "$PANEL_SAVED_STATE"; return 0; }\nmsg_err() { echo "$*" >&2; }\n' + initial.replace("/usr/local/x-ui/x-ui", str(executable)) + "\n_panel_initial_config\n"
            for failed in ("", "setting", "migrate", "unsaved-state"):
                with self.subTest(failed=failed):
                    log.write_text("")
                    result = subprocess.run(["bash", "-u", "-c", script], capture_output=True, text=True, env={
                        **os.environ, "PANEL_TEST_LOG": str(log), "FAIL_PANEL_COMMAND": failed,
                        "config_username": "fixture-user", "config_password": "fixture-secret",
                        "panel_port": "10002", "panel_path": "fixture-path", "XUIDB": str(root / "db"),
                        "PANEL_SAVED_STATE": "admin|0.0.0.0|2053|/" if failed == "unsaved-state" else "fixture-user|127.0.0.1|10002|/fixture-path/",
                    })
                    calls = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertEqual(calls[0], ["setting", "-username", "fixture-user", "-password", "fixture-secret",
                                                "-port", "10002", "-webBasePath", "fixture-path"])
                    self.assertEqual(calls[1:], [] if failed == "setting" else [["migrate"]])
                    self.assertEqual(result.returncode, 1 if failed else 0)

    def test_firewall_does_not_open_panel_port_for_mtls_automatically(self):
        for status, connection, expected in (
            ("active", "", ["80/tcp", "443/tcp", "443/udp"]),
            ("inactive", "198.51.100.10 54321 203.0.113.5 2222", ["80/tcp", "443/tcp", "443/udp", "2222/tcp"]),
            ("inactive", "", ["80/tcp", "443/tcp", "443/udp"]),
        ):
            with self.subTest(status=status, connection=connection):
                result, calls, _, _ = self.firewall(status, connection)
                self.assertEqual(result.returncode, 0, result.stderr)
                allowed = [call.split()[1] for call in calls if call.startswith("allow ")]
                self.assertCountEqual(allowed, expected)
                self.assertNotIn(FIXTURE["panel_port"], [rule.split("/")[0] for rule in allowed])

    def test_panel_version_minimum_is_checked_before_destructive_actions(self):
        start = SOURCE.index('while [ "$#" -gt 0 ]; do')
        end = SOURCE.index("# ─── Detect package manager")
        preflight = SOURCE[start:end]
        self.assertLess(end, SOURCE.index('    uninstall_xui || exit 1\n'))
        for version, accepted in (("v3.7.0", False), ("v3.7.99", False), ("v3.8.0", True), ("v3.8.5", True),
                                  ("v3.9.0", True), ("3.10.0", True), ("v4.0.0", True),
                                  ("v3.08.0", False), ("v3.8", False), ("latest", False), ("", False)):
            with self.subTest(version=version):
                script = 'PANEL_VERSION=""\nmsg_err() { echo "$*" >&2; }\n' + preflight + '\necho destructive-actions\n'
                result = subprocess.run(["bash", "-u", "-c", script, "fixture", "-version", version], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if accepted else 1, result.stderr)
                self.assertEqual("destructive-actions" in result.stdout, accepted)

    def test_panel_loopback_bind_and_managed_backend_listeners(self):
        rows = inbounds()
        for name in ("reality", "ws", "trojan-grpc"):
            self.assertEqual(rows[name]["listen"], "127.0.0.1", name)
        self.assertEqual((rows["hysteria2"]["listen"], rows["hysteria2"]["port"], rows["hysteria2"]["enable"]), ("", "443", "1"))
        self.assertEqual(rows["xhttp"]["listen"], "/dev/shm/uds2023.sock,0666")
        sql = render("sqlite3 $XUIDB", XUIDB="/fixture/x-ui.db").split('INSERT INTO "inbounds"', 1)[0]
        with sqlite3.connect(":memory:") as db:
            db.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)')
            db.executemany('INSERT INTO settings VALUES (?,?)', [("webListen", "0.0.0.0"), ("subListen", "::")])
            db.executescript(sql)
            values = dict(db.execute('SELECT key,value FROM settings'))
        self.assertEqual(values["webListen"], "127.0.0.1")
        self.assertNotIn("-listenIP", function("_panel_initial_config") + function("configure_xui_db"))
        self.assertEqual(values["subListen"], "127.0.0.1")

    def test_nginx_internal_tls_listeners_are_loopback_only(self):
        for target, port in ((MAIN, "7443"), ('cat > "/etc/nginx/sites-available/${reality_domain}"', "9443")):
            with self.subTest(port=port):
                self.assertEqual(re.findall(r"(?m)^\s*listen\s+(\S+)", render(target)), ["127.0.0.1:" + port])
        stream = render("cat > /etc/nginx/stream-enabled/stream.conf")
        self.assertRegex(stream, r"\blisten\s+443;")
        self.assertIn("127.0.0.1:8443", stream)
        self.assertIn("127.0.0.1:7443", stream)

    def release_stage(self, failure=""):
        # Execute only the isolated download/extraction block, relocated into a
        # private directory. curl/systemctl are mocked; tar and sha256sum are real.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "local"
            destination.mkdir()
            (destination / "x-ui").mkdir()
            (destination / "x-ui" / "old-state").write_text("preserve until verified")
            cli = root / "x-ui.sh"
            cli.write_text("#!/bin/bash\necho verified-release\n")
            archive = root / "fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                for name in ('x-ui.sh','x-ui','x-ui.service.debian','bin/xray-linux-amd64'):
                    bundle.add(cli, arcname="x-ui/"+name)
            checksum = root / "fixture.sha256"
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            checksum.write_text(("0" * 64 if failure == "mismatch" else "bad-hash" if failure == "malformed" else digest) + "  x-ui-linux-amd64.tar.gz\n")
            log = root / "calls"
            log.write_text("")
            panel = function("install_panel")
            block = ('    archive=$(mktemp /usr/local/x-ui-release.XXXXXX.tar.gz) || return 1\n'
                     '    _download_panel_archive "https://github.com/MHSanaei/3x-ui/releases/download/${tag_version}/x-ui-linux-amd64.tar.gz" "$archive" || return 1\n'
                     '    _validate_panel_archive "$archive" amd64 || return 1\n'
                     + panel[panel.index('    [[ -d /usr/local/x-ui/ ]]'):panel.index('    cd x-ui')])
            block = block.replace("/usr/local", str(destination))
            mock = '''_arch() { echo amd64; }
msg_err() { echo "$*" >&2; }
systemctl() { :; }
curl() {
    local url="" output=""
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -o) output="$2"; shift 2 ;;
            https://*) url="$1"; shift ;;
            *) shift ;;
        esac
    done
    printf '%s\\n' "$url" >> "$RELEASE_LOG"
    if [[ "$url" == *.sha256 ]]; then
        [[ "$RELEASE_FAILURE" != checksum-download ]] || { echo partial > "$output"; return 22; }
        cp "$CHECKSUM_FIXTURE" "$output"
    else
        [[ "$RELEASE_FAILURE" != archive-download ]] || { echo partial > "$output"; return 22; }
        cp "$ARCHIVE_FIXTURE" "$output"
    fi
}
tar() { echo extract >> "$RELEASE_LOG"; command tar "$@"; }
stage() {
'''
            result = subprocess.run(["bash", "-u", "-c", mock + function("_download_panel_archive") + "\n" + function('_validate_panel_archive') + "\n" + block + "\n}\nstage"],
                                    capture_output=True, text=True, env={**os.environ,
                                    "RELEASE_LOG": str(log), "RELEASE_FAILURE": failure,
                                    "ARCHIVE_FIXTURE": str(archive), "CHECKSUM_FIXTURE": str(checksum), "tag_version": "v3.9.0"})
            calls = log.read_text().splitlines()
            self.assertFalse(list(destination.glob("x-ui-release.*")), "Candidates/sidecars must not survive failure or extraction")
            if failure:
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("extract", calls, "Unverified archive must not reach tar")
                self.assertTrue((destination / "x-ui" / "old-state").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((destination / "x-ui" / "x-ui.sh").read_bytes(), cli.read_bytes())
                self.assertEqual(calls[-1], "extract")
            return calls

    def test_release_checksum_success_extracts_verified_bundled_cli(self):
        self.release_stage()

    def test_release_checksum_mismatch_or_invalid_digest_aborts_before_extraction(self):
        for failure in ("mismatch", "malformed"):
            with self.subTest(failure=failure):
                self.release_stage(failure)

    def test_release_download_failure_aborts_before_extraction(self):
        for failure in ("archive-download", "checksum-download"):
            with self.subTest(failure=failure):
                self.release_stage(failure)

    def test_ip_discovery_fallback_is_https_bounded_and_validated(self):
        self.assertNotRegex(SOURCE, r"(?<!https://)(?:ipv4|ipv6)\.icanhazip\.com")
        declarations = '\n'.join(line for line in SOURCE.splitlines() if line.startswith(('IP4_REGEX=', 'IP6_REGEX=')))
        mock = '''ip() { return 1; }
curl() {
    printf '%s\\n' "$*" >> "$IP_TEST_LOG"
    case "${@: -1}" in
        https://ipv4.icanhazip.com)
            [[ "$IP_BAD_RESULT" != 1 ]] || { echo 'IPv4 discovery failed' >&2; echo invalid; return 22; }
            echo 203.0.113.5 ;;
        https://ipv6.icanhazip.com)
            [[ "$IP_BAD_RESULT" == 0 ]] || { echo 'Optional IPv6 discovery failed' >&2; echo invalid; return 7; }
            echo 2001:db8::5 ;;
        *) return 1 ;;
    esac
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "calls"
            for bad in ("0", "1", "ipv6-only"):
                with self.subTest(bad=bad):
                    log.write_text("")
                    result = subprocess.run(["bash", "-u", "-c", mock + declarations + '\n' + function("get_server_ip") + '\nget_server_ip\nprintf "%s|%s" "$IP4" "$IP6"'],
                                            capture_output=True, text=True, env={**os.environ, "IP_TEST_LOG": str(log), "IP_BAD_RESULT": bad})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, {"0": "203.0.113.5|2001:db8::5", "1": "|", "ipv6-only": "203.0.113.5|"}[bad])
                    self.assertEqual(result.stderr, "IPv4 discovery failed\n" if bad == "1" else "")
                    for call in log.read_text().splitlines():
                        self.assertIn("-fsS", call)
                        self.assertIn("--connect-timeout 5", call)
                        self.assertIn("--max-time 10", call)

    def test_nginx_syntax(self):
        nginx = os.environ.get("NGINX_BIN") or shutil.which("nginx")
        if not nginx:
            self.skipTest("nginx unavailable; CI sets NGINX_BIN to require this check")
        version = subprocess.run([nginx, "-v"], check=True, capture_output=True, text=True)
        number = tuple(map(int, re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", version.stderr).groups()))
        http2 = {"http2_listen": "", "http2_on": "http2 on;"} if number >= (1, 25, 1) else {}
        with tempfile.TemporaryDirectory(prefix="personal-xhttp-") as tmp:
            root = Path(tmp)
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=deploy.example", "-keyout", str(root / "key.pem"),
                "-out", str(root / "cert.pem"),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            source = SOURCE
            (root / "includes.conf").write_text(render(SHARED, source))
            fragments = [render("cat > /etc/nginx/sites-available/00-maps.conf", source)]
            for target in (MAIN, 'cat > "/etc/nginx/sites-available/${reality_domain}"'):
                fragment = render(target, source, **http2)
                fragment = re.sub(r"/etc/letsencrypt/live/[^/]+/fullchain.pem", str(root / "cert.pem"), fragment)
                fragment = re.sub(r"/etc/letsencrypt/live/[^/]+/privkey.pem", str(root / "key.pem"), fragment)
                fragments.append(fragment.replace("/etc/nginx/snippets/includes.conf", str(root / "includes.conf")).replace("/etc/nginx/snippets/x-ui-auto-optional", str(root / "optional")))
            # Relocate only filesystem dependencies; generated HTTP directives stay intact.
            temp_paths = "".join(
                f"{kind}_temp_path {root}/{kind};\n"
                for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
            )
            (root / "nginx.conf").write_text(
                f"pid {root}/nginx.pid;\nerror_log stderr;\nevents {{ worker_connections 32; }}\n"
                "http {\naccess_log off;\n" + temp_paths + "\n".join(fragments) + "\n}\n"
            )
            result = subprocess.run(
                [nginx, "-t", "-p", str(root) + "/", "-c", str(root / "nginx.conf")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(f"\nnginx {'.'.join(map(str, number))}: generated HTTP vhosts syntax OK")


from test_certificate_renewal import CertificateRenewal
from test_adguard import AdGuardInstaller

from test_audit_findings import AuditInstaller


if __name__ == "__main__":
    unittest.main(verbosity=2)

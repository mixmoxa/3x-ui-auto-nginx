"""Invoke the unmodified production main() in a clean disposable systemd guest."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import time
import urllib.request

from diagnostics import vision_failure

ROOT = Path('/root/pilot')
UNITS = ('ssh', 'nginx', 'x-ui', 'mtr-backend', 'AdGuardHome', 'fail2ban',
         'apt-daily.timer', 'apt-daily-upgrade.timer', 'certbot.timer')


def mtr_api():
    unit = Path('/etc/systemd/system/mtr-backend.service').read_text()
    owner = subprocess.check_output(
        ['systemctl', 'show', 'mtr-backend', '-p', 'User', '--value'], text=True).strip()
    assert owner == 'mtr-backend'
    port = int(re.search(r'--port ([0-9]+)', unit)[1])
    # A global-looking diagnostic destination entirely inside this disposable VM.
    subprocess.run(['ip', 'addr', 'add', '8.8.8.9/32', 'dev', 'lo'], check=True, timeout=10)
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/mtr',
            data=b'{"count":1}', headers={'Content-Type': 'application/json',
                                        'X-Real-IP': '8.8.8.9'})
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.load(response)
            assert response.status == 200
        assert data['success'] and data['target'] == '8.8.8.9' and '8.8.8.9' in data['output']
    finally:
        subprocess.run(['ip', 'addr', 'del', '8.8.8.9/32', 'dev', 'lo'], check=True, timeout=10)


def install(scenario, ref):
    caller_umask = os.umask(0o077)
    report = {'scenario': scenario, 'passed': False}
    try:
        assert os.geteuid() == 0 and Path('/proc/1/comm').read_text().strip() == 'systemd'
        assert re.fullmatch('[0-9a-f]{40}', ref)
        packages = subprocess.check_output(
            ['dpkg-query', '-W', '-f=${binary:Package}\t${db:Status-Status}\n'], text=True)
        for package in ('nginx', 'nginx-common', 'certbot', 'fail2ban',
                        'unattended-upgrades', 'mtr-tiny', 'ufw'):
            assert not any(line.split('\t')[0] == package and line.endswith('\tinstalled')
                           for line in packages.splitlines()), 'Application stack preinstalled'
        for path in ('/etc/x-ui', '/usr/local/x-ui', '/opt/AdGuardHome'):
            assert not Path(path).exists(), 'Application state preinstalled'
        subprocess.run(['/usr/sbin/sshd', '-t'], check=True, capture_output=True, timeout=10)
        dns_before = (Path('/etc/resolv.conf').readlink(), Path('/etc/resolv.conf').read_bytes())
        network = Path('/etc/systemd/network/10-pilot.network').read_bytes()
        env = {**os.environ, **json.loads((ROOT/'environment.json').read_text()),
               'XUI_AUTO_REF': ref, 'CURL_CA_BUNDLE': '/etc/ssl/certs/ca-certificates.crt',
               'REQUESTS_CA_BUNDLE': '/etc/ssl/certs/ca-certificates.crt'}
        os.environ.update(env)
        started = time.monotonic()
        context = ssl.create_default_context(cafile=str(ROOT/'fixture.crt'))
        with urllib.request.urlopen('https://10.0.2.2:15000/roots/0', context=context, timeout=10) as response:
            Path('/usr/local/share/ca-certificates/pilot-pebble.crt').write_bytes(response.read())
        subprocess.run(['update-ca-certificates'], check=True, capture_output=True, timeout=120)
        report['trust_seconds'] = round(time.monotonic()-started, 2)
        if scenario == 'dependency':
            Path('/etc/apt/preferences.d/pilot-mandatory-failure').write_text(
                'Package: nginx-full\nPin: version *\nPin-Priority: -1\n')
        answers = b'y\ny\nvision.example.test\ny\ny\ny\n' if scenario != 'dot-outage' else b'y\nn\nn\nn\ny\n'
        started = time.monotonic()
        with (ROOT/'installer.raw.log').open('wb') as log:
            result = subprocess.run(['bash', str(ROOT/'x-ui-latest.sh'), '-subdomain',
                'panel.example.test', '-reality_domain', 'reality.example.test'],
                input=answers, stdout=log, stderr=subprocess.STDOUT, env=env, umask=caller_umask,
                timeout=1200)
        report.update(main_exit=result.returncode, main_seconds=round(time.monotonic()-started, 2),
                      installer_sha256=hashlib.sha256((ROOT/'x-ui-latest.sh').read_bytes()).hexdigest())
        private = re.sub(r'\x1b\[[0-9;]*m', '', (ROOT/'installer.raw.log').read_text(errors='replace'))
        vision = vision_failure(private)
        if vision is not None: report['vision_failure'] = vision
        # Public diagnostics are fixed booleans, never log lines or secret URLs.
        patterns = {
            'core_running': r'\[✓\]\s+3X-UI / Xray\s+Running',
            'dot_configured': r'Global DoT — Configured',
            'fail2ban_configured': r'Fail2ban — Configured',
            'apt_configured': r'APT security — Configured',
            'vision_ready': r'\[✓\]\s+VLESS TLS Vision\s+Ready',
            'awg_configured': r'\[✓\]\s+AmneziaWG\s+Configured',
            'agh_running': r'\[✓\]\s+AdGuard Home\s+Running',
            'client_created': r'\[✓\]\s+Client\s+Created',
            'subscription_ready': r'\[✓\]\s+Subscription\s+Ready',
            'dns_rollback_verified': r'DoT unavailable; original DNS restored\.',
            'rollback_unverified': r'rollback not verified',
            'core_health_unverified': r'Post-rollback health not verified',
            'xray_runtime_failure': r'Xray must own the REALITY TCP, live XHTTP Unix and Hysteria2 UDP listeners',
        }
        report['components'] = {name: bool(re.search(pattern, private)) for name, pattern in patterns.items()}
        subprocess.run(['systemctl', 'is-active', '--quiet', 'ssh'], check=True, timeout=10)
        subprocess.run(['getent', 'ahosts', 'debian.org'], check=True, capture_output=True, timeout=30)
        if scenario == 'dependency':
            assert result.returncode != 0, 'Mandatory dependency failure returned success'
            assert 'Dependency setup failed.' in private, 'Intended dependency fault point not reached'
            assert 'nginx-full' in private and 'no installation candidate' in private.lower()
            assert 'Installation Result' not in private, 'Mandatory failure displayed success summary'
            assert not Path('/usr/local/x-ui/x-ui').exists()
        else:
            required = [u for u in UNITS if scenario == 'positive' or u != 'AdGuardHome']
            for unit in required:
                subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=True, timeout=10)
            assert re.search(r'^ Username: \S+$', private, re.M)
            assert re.search(r'^ Password: \S+$', private, re.M)
            assert re.search(r'\[✓\]\s+Client\s+Created', private)
            assert re.search(r'\[✓\]\s+Subscription\s+Ready', private)
            if scenario == 'positive':
                assert result.returncode == 0, 'Maximum installation failed'
                for component in ('Global DoT', 'Fail2ban', 'APT security'):
                    assert component+' — Configured' in private
            else:
                assert result.returncode != 0, 'Requested DoT outage reported full success'
                assert 'DoT unavailable; original DNS restored.' in private
                assert 'Global DoT — Failed, rolled back / unchanged' in private
                assert 'Fail2ban — Configured' in private and 'APT security — Configured' in private
                assert (Path('/etc/resolv.conf').readlink(), Path('/etc/resolv.conf').read_bytes()) == dns_before
                assert Path('/etc/systemd/network/10-pilot.network').read_bytes() == network
                assert not Path('/etc/systemd/resolved.conf.d/90-3x-ui-auto-nginx.conf').exists()
                subprocess.run(['fail2ban-client', 'status', 'sshd'], check=True,
                               capture_output=True, timeout=15)
            mtr_api()
            report['restricted_mtr_http'] = True
        report['passed'] = True
    finally:
        (ROOT/'install-result.json').write_text(json.dumps(report))

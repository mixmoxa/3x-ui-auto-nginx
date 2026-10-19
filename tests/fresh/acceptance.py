"""One disk-based Ubuntu 26.04 acceptance, using real main(), services and consumers."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import traceback

from diagnostics import VISION_STAGES

ROOT = Path('/pilot')
REPO = Path('/repo')
os.umask(0o077)
processes = []
vm = None
phase = 'prepare'
report = {}


def launch(args, name, env=None):
    with (ROOT/(name+'.private.log')).open('wb') as log:
        process = subprocess.Popen(args, stdout=log, stderr=log, env=env)
    processes.append(process)
    return process


def ssh(command, timeout=30):
    return subprocess.run(['ssh', '-i', '/pilot/ssh-key', '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'UserKnownHostsFile=/pilot/known_hosts', '-o', 'ConnectTimeout=3',
        '-p', '22220', 'root@127.0.0.1', command], capture_output=True, timeout=timeout)


def failure_location(output):
    # Source locations identify the failed assertion without exposing the
    # exception text, API response, command arguments or raw installer log.
    frames = re.findall(rb'File "/root/pilot/(checks|install|client|session)\.py", line ([0-9]+)', output)
    if frames:
        name, line = frames[-1]
        report['failure_location'] = name.decode()+'.py:'+line.decode()


def boot():
    global vm
    started = time.monotonic()
    kernel = (ROOT/'kernel.path').read_text().strip()
    report['kernel'] = Path(kernel).name
    vm = launch(['qemu-system-x86_64', '-machine', 'accel=tcg', '-cpu', 'max', '-m', '4096',
        '-smp', '2', '-nodefaults', '-no-reboot', '-display', 'none', '-serial', 'stdio',
        '-monitor', 'none', '-drive', 'file=/pilot/disk.raw,format=raw,if=virtio',
        '-netdev', 'user,id=n0,hostfwd=tcp:127.0.0.1:22220-:22,hostfwd=tcp:127.0.0.1:18080-:80',
        '-device', 'virtio-net-pci,netdev=n0', '-kernel', kernel, '-initrd', '/pilot/initrd.img',
        '-append', 'root=/dev/vda rw rootfstype=ext4 console=ttyS0 panic=1 quiet net.ifnames=0 '
                   'systemd.show_status=true systemd.log_target=console'], phase+'-serial')
    deadline = started+180
    while time.monotonic() < deadline:
        if vm.poll() is not None:
            raise RuntimeError('QEMU exited during boot')
        try:
            ready = ssh('test "$(cat /proc/1/comm)" = systemd && systemctl is-active --quiet ssh '
                        '&& systemctl is-active --quiet pilot-external-network', 10)
        except subprocess.TimeoutExpired:
            continue
        if ready.returncode == 0:
            report[phase+'_boot_seconds'] = round(time.monotonic()-started, 2)
            return
        time.sleep(.5)
    raise RuntimeError('SSH/systemd readiness exceeded 180 seconds')


def poweroff():
    ssh('systemctl poweroff', 15)
    vm.wait(timeout=30)


def invoke(expression, result_name, timeout=180):
    started = time.monotonic()
    # No credentials are passed in argv or printed; all guest stdout stays private.
    code = ('import sys,json;from pathlib import Path;sys.path.insert(0,"/root/pilot");'
            'Path("/root/pilot/dns-diagnostics.jsonl").unlink(missing_ok=True);'
            'import checks,install;result='+expression+';'
            'Path("/root/pilot/'+result_name+'.json").write_text(json.dumps(result))')
    import shlex
    result = ssh('python3 -c '+shlex.quote(code), timeout)
    (ROOT/(phase+'.private.log')).write_bytes(result.stdout+result.stderr)
    diagnostics = ssh('cat /root/pilot/dns-diagnostics.jsonl', 15)
    if diagnostics.returncode == 0:
        probes = [json.loads(line) for line in diagnostics.stdout.splitlines()]
        allowed = {'probe','rcode','transaction_id_match','answer_records','expected_a',
                   'response_length','elapsed_seconds','parse_valid','transport_error'}
        for probe in probes:
            assert set(probe) <= allowed and probe['probe'] in ('native_udp','doh_get','doh_post')
            assert probe['rcode'] is None or type(probe['rcode']) is int and 0 <= probe['rcode'] <= 15
            for key in ('transaction_id_match','expected_a','parse_valid'):
                assert type(probe[key]) is bool
            for key in ('answer_records','response_length','elapsed_seconds'):
                assert type(probe[key]) in (int, float) and probe[key] >= 0
            if 'transport_error' in probe: assert type(probe['transport_error']) is bool
        report[phase+'_dns_probes'] = probes
    if result.returncode:
        failure_location(result.stderr)
        raise AssertionError('Guest phase failed; private output is not published')
    data = ssh('cat /root/pilot/'+result_name+'.json', 15)
    if data.returncode:
        raise AssertionError('Guest result unavailable')
    values = json.loads(data.stdout)
    assert isinstance(values, dict) and values and all(v is True for v in values.values())
    report[phase] = 'PASS'
    report[phase+'_seconds'] = round(time.monotonic()-started, 2)
    print(phase+': PASS', flush=True)


def install(scenario, ref):
    import shlex
    code = 'import sys;sys.path.insert(0,"/root/pilot");import install;install.install('+repr(scenario)+','+repr(ref)+')'
    result = ssh('python3 -c '+shlex.quote(code), 1320)
    (ROOT/(phase+'.private.log')).write_bytes(result.stdout+result.stderr)
    if result.returncode:
        failure_location(result.stderr)
    data = ssh('cat /root/pilot/install-result.json', 20)
    if data.returncode:
        raise AssertionError('Install result unavailable')
    values = json.loads(data.stdout)
    (ROOT/(phase+'-result.json')).write_bytes(data.stdout)
    vision = values.get('vision_failure')
    if vision is not None:
        assert set(vision) == {'stage','exit_code','rollback'}
        assert vision['stage'] in set(VISION_STAGES.values()) | {'unknown'}
        assert type(vision['exit_code']) is int and 0 <= vision['exit_code'] <= 999
        assert vision['rollback'] in ('failed_rolled_back','failed_unverified','unknown')
        report[phase+'_vision_failure'] = vision
    flags = values.get('components', {})
    allowed = {'core_running','dot_configured','fail2ban_configured','apt_configured','vision_ready',
               'awg_configured','agh_running','client_created','subscription_ready','dns_rollback_verified',
               'rollback_unverified','core_health_unverified','xray_runtime_failure'}
    assert isinstance(flags, dict) and set(flags) <= allowed and all(type(v) is bool for v in flags.values())
    report[phase+'_components'] = flags
    print(phase+' components: '+json.dumps(flags, sort_keys=True), flush=True)
    for key in ('main_seconds', 'trust_seconds', 'main_exit'):
        assert type(values[key]) in (int, float)
        report[phase+'_'+key] = values[key]
    assert result.returncode == 0 and values['passed'] is True, 'Unexpected real-main result'
    assert values['installer_sha256'] == hashlib.sha256((REPO/'x-ui-latest.sh').read_bytes()).hexdigest()
    report[phase] = 'PASS'
    print(phase+': PASS (main exit '+str(values['main_exit'])+', '+str(values['main_seconds'])+'s)', flush=True)


def fresh_disk():
    assert vm is None or vm.poll() is not None
    subprocess.run(['cp', '--reflink=auto', '--sparse=always', '/pilot/clean.raw', '/pilot/disk.raw'],
                   check=True, timeout=60)


def fixtures():
    # Reuse the existing services suite's authoritative public artifact pin.
    constants = {}
    for node in ast.parse((REPO/'tests/test_real_services.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('PEBBLE_VERSION', 'PEBBLE_SHA'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    archive = ROOT/'pebble.tar.gz'
    url = ('https://github.com/letsencrypt/pebble/releases/download/'
           +constants['PEBBLE_VERSION']+'/pebble-linux-amd64.tar.gz')
    subprocess.run(['curl', '-q', '-fLsS', '--retry', '3', '--connect-timeout', '15',
                    '--max-time', '180', url, '-o', str(archive)], check=True, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == constants['PEBBLE_SHA']
    import tarfile
    with tarfile.open(archive) as tar:
        source = tar.extractfile('pebble-linux-amd64/linux/amd64/pebble')
        assert source is not None
        (ROOT/'pebble').write_bytes(source.read())
    (ROOT/'pebble').chmod(0o700)
    launch(['python3', '/repo/tests/fresh/fixtures.py'], 'external-fixtures')
    config = {'pebble': {'listenAddress': '0.0.0.0:14000',
        'managementListenAddress': '127.0.0.1:15000', 'certificate': '/pilot/fixture.crt',
        'privateKey': '/pilot/fixture.key', 'httpPort': 18080, 'tlsPort': 15001,
        'ocspResponderURL': '', 'externalAccountBindingRequired': False,
        'retryAfter': {'authz': 1, 'order': 1}}}
    (ROOT/'pebble.json').write_text(json.dumps(config))
    launch(['/pilot/pebble', '-config', '/pilot/pebble.json', '-dnsserver', '127.0.0.1:1053'],
        'pebble', {**os.environ, 'PEBBLE_VA_NOSLEEP': '1', 'PEBBLE_VA_ALWAYS_VALID': '0',
            'PEBBLE_WFE_NONCEREJECT': '0', 'PEBBLE_AUTHZREUSE': '0', 'NO_PROXY': 'localhost,127.0.0.1'})
    deadline = time.monotonic()+20
    for port in (53, 443, 853, 1053, 14000, 15000, 18081):
        while True:
            assert all(p.poll() is None for p in processes), 'External fixture exited'
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.3):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('External fixture readiness deadline')
                time.sleep(.05)


if __name__ == '__main__':
    ref = os.environ['XUI_AUTO_REF']
    assert re.fullmatch('[0-9a-f]{40}', ref)
    sampling = threading.Event()
    def sample():
        while not sampling.wait(.5):
            try:
                if vm is not None and vm.poll() is None:
                    status = Path(f'/proc/{vm.pid}/status').read_text()
                    rss = int(next(l.split()[1] for l in status.splitlines() if l.startswith('VmHWM:')))*1024
                    report['qemu_peak_rss_bytes'] = max(report.get('qemu_peak_rss_bytes', 0), rss)
                disk = ROOT/'disk.raw'
                if disk.exists():
                    report['disk_allocated_bytes'] = max(report.get('disk_allocated_bytes', 0), disk.stat().st_blocks*512)
            except (OSError, StopIteration):
                pass
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        report['image_prepare_seconds'] = int((ROOT/'images.ready').read_text())-int((ROOT/'started').read_text())
        report['disk_prepare_seconds'] = int((ROOT/'disk.ready').read_text())-int((ROOT/'images.ready').read_text())
        fixtures()
        fresh_disk()
        phase = 'maximum-install'
        boot()
        install('positive', ref)
        invoke('checks.installed()', 'installed')
        phase = 'transport-consumers'
        invoke('checks.transports()', 'transports', 300)
        phase = 'AWG-payload'
        invoke('checks.amneziawg()', 'awg', 120)
        phase = 'tech0-RED-GREEN'
        invoke('checks.search_domain_regression()', 'tech0', 120)
        phase = 'installed-renewal-hooks'
        invoke('checks.renewal()', 'renewal', 300)
        identity = ssh('cat /proc/sys/kernel/random/boot_id', 10)
        assert identity.returncode == 0 and re.fullmatch(rb'[a-f0-9-]{36}\n', identity.stdout)
        # The second QEMU process boots exactly the same installed disk.
        command = "tr -d '-' < /proc/sys/kernel/random/boot_id > /root/pilot/first-boot-id"
        assert ssh(command, 10).returncode == 0
        poweroff()
        phase = 'cold-boot'
        boot()
        invoke('checks.installed(cold=True)', 'cold')
        phase = 'cold-transport-consumers'
        invoke('checks.transports()', 'cold-transports', 300)
        poweroff()
        phase = 'mandatory-dependency-negative'
        fresh_disk()
        boot()
        install('dependency', ref)
        poweroff()
        phase = 'DoT-outage-partial-install'
        fresh_disk()
        (ROOT/'dot-outage').touch()
        boot()
        install('dot-outage', ref)
        phase = 'DoT-outage-core-consumers'
        invoke('checks.transports(vision=False)', 'partial-transports', 240)
        poweroff()
        report['result'] = 'PASS'
    except Exception as error:
        (ROOT/'failure.private.log').write_text(traceback.format_exc())
        report['result'] = 'FAIL'
        report['error_class'] = type(error).__name__
        print(phase+': FAIL; private logs/images are never uploaded', flush=True)
        raise SystemExit(1)
    finally:
        sampling.set()
        sampler.join(timeout=2)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        peak = Path('/sys/fs/cgroup/memory.peak')
        if peak.exists():
            report['container_peak_bytes'] = int(peak.read_text())
        report['total_seconds'] = round(time.time()-float((ROOT/'started').read_text()), 2)
        (ROOT/'summary.json').write_text(json.dumps(report))
        print(json.dumps(report, sort_keys=True), flush=True)

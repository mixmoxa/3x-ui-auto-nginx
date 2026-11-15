"""Fresh-install WARP MASQUE through the official panel; never register twice."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time


RU3_DOMAINS = (
    'domain:ipify.org', 'domain:ifconfig.me', 'full:checkip.amazonaws.com',
    'domain:ipapi.is', 'domain:iplocate.io', 'domain:ip.sb', 'domain:2gis.com',
)
COMMENTS = ('WARP - RU', 'WARP - RU2', 'WARP - RU3')
ROUTE_DOMAINS = (
    'yandex.ru', 'api.ipify.org', 'ifconfig.me', 'checkip.amazonaws.com',
    'api.ipapi.is', 'www.iplocate.io', 'api.ip.sb', 'relay-api.eu.2gis.com',
)


def read_template(panel):
    return json.loads(panel.request('panel/api/xray/', method='POST')['obj'])


def validate(template):
    outbounds = template['outbounds']
    rules = template['routing']['rules']
    if not isinstance(outbounds, list) or not isinstance(rules, list):
        raise ValueError('Template lists missing')
    if any(o.get('tag') == 'warp-masque' for o in outbounds):
        raise ValueError('Existing WARP outbound')
    if any(r.get('comment') in COMMENTS for r in rules):
        raise ValueError('Existing WARP rule')


def merge(template, registration):
    result = copy.deepcopy(template)
    result['outbounds'].append(dict(
        tag='warp-masque', protocol='masque',
        settings=dict(address=registration['endpoint'], port=443),
        streamSettings=dict(network='masque', security='tls',
            tlsSettings=dict(serverName='consumer-masque.cloudflareclient.com', alpn=['h3']),
            masqueSettings=dict(warp={k: registration[k] for k in ('privateKey', 'publicKey', 'address')}))))
    for comment, criterion in zip(COMMENTS, (
            dict(domain=['geosite:category-ru']), dict(ip=['geoip:ru']), dict(domain=list(RU3_DOMAINS)))):
        result['routing']['rules'].append(dict(type='field', outboundTag='warp-masque',
                                             comment=comment, enabled=True, **criterion))
    return result


def probe_ok(result):
    return (isinstance(result, dict) and result.get('success') is True and
            result.get('tag') == 'warp-masque' and result.get('mode') == 'real' and
            type(result.get('delay')) is int and result['delay'] > 0 and
            type(result.get('httpStatus')) is int and result['httpStatus'] > 0 and not result.get('error'))


def test_routes(panel):
    targets = [(dict(domain=d), True) for d in ROUTE_DOMAINS]
    # Confirmed in geoip:ru of the verified baseline; synthetic, no traffic sent.
    targets.append((dict(ip='77.88.55.88'), True))
    targets += [(dict(domain=d), False) for d in ('example.com', 's3.amazonaws.com')]
    for destination, expected in targets:
        result = panel.request('panel/api/xray/routeTest', dict(network='tcp', port=443, **destination),
                               method='POST', form=True, timeout=10)['obj']
        if not isinstance(result, dict) or type(result.get('matched')) is not bool or not isinstance(result.get('outboundTag'), str):
            raise ValueError('Unknown route result')
        matched, tag = result['matched'], result['outboundTag']
        if expected:
            valid = matched and tag == 'warp-masque'
        else:
            valid = (matched and bool(tag) and tag != 'warp-masque') or (not matched and tag == '')
        if not valid:
            raise ValueError('Route mismatch')


def save(panel, template, test_url):
    panel.request('panel/api/xray/update', dict(xraySetting=json.dumps(template), outboundTestUrl=test_url),
                  method='POST', form=True)


def private_json(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as output:
        json.dump(value, output)


def failed(step):
    # Exception messages and response bodies can contain keys or credentials.
    print('WARP configuration failed at step: '+step, file=sys.stderr)


def apply(panel, directory):
    step = 'template'
    try:
        original = read_template(panel)
        template, test_url = original['xraySetting'], original['outboundTestUrl']
        validate(template)
        private_json(directory/'original.json', dict(xraySetting=template, outboundTestUrl=test_url))
        step = 'registration'
        registration = json.loads(panel.request('panel/api/xray/warp/regMasque', method='POST', timeout=40)['obj'])
        if (any(not isinstance(registration.get(k), str) or not registration[k].strip()
                for k in ('privateKey', 'publicKey', 'endpoint')) or
                not isinstance(registration.get('address'), list) or not registration['address'] or
                any(not isinstance(a, str) or not a.strip() for a in registration['address'])):
            raise ValueError('Incomplete registration')
        candidate = merge(template, registration)
        step = 'outbound_test'
        result = panel.request('panel/api/xray/testOutbound',
                               dict(outbound=json.dumps(candidate['outbounds'][-1]), mode='real'),
                               method='POST', form=True, timeout=30)['obj']
        if not probe_ok(result):
            raise ValueError('Outbound probe failed')
        step = 'save'
        (directory/'save-attempted').touch(mode=0o600)
        save(panel, candidate, test_url)
        step = 'readback'
        current = read_template(panel)
        if current['xraySetting'] != candidate or current['outboundTestUrl'] != test_url:
            raise ValueError('Saved template mismatch')
        step = 'route_test'
        test_routes(panel)
        return 'applied_pending_health'
    except Exception:
        failed(step)
        return 'failed_needs_rollback' if (directory/'save-attempted').exists() else 'failed'


def rollback(panel, directory):
    step = 'rollback_save'
    try:
        original = json.loads((directory/'original.json').read_text())
        save(panel, original['xraySetting'], original['outboundTestUrl'])
        step = 'rollback_restart'
        panel.request('panel/api/server/restartXrayService', method='POST')
        step = 'rollback_readback'
        current = read_template(panel)
        if any(current[k] != original[k] for k in ('xraySetting', 'outboundTestUrl')):
            raise ValueError('Rollback mismatch')
        return 'restored_pending_health'
    except Exception:
        failed(step)
        return 'failed_unverified'


def budget_expired(signum, frame):
    raise TimeoutError('WARP helper budget exhausted')


def main():
    mode = 'apply'
    directory = None
    try:
        mode, helper, domain, path, target = sys.argv[1:]
        directory = Path(target)
        budget = 180 if mode == 'apply' else 60
        deadline = time.monotonic() + budget
        signal.signal(signal.SIGALRM, budget_expired)
        signal.alarm(budget)
        spec = importlib.util.spec_from_file_location('warp_panel_api', helper)
        api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
        username, password = sys.stdin.read().split('\0', 1)
        with tempfile.TemporaryDirectory(prefix='warp-session-', dir=directory) as session:
            os.chmod(session, 0o700)
            panel = api.Panel(f'https://{domain}/{path}/', username, password, session,
                              ['--resolve', f'{domain}:443:127.0.0.1'], deadline=deadline)
            status = apply(panel, directory) if mode == 'apply' else rollback(panel, directory)
    except Exception:
        failed('session')
        status = ('failed_needs_rollback' if directory is not None and (directory/'save-attempted').exists()
                  else 'failed') if mode == 'apply' else 'failed_unverified'
    finally:
        signal.alarm(0)
    print(status)
    return 0 if status in ('applied_pending_health', 'restored_pending_health') else 1


if __name__ == '__main__':
    sys.exit(main())

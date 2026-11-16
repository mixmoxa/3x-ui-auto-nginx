"""Manage the cascade client on the exit server through the native panel API."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import uuid


MANIFEST = Path('/etc/x-ui/auto-nginx-managed.json')
EMAIL = 'cascade'
FLOW = 'xtls-rprx-vision'


class Refusal(ValueError):
    """Only fixed, non-secret reason codes may cross the CLI boundary."""


def object_value(value):
    return json.loads(value) if isinstance(value, str) else value


def reality_inbound(panel, manifest):
    try:
        saved = json.loads(manifest.read_text())['inbound_roles']['reality']
        if type(saved) is not int:
            raise ValueError('manifest_invalid')
    except FileNotFoundError:
        saved = None
    except Exception:
        raise Refusal('manifest_invalid') from None
    rows = panel.request('panel/api/inbounds/list')['obj']
    matches = []
    for row in rows:
        if saved is not None and row['id'] != saved:
            continue
        stream = object_value(row.get('streamSettings') or {})
        if ((row.get('protocol'), row.get('listen'), row.get('port')) == ('vless', '127.0.0.1', 8443)
                and stream.get('network') == 'tcp' and stream.get('security') == 'reality'):
            matches.append(row)
    if saved is not None and len(matches) != 1:
        raise Refusal('manifest_invalid')
    if not matches:
        raise Refusal('no_reality')
    if len(matches) != 1:
        raise Refusal('ambiguous_reality')
    return matches[0]


def read_client(panel):
    rows = panel.request('panel/api/clients/list')['obj']
    if not any(row['email'] == EMAIL for row in rows):
        return None
    return panel.request('panel/api/clients/get/' + EMAIL)['obj']


def form_reason(record, iid, *, enabled=True):
    client = record['client']
    if enabled and client.get('enable') is not True:
        return 'disabled'
    if record['inboundIds'] != [iid]:
        return 'wrong_binding'
    if client.get('flow') != FLOW:
        return 'wrong_flow'
    return None


def validate_link(link, identity):
    try:
        parsed = urlsplit(link)
        if parsed.scheme != 'vless':
            raise Refusal('wrong_scheme')
        if uuid.UUID(parsed.username or '') != uuid.UUID(identity):
            raise Refusal('uuid_mismatch')
        if not parsed.hostname:
            raise Refusal('missing_host')
        if parsed.port == 8443:
            raise Refusal('internal_port_8443')
        if parsed.port != 443:
            raise Refusal('wrong_port')
        query = parse_qs(parsed.query, keep_blank_values=True)
        for key, expected in (('encryption', 'none'), ('security', 'reality'), ('type', 'tcp'), ('flow', FLOW)):
            if query.get(key) != [expected]:
                raise Refusal('invalid_' + key)
        for key in ('sni', 'pbk', 'sid', 'fp'):
            values = query.get(key, [])
            if len(values) != 1 or not values[0].strip():
                raise Refusal('invalid_' + key)
    except Refusal:
        raise
    except Exception:
        raise Refusal('malformed_link') from None
    return link


def select_link(links, identity):
    if len(links) != 1:
        candidates = []
        for link in links:
            try:
                query = parse_qs(urlsplit(link).query)
            except ValueError:
                continue
            if all(query.get(k) == [v] for k,v in (('security','reality'), ('type','tcp'), ('flow',FLOW))):
                candidates.append(link)
        if len(candidates) != 1:
            raise Refusal('link_count')
        links = candidates
    return validate_link(links[0], identity)


def delete_client(panel, identity):
    # Check identity immediately before deleting by email; never delete a replacement.
    record = read_client(panel)
    if record is None:
        return
    if record['client']['uuid'] != identity:
        raise Refusal('identity_changed')
    try:
        panel.request('panel/api/clients/del/' + EMAIL, method='POST')
    except Exception:
        pass
    if read_client(panel) is not None:
        raise Refusal('delete_unverified')


def exit_create(panel, reality):
    existing = panel.request('panel/api/clients/list')['obj']
    if any(client['email'] == EMAIL for client in existing):
        return dict(state='name_taken')
    identity = str(uuid.uuid4())
    try:
        panel.request('panel/api/clients/add', dict(client=dict(email=EMAIL, id=identity, flow=FLOW,
                      enable=True, totalGB=0, expiryTime=0), inboundIds=[reality['id']]), method='POST')
    except Exception:
        # A rejected or lost response may still have committed the client.
        pass
    state, reason = 'failed', 'readback_failed'
    try:
        record = read_client(panel)
        if record is None:
            return dict(state='failed', reason='client_absent')
        if record['client']['uuid'] != identity:
            return dict(state='failed', reason='identity_changed')
        reason = form_reason(record, reality['id'])
        if reason is None:
            links = panel.request('panel/api/clients/links/' + EMAIL)['obj']
            try:
                link = select_link(links, identity)
            except Refusal as error:
                state, reason = 'link_invalid', str(error)
            else:
                return dict(state='created', link=link)
    except Exception:
        reason = 'panel_request_failed'
    try:
        delete_client(panel, identity)
    except Refusal as error:
        if str(error) == 'identity_changed':
            return dict(state='failed', reason='identity_changed')
        return dict(state='failed_cleanup', reason='cleanup_unverified', client_may_remain=True)
    except Exception:
        return dict(state='failed_cleanup', reason='cleanup_unverified', client_may_remain=True)
    return dict(state=state, reason=reason)


def execute(mode, panel, manifest=None):
    manifest = MANIFEST if manifest is None else Path(manifest)
    try:
        reality = reality_inbound(panel, manifest)
        if mode == 'exit-create':
            return exit_create(panel, reality)
        record = read_client(panel)
        if record is None:
            return dict(state='absent')
        if mode == 'exit-status':
            reason = form_reason(record, reality['id'])
            return dict(state='inconsistent', reason=reason) if reason else dict(state='ready')
        if mode == 'exit-remove':
            if form_reason(record, reality['id'], enabled=False):
                return dict(state='not_ours')
            delete_client(panel, record['client']['uuid'])
            return dict(state='removed')
        raise Refusal('invalid_command')
    except Refusal as error:
        reason = str(error)
        if reason in ('no_reality', 'ambiguous_reality'):
            return dict(state=reason)
        return dict(state='panel_error' if mode == 'exit-status' else 'failed', reason=reason)
    except Exception:
        return dict(state='panel_error' if mode == 'exit-status' else 'failed', reason='panel_request_failed')


def main():
    mode = None
    try:
        mode, helper, domain, path, target = sys.argv[1:]
        if mode not in ('exit-create', 'exit-status', 'exit-remove'):
            raise Refusal('invalid_command')
        spec = importlib.util.spec_from_file_location('cascade_panel_api', helper)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        username, password = sys.stdin.read().split('\0', 1)
        with tempfile.TemporaryDirectory(prefix='cascade-session-', dir=target) as session:
            os.chmod(session, 0o700)
            panel = api.Panel(f'https://{domain}/{path}/', username, password, session,
                              ['--resolve', f'{domain}:443:127.0.0.1'])
            result = execute(mode, panel)
    except Exception:
        result = dict(state='panel_error' if mode == 'exit-status' else 'failed', reason='session_failed')
    print(json.dumps(result))
    return 0 if result['state'] in ('created', 'ready', 'removed', 'absent') else 1


if __name__ == '__main__':
    sys.exit(main())

# 3X-UI AUTO NGINX - https://github.com/xPROMSx/3x-ui-auto-nginx
# Copyright (C) 2026 xPROMSx contributors
# SPDX-License-Identifier: GPL-3.0-only
# Additional attribution terms (GPL-3.0 section 7) apply to material added by xPROMSx contributors: see docs/NOTICE.md

"""Manage cascade exit clients and entry routing through the native panel API."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit
import uuid


MANIFEST = Path('/etc/x-ui/auto-nginx-managed.json')
EMAIL = 'cascade'
FLOW = 'xtls-rprx-vision'
ENTRY_TAG = 'cascade-exit'
ENTRY_COMMENTS = ('CASCADE - RU', 'CASCADE - RU2', 'CASCADE - EXIT')
WARP_COMMENTS = ('WARP - RU', 'WARP - RU2', 'WARP - RU3')
HEALTH_WINDOW = 15
HEALTH_INTERVAL = 1
CONDITIONS = ('domain', 'ip', 'port', 'sourcePort', 'source', 'user', 'inboundTag',
              'protocol', 'attrs', 'localIP', 'localPort', 'vlessRoute', 'process', 'localOS')
# Xray's webhook is an action; the other fields are targets or panel metadata.
RULE_FIELDS = {*CONDITIONS, 'domains', 'sourceIP', 'network', 'webhook', 'type',
               'outboundTag', 'balancerTag', 'ruleTag', 'comment', 'enabled'}


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


def entry_outbound(link):
    try:
        parsed = urlsplit(link)
        if parsed.scheme != 'vless':
            raise Refusal('wrong_scheme')
        try:
            identity = str(uuid.UUID(parsed.username or ''))
        except ValueError:
            raise Refusal('invalid_uuid') from None
        if not parsed.hostname:
            raise Refusal('missing_host')
        try:
            port = parsed.port
        except ValueError:
            raise Refusal('invalid_port') from None
        if port is None or not 1 <= port <= 65535:
            raise Refusal('invalid_port')
        query = parse_qs(parsed.query, keep_blank_values=True)
        for key, expected in (('encryption', 'none'), ('security', 'reality'), ('type', 'tcp'), ('flow', FLOW)):
            if query.get(key) != [expected]:
                raise Refusal('invalid_' + key)
        for key in ('sni', 'pbk', 'sid', 'fp'):
            values = query.get(key, [])
            if len(values) != 1 or not values[0].strip():
                raise Refusal('invalid_' + key)
        reality = dict(serverName=query['sni'][0], fingerprint=query['fp'][0],
                       publicKey=query['pbk'][0], shortId=query['sid'][0])
        if 'spx' in query:
            reality['spiderX'] = query['spx'][0]
        return dict(tag=ENTRY_TAG, protocol='vless',
                    settings=dict(address=parsed.hostname, port=port, id=identity, flow=FLOW, encryption='none'),
                    streamSettings=dict(network='tcp', security='reality', realitySettings=reality))
    except Refusal:
        raise
    except Exception:
        raise Refusal('malformed_link') from None


def entry_rules():
    return [dict(type='field', outboundTag=tag, comment=comment, enabled=True, **criterion)
            for tag, comment, criterion in zip(('direct', 'direct', ENTRY_TAG), ENTRY_COMMENTS,
                (dict(domain=['geosite:category-ru']), dict(ip=['geoip:ru']), dict(network='tcp,udp')))]


def read_entry_template(panel):
    response = object_value(panel.request('panel/api/xray/', method='POST')['obj'])
    template = object_value(response['xraySetting'])
    if not isinstance(template['outbounds'], list) or not isinstance(template['routing']['rules'], list):
        raise Refusal('template_lists_invalid')
    return template, response['outboundTestUrl']


def save_entry_template(panel, template, test_url):
    wire = copy.deepcopy(template)
    wire['outbounds'] = normalized(wire['outbounds'])
    panel.request('panel/api/xray/update', dict(xraySetting=json.dumps(wire), outboundTestUrl=test_url),
                  method='POST', form=True)


def owned_rule(rule):
    return isinstance(rule, dict) and rule.get('comment') in ENTRY_COMMENTS


def api_rule(rule):
    if not isinstance(rule, dict):
        return False
    tags = rule.get('inboundTag')
    return rule.get('outboundTag') == 'api' and isinstance(tags, list) and 'api' in tags


def entry_state(template):
    outbounds, rules = template['outbounds'], template['routing']['rules']
    present = any(o.get('tag') == ENTRY_TAG for o in outbounds)
    comments = [r['comment'] for r in rules if owned_rule(r)]
    if not present and not comments:
        return dict(state='absent')
    if not present:
        return dict(state='inconsistent', reason='missing_outbound')
    if any(c not in comments for c in ENTRY_COMMENTS):
        return dict(state='inconsistent', reason='missing_rules')
    if comments != list(ENTRY_COMMENTS):
        return dict(state='inconsistent', reason='wrong_order')
    return dict(state='active')


def warp_present(template):
    details = warp_details(template)
    return details['warp_outbound'] or bool(details['warp_rules'])


def warp_details(template):
    return dict(warp_outbound=any(o.get('tag') == 'warp-masque' for o in template['outbounds']),
                warp_rules=[c for c in WARP_COMMENTS if any(isinstance(r, dict) and r.get('comment') == c
                            for r in template['routing']['rules'])])


def custom_rules(template):
    # 3x-ui v3.11.0 internal/web/service/config.json. No other installer
    # rules exist apart from WARP (a separate refusal) and cascade itself.
    defaults = (dict(inboundTag=['api'], outboundTag='api'),
                dict(ip=['geoip:private'], outboundTag='blocked'),
                dict(protocol=['bittorrent'], outboundTag='blocked'))
    result = []
    for index, rule in enumerate(template['routing']['rules']):
        if owned_rule(rule):
            break
        if not isinstance(rule, dict):
            result.append(index + 1)
            continue
        if rule.get('enabled') is False:
            continue
        meaningful = {k: v for k, v in rule.items() if k not in ('comment', 'enabled', 'type', 'ruleTag')}
        if meaningful not in defaults:
            result.append(index + 1)
    return result


def read_xray(panel):
    value = panel.request('panel/api/server/status')['obj']['xray']
    state = value.get('state')
    return (state if state in ('running', 'stop', 'error') else 'unknown', bool(value.get('errorMsg')))


def wait_entry_health(panel, deadline, *, routes=False):
    previous_deadline = getattr(panel, 'deadline', None)
    panel.deadline = min(previous_deadline, deadline) if previous_deadline is not None else deadline
    healthy = False
    try:
        while time.monotonic() < deadline:
            try:
                state, error = read_xray(panel)
                healthy = state == 'running' and not error
            except Exception:
                healthy = False
            if healthy:
                try:
                    if routes:
                        for domain, tag in (('yandex.ru', 'direct'), ('example.com', ENTRY_TAG)):
                            result = panel.request('panel/api/xray/routeTest',
                                dict(network='tcp', port=443, domain=domain), method='POST', form=True, timeout=10)['obj']
                            if not isinstance(result, dict) or result.get('matched') is not True or result.get('outboundTag') != tag:
                                raise Refusal('route_test_failed')
                    return None
                except Exception:
                    pass
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(HEALTH_INTERVAL, remaining))
        return 'route_test_failed' if healthy else 'xray_unhealthy'
    finally:
        panel.deadline = previous_deadline


def interception(rules):
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            return dict(state='failed', reason='invalid_rule', rule_index=index)
        if api_rule(rule) or owned_rule(rule) or rule.get('enabled') is False:
            continue
        network = rule.get('network')
        if isinstance(network, str):
            networks = network.lower().split(',') if network else []
        elif network is None:
            networks = []
        elif isinstance(network, list) and all(isinstance(n, str) for n in network):
            networks = [n.lower() for n in network]
        else:
            return dict(state='failed', reason='invalid_network', rule_index=index)
        # Unknown fields cannot be classified as conditions: the owner's policy
        # treats such a rule as non-universal, without changing or rejecting it.
        if rule.keys() - RULE_FIELDS:
            continue
        conditions = {k: rule.get(k) for k in CONDITIONS}
        conditions['domain'] = rule.get('domains', conditions['domain'])
        if rule.get('sourceIP') is not None:
            conditions['source'] = rule['sourceIP']
        if not any(conditions.values()) and (not networks or 'tcp' in networks):
            return dict(state='intercepted', rule_index=index)
    return None


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(object_value(v) if k in ('settings', 'streamSettings', 'realitySettings') else v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def assigned_fields_match(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and assigned_fields_match(actual[k], v)
                                              for k, v in expected.items())
    return actual == expected


def foreign_lists(template):
    return normalized([o for o in template['outbounds'] if o.get('tag') != ENTRY_TAG]), normalized(
        [r for r in template['routing']['rules'] if not owned_rule(r) and not api_rule(r)])


def entry_readback_matches(current, original, outbound):
    ours = [o for o in current['outbounds'] if o.get('tag') == ENTRY_TAG]
    rules = current['routing']['rules']
    expected_rules = entry_rules()
    # The agreed readback contract covers these lists and the fields we set;
    # other template fields and response metadata are deliberately not compared.
    return (len(ours) == 1 and assigned_fields_match(normalized(ours[0]), normalized(outbound)) and
            [r.get('comment') for r in rules if owned_rule(r)] == list(ENTRY_COMMENTS) and
            len(rules) >= 3 and all(assigned_fields_match(normalized(a), normalized(b))
                                   for a, b in zip(rules[-3:], expected_rules)) and
            foreign_lists(current) == foreign_lists(original))


def foreign_references(template):
    rules = [i + 1 for i, r in enumerate(template['routing']['rules'])
             if isinstance(r, dict) and not owned_rule(r) and r.get('outboundTag') == ENTRY_TAG]
    found = []
    balancers = template['routing'].get('balancers')
    for index, balancer in enumerate(balancers if isinstance(balancers, list) else []):
        if not isinstance(balancer, dict):
            continue
        selectors = balancer.get('selector', [])
        if isinstance(selectors, str):
            selectors = selectors.split(',')  # Xray conf.StringList accepts both wire shapes.
        if not isinstance(selectors, list):
            selectors = []
        if balancer.get('fallbackTag') == ENTRY_TAG or any(isinstance(s, str) and ENTRY_TAG.startswith(s) for s in selectors):
            found.append(index + 1)
    return dict(foreign_rules=rules, foreign_balancers=found)


def foreign_reference(template):
    return any(foreign_references(template).values())


def remove_entry_elements(template, *, keep_outbound=False):
    result = copy.deepcopy(template)
    result['routing']['rules'] = [r for r in result['routing']['rules'] if not owned_rule(r)]
    if not keep_outbound:
        result['outbounds'] = [o for o in result['outbounds'] if o.get('tag') != ENTRY_TAG]
    return result


def rollback_entry(panel, reason):
    result = dict(state='failed_rollback', reason=reason, config_may_contain_changes=True)
    try:
        current, test_url = read_entry_template(panel)
        references = foreign_references(current)
        keep = any(references.values())
        candidate = remove_entry_elements(current, keep_outbound=keep)
        if candidate != current:
            try:
                save_entry_template(panel, candidate, test_url)
            except Exception:
                pass  # A lost response may still have committed; always read back.
        current, _ = read_entry_template(panel)
        if keep:
            result.update(reason='foreign_reference', **foreign_references(current))
        elif entry_state(current)['state'] == 'absent':
            result = dict(state='failed', reason=reason)
    except Exception:
        pass
    if wait_entry_health(panel, time.monotonic() + HEALTH_WINDOW) is not None:
        result.update(state='failed_rollback', config_may_contain_changes=True, xray_running=False)
    return result


def connect_entry(panel, template, test_url, outbound):
    if entry_state(template)['state'] != 'absent':
        return dict(state='already_connected')
    if warp_present(template):
        return dict(state='warp_active', **warp_details(template))
    refusal = interception(template['routing']['rules'])
    if refusal:
        return refusal
    if not any(o.get('tag') == 'direct' for o in template['outbounds']):
        return dict(state='failed', reason='missing_direct')
    if read_xray(panel)[0] != 'running':
        return dict(state='failed', reason='xray_not_running')
    try:
        probe = panel.request('panel/api/xray/testOutbound', dict(outbound=json.dumps(outbound), mode='real'),
                              method='POST', form=True, timeout=30)['obj']
        if not (isinstance(probe, dict) and probe.get('success') is True and probe.get('tag') == ENTRY_TAG and
                probe.get('mode') == 'real' and type(probe.get('delay')) is int and probe['delay'] > 0 and
                type(probe.get('httpStatus')) is int and 200 <= probe['httpStatus'] < 300 and not probe.get('error')):
            raise Refusal('outbound_test_failed')
    except Exception:
        return dict(state='test_failed', reason='outbound_test_failed')
    candidate = copy.deepcopy(template)
    candidate['outbounds'].append(outbound)
    candidate['routing']['rules'].extend(entry_rules())
    reason = 'save_failed'
    try:
        save_entry_template(panel, candidate, test_url)
        deadline = time.monotonic() + HEALTH_WINDOW
        reason = 'readback_failed'
        current, _ = read_entry_template(panel)
        reason = 'readback_mismatch'
        if not entry_readback_matches(current, template, outbound):
            raise Refusal(reason)
        reason = wait_entry_health(panel, deadline, routes=True)
        if reason:
            raise Refusal(reason)
    except Exception:
        return rollback_entry(panel, reason)
    return dict(state='connected', custom_rules=custom_rules(template))


def disable_entry(panel, template, test_url):
    if entry_state(template)['state'] == 'absent':
        return dict(state='absent')
    if foreign_reference(template):
        return dict(state='foreign_reference', **foreign_references(template))
    save_failed = False
    try:
        save_entry_template(panel, remove_entry_elements(template), test_url)
    except Exception:
        save_failed = True
    try:
        current, _ = read_entry_template(panel)
        actual = entry_state(current)
    except Exception:
        return dict(state='failed', reason='save_failed_actual_unknown' if save_failed else 'readback_failed')
    if save_failed:
        return dict(state='failed', reason='save_failed_actual_' + actual.get('reason', actual['state']))
    if actual['state'] == 'absent':
        return dict(state='removed', xray_running=wait_entry_health(panel, time.monotonic() + HEALTH_WINDOW) is None)
    return dict(state='failed', reason='remove_unverified')


def execute_entry(mode, panel, link=None):
    if mode == 'entry-connect':
        try:
            outbound = entry_outbound(link)
        except Refusal as error:
            return dict(state='link_invalid', reason=str(error))
    try:
        template, test_url = read_entry_template(panel)
        if mode == 'entry-status':
            try:
                xray = read_xray(panel)[0]
            except Exception:
                xray = 'unknown'
            return dict(**entry_state(template), warp=warp_present(template), **warp_details(template),
                        xray=xray, custom_rules=custom_rules(template))
        if mode == 'entry-disable':
            return disable_entry(panel, template, test_url)
        return connect_entry(panel, template, test_url, outbound)
    except Exception:
        return dict(state='failed' if mode == 'entry-connect' else 'panel_error', reason='panel_request_failed')


def main():
    mode = None
    try:
        mode, helper, domain, path, target = sys.argv[1:]
        if mode not in ('exit-create', 'exit-status', 'exit-remove', 'entry-connect', 'entry-status', 'entry-disable'):
            raise Refusal('invalid_command')
        spec = importlib.util.spec_from_file_location('cascade_panel_api', helper)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        if mode == 'entry-connect':
            username, password, link = sys.stdin.read().split('\0', 2)
        else:
            username, password = sys.stdin.read().split('\0', 1)
        with tempfile.TemporaryDirectory(prefix='cascade-session-', dir=target) as session:
            os.chmod(session, 0o700)
            panel = api.Panel(f'https://{domain}/{path}/', username, password, session,
                              ['--resolve', f'{domain}:443:127.0.0.1'])
            if mode.startswith('entry-'):
                result = execute_entry(mode, panel, link if mode == 'entry-connect' else None)
            else:
                result = execute(mode, panel)
    except Exception:
        result = dict(state='panel_error' if mode in ('exit-status', 'entry-status', 'entry-disable') else 'failed', reason='session_failed')
    print(json.dumps(result))
    return 0 if result['state'] in ('created', 'ready', 'removed', 'absent', 'connected', 'active') else 1


if __name__ == '__main__':
    sys.exit(main())

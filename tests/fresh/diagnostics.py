"""Allowlisted public diagnostics; never return raw logs, names, URLs or packets."""
import ast
import json
import re
import struct
import time

VISION_STAGES = {
    'rendering ACME configuration':'rendering_acme',
    'activating ACME configuration':'activating_acme',
    'validating ACME nginx configuration':'validating_nginx',
    'reloading ACME nginx':'reloading_nginx',
    'issuing/checking Vision certificate':'certificate',
    'installing Vision renewal hook':'renewal_hook',
    'configuring Vision inbound/nginx/HTTPS':'configuring_inbound',
}


def vision_failure(log):
    matches = re.findall(r'Vision failed during ([^\n]+?) \(exit ([0-9]{1,3})\): rollback=([^\s]+)', log)
    if not matches: return None
    stage, code, rollback = matches[-1]
    return {'stage':VISION_STAGES.get(stage, 'unknown'), 'exit_code':int(code),
            'rollback':rollback if rollback in ('failed_rolled_back','failed_unverified') else 'unknown'}


def domain_failure(log, source):
    matches=re.findall(r'Change Domains failed during ([^\r\n:]+): ([^\r\n]+)',log)
    if not matches:return None
    stage,reason=matches[-1]
    stages=('preflight','validating installed layout','recognizing managed configuration','checking target domains',
            'planning scoped changes','checking original stack','checking original nginx','checking original certificates','checking stack after Backup',
            'creating full Backup v3','preparing certificates','validating complete candidate nginx',
            'switching','verifying new stack','recovering prepared operation','recovering switching operation','recovering committed operation')
    # Only exact messages already public in the checked-out helper may leave
    # the private guest; arbitrary command/API bodies never become diagnostics.
    public={node.value for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
    formats=(r'Managed (?:hook|lineage|health|adguard|amneziawg|render-hook) check failed \(exit -?[0-9]{1,3}\)\.',
             r'command failed \(exit -?[0-9]{1,3}\)',
             r'Required local component is missing/inaccessible \(errno (?:[0-9]{1,3}|None)\)\.')
    safe=reason in public or any(re.fullmatch(pattern,reason) for pattern in formats)
    return {'stage':stage.replace(' ','_') if stage in stages else 'unknown','reason':reason if safe else 'unknown'}


def dns_metrics(data, ident):
    metrics = {'response_length':len(data), 'rcode':None, 'transaction_id_match':data[:2] == ident,
               'answer_records':0, 'expected_a':False, 'parse_valid':False}
    try:
        if len(data) < 12: return metrics
        _, flags, qd, an, ns, ar = struct.unpack('!6H', data[:12])
        metrics.update(rcode=flags & 15, answer_records=an)
        def name(offset):
            seen = set()
            end = None
            while True:
                if offset in seen or offset >= len(data): raise ValueError('Invalid DNS name')
                seen.add(offset)
                size = data[offset]
                if size & 0xc0 == 0xc0:
                    if offset+1 >= len(data): raise ValueError('Truncated DNS pointer')
                    pointer = ((size & 63) << 8) | data[offset+1]
                    if pointer >= offset: raise ValueError('Invalid DNS pointer')
                    if end is None: end = offset+2
                    offset = pointer
                elif size & 0xc0 or size > 63: raise ValueError('Invalid label')
                elif size == 0: return end if end is not None else offset+1
                else:
                    offset += size+1
        offset = 12
        for _ in range(qd): offset = name(offset)+4
        for index in range(an+ns+ar):
            offset = name(offset)
            kind, cls, _, length = struct.unpack('!HHIH', data[offset:offset+10])
            offset += 10
            if offset+length > len(data): raise ValueError('Truncated record')
            if index < an and kind == 1 and cls == 1 and length == 4 and data[offset:offset+4] == bytes([203,0,113,7]):
                metrics['expected_a'] = True
            offset += length
        metrics['parse_valid'] = offset == len(data) and bool(flags & 0x8000) and not bool(flags & 0x0200)
    except (ValueError, IndexError, struct.error): pass
    return metrics


def validate_dns(data, ident, probe, elapsed):
    if probe not in ('native_udp','doh_get','doh_post'): raise ValueError('Unknown DNS probe')
    metrics = {'probe':probe, **dns_metrics(data, ident), 'elapsed_seconds':round(elapsed, 3)}
    if not (metrics['parse_valid'] and metrics['transaction_id_match'] and metrics['rcode'] == 0
            and metrics['answer_records'] >= 1 and metrics['expected_a']):
        raise AssertionError(json.dumps(metrics, sort_keys=True))
    return metrics


def probe_dns(probe, ident, fetch, publish):
    if probe not in ('native_udp','doh_get','doh_post'): raise ValueError('Unknown DNS probe')
    started = time.monotonic()
    try:
        data = fetch()
    except Exception:
        metrics = {'probe':probe, **dns_metrics(b'', ident),
                   'elapsed_seconds':round(time.monotonic()-started, 3), 'transport_error':True}
        publish(metrics)
        raise AssertionError(json.dumps(metrics, sort_keys=True)) from None
    try:
        metrics = validate_dns(data, ident, probe, time.monotonic()-started)
    except AssertionError as error:
        publish(json.loads(str(error)))
        raise
    publish(metrics)
    return metrics

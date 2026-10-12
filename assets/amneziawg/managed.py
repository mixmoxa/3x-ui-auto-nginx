"""Create an empty AWG inbound through official 3x-ui, never generate VPN keys locally."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def validate(inbound, domain, port=8443):
    if (inbound.get('protocol'), inbound.get('port'), inbound.get('listen'), inbound.get('enable'),
        inbound.get('shareAddrStrategy'), inbound.get('shareAddr')) != ('amneziawg', port, '0.0.0.0', True, 'custom', domain):
        raise ValueError('Unexpected AmneziaWG inbound topology/share address')
    settings = inbound['settings']
    if isinstance(settings, str):
        settings = json.loads(settings)
    if settings.get('clients') != []:
        raise ValueError('Installer must not create AmneziaWG clients')
    server = settings['server']
    for key in ('privateKey', 'publicKey', 'headerProtectionKey'):
        if len(base64.b64decode(server[key], validate=True)) != 32:
            raise ValueError('Invalid AmneziaWG key')
    if any(server.get(k) for k in ('ipv6Enabled', 'routeThroughXray', 'externalInterface', 'ipv6ExternalInterface')):
        raise ValueError('Unexpected optional AmneziaWG feature')
    if not (3 <= server['jc'] <= 6 and 40 <= server['jmin'] <= 89 and server['jmin'] < server['jmax'] <= 339):
        raise ValueError('Unexpected AmneziaWG junk parameters')
    if not (15 <= server['s1'] <= 150 and 15 <= server['s2'] <= 150 and server['s1']+56 != server['s2']
            and 12 <= server['s3'] <= 55 and 12 <= server['s4'] <= 27):
        raise ValueError('Unexpected AmneziaWG padding')
    ranges = []
    for name in ('h1','h2','h3','h4'):
        parts = list(map(int,server[name].split('-')))
        lo,hi = (parts[0],parts[-1])
        if not (4 < lo <= hi <= 2147483647) or any(lo <= b and a <= hi for a,b in ranges):
            raise ValueError('Invalid AmneziaWG header ranges')
        ranges.append((lo,hi))
    if not server.get('i1') or not server.get('contentPaddingAddition'):
        raise ValueError('Missing AmneziaWG 3.1 parameters')
    return inbound


class Panel:
    def __init__(self, base, username, password, directory, options=()):
        self.base = base
        self.directory = Path(directory)
        self.options = list(options)
        self.cookie = self.directory/'cookies'
        self.cookie.touch(mode=0o600)
        self.headers = self.directory/'csrf-header'
        self.headers.touch(mode=0o600)
        self.token = None
        self.token = self.request('csrf-token')['obj']
        self.request('login', {'username':username,'password':password})
        self.token = self.request('csrf-token')['obj']

    def request(self, path, data=None):
        argv = ['curl','-q','--fail','--silent','--show-error','--noproxy','*',
                '--connect-timeout','5','--max-time','20',*self.options,
                '--cookie',str(self.cookie),'--cookie-jar',str(self.cookie)]
        if self.token:
            # Session secrets stay in the private temporary directory, never argv.
            self.headers.write_text('X-CSRF-Token: '+self.token+'\n')
            argv += ['--header','@'+str(self.headers)]
        if data is not None:
            argv += ['--header','Content-Type: application/json','--data-binary','@-']
        argv.append(self.base+path)
        result = subprocess.run(argv,input=json.dumps(data).encode() if data is not None else None,
                                capture_output=True,timeout=25)
        if result.returncode:
            raise ValueError('AmneziaWG panel request failed: '+path)
        value = json.loads(result.stdout)
        if value.get('success') is not True:
            raise ValueError('AmneziaWG panel rejected request: '+path)
        return value

    def create(self, domain, port=8443):
        # {} invokes defaultAmneziaWGServer / GenerateObfuscation31 in official 3x-ui.
        body = {'enable':True,'listen':'0.0.0.0','port':port,'protocol':'amneziawg',
                'remark':'AmneziaWG','tag':f'inbound-{port}-udp', 'shareAddrStrategy':'custom',
                'shareAddr':domain,'settings': {},'streamSettings':{},'sniffing':{}}
        inbound = self.request('panel/api/inbounds/add',body)['obj']
        try:
            validate(inbound,domain,port)
        except Exception:
            self.request('panel/api/inbounds/del/'+str(inbound['id']), {})
            raise
        return inbound


def configure(panel, domain):
    inbound = panel.create(domain)
    try:
        subprocess.run(['ufw','allow','8443/udp'],capture_output=True,timeout=20,check=True)
    except Exception:
        # A failed allow does not establish ownership of a firewall rule. Never
        # compensate with delete: it can remove an equivalent administrator rule.
        panel.request('panel/api/inbounds/del/'+str(inbound['id']), {})
        raise ValueError('Cannot configure AmneziaWG firewall; inbound removed')
    return inbound


def main():
    domain, path, username = sys.argv[1:]
    password = sys.stdin.read()
    # Cookie state and credentials never enter argv or persistent storage.
    with tempfile.TemporaryDirectory(prefix='xui-awg-') as directory:
        os.chmod(directory,0o700)
        panel = Panel(f'https://{domain}/{path}/',username,password,directory,
                      ['--resolve',f'{domain}:443:127.0.0.1'])
        inbound = configure(panel, domain)
        print(inbound['id'])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never print API bodies, keys, obfuscation parameters or credentials.
        print('AmneziaWG configuration failed. Check panel/UFW health; no success was reported.',file=sys.stderr)
        sys.exit(1)

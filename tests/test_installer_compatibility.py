"""Targeted supported-VPS regressions; all paths/services stay private fixtures."""
import errno
import http.client
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from test_personal_xhttp import SOURCE, function
from test_integrated_features import helper


def shell(names, body, env=None, stubs='', timeout=15):
    source='\n'.join(function(n) for n in names if n+'() {' in SOURCE)
    return subprocess.run(['bash','-u','-c','msg_err() { echo "$*" >&2; };\n'+source+'\n'+stubs+'\n'+body],
                          env={**os.environ,**(env or {})},capture_output=True,text=True,timeout=timeout)


def root_stat(path, *args, **kwargs):
    fields=list(REAL_STAT(path,*args,**kwargs));fields[4]=fields[5]=0
    return os.stat_result(fields)


REAL_STAT=Path.stat


def nginx_ipv4_acme(simulate=False):
    """Production renderers plus real nginx; reused by the existing second VM boot."""
    from certificate_fixtures import relocate
    from test_personal_xhttp import FIXTURE
    nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
    if not nginx: raise AssertionError('Real nginx required')
    with tempfile.TemporaryDirectory(prefix='ipv4-acme-') as directory:
        root=Path(directory);root.chmod(0o755)
        (root/'etc/nginx').mkdir(parents=True)
        (root/'etc/nginx/nginx.conf').write_text('events {}\nhttp {}\n')
        stubs="""nginx() { [[ \"${1:-}\" != -v ]] || echo 'nginx version: nginx/1.24.0' >&2; return 0; }
systemctl() { :; }
install() { local -a args=(); while (($#)); do case \"$1\" in -o|-g) shift 2;; *) args+=(\"$1\"); shift;; esac; done; command install \"${args[@]}\"; }
"""
        if simulate: stubs+='ipv6_available() { return 1; };\n'
        def complete_function(name):
            # These nginx functions contain column-zero braces inside heredocs.
            text=SOURCE[SOURCE.index(name+'() {'):]
            headers=list(re.finditer(r'^\w+\(\)\s*\{',text,re.M))
            return text[:headers[1].start()] if len(headers)>1 else text
        source='\n'.join(relocate(complete_function(n),root) for n in ('ipv6_available','prepare_acme_webroot','setup_acme_http','configure_nginx'))
        result=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\nsetup_acme_http && configure_nginx'],
            env={**os.environ,**FIXTURE},capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr
        main=(root/'etc/nginx/sites-available/80.conf').read_text()
        stream=(root/'etc/nginx/stream-enabled/stream.conf').read_text()
        assert 'listen 80;' in main and 'listen     443;' in stream
        assert '[::]' not in main+stream
        vision=helper('vision')
        config=vision.acme_config('vision.example',ipv6=False) if simulate else vision.acme_config('vision.example')
        assert '[::]' not in config
        with socket.socket() as listener, socket.socket() as stream_listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            stream_listener.bind(('127.0.0.1',0));stream_port=stream_listener.getsockname()[1]
        stream=stream.replace('listen     443;',f'listen 127.0.0.1:{stream_port};')
        main=main.replace('listen 80;',f'listen 127.0.0.1:{port};')
        config=config.replace('listen 80;',f'listen 127.0.0.1:{port};').replace('/var/www/acme',str(root/'var/www/acme'))
        token=root/'var/www/acme/.well-known/acme-challenge/check';token.write_bytes(b'IPv4 ACME OK')
        temporary='\n'.join(f'{kind}_temp_path {root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        conf=root/'test.conf';conf.write_text(f'load_module /usr/lib/nginx/modules/ngx_stream_module.so; pid {root}/pid; error_log stderr; events {{}} stream {{{stream}}} http {{ access_log off; {temporary}\n{main}\n{config}\n}}')
        command=[nginx,'-e','stderr','-p',str(root)+'/', '-c',str(conf)]
        subprocess.run([*command,'-t'],check=True,capture_output=True,timeout=10)
        with (root/'private.log').open('wb') as log:
            child=subprocess.Popen([*command,'-g','daemon off;'],stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+5
                while True:
                    assert child.poll() is None,'nginx exited'
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                    except OSError:
                        if time.monotonic()>=deadline:raise AssertionError('nginx readiness deadline')
                        time.sleep(.02)
                for domain in ('deploy.example','vision.example'):
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                    try:
                        connection.request('GET','/.well-known/acme-challenge/check',headers={'Host':domain})
                        response=connection.getresponse()
                        assert response.status==200 and response.read()==b'IPv4 ACME OK'
                    finally:connection.close()
            finally:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)


class InstallerCompatibility(unittest.TestCase):
    def test_domain_syntax_canonicalization_and_precleanup_failure(self):
        names=('valid_hostname','validate_domains')
        for panel,reality in (('Panel.Example.COM','Reality.Example.COM'),
                              ('xn--e1afmkfd.xn--p1ai','cover.example'),
                              ('.'.join(['a'*63]*3+['a'*61]),'cover.example'),
                              ('203-0-113-7.sslip.io','reality.203-0-113-7.sslip.io')):
            with self.subTest(panel=panel,reality=reality):
                result=shell(names,'validate_domains || exit 1; printf "%s|%s" "$domain" "$reality_domain"',
                             {'domain':panel,'reality_domain':reality})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,panel.lower()+'|'+reality.lower())
        bad=('','https://panel.example','panel.example/path','panel.example:443','pan el.example',
             ' panel.example','panel.example ','panel.example\nother.example','panel.\texample','bad_name.example','-bad.example','bad-.example',
             'a..example','panel.example.','панель.example','a'*64+'.example',
             '.'.join(['a'*63]*4))
        stubs='\n'.join(n+'() { :; };' for n in re.findall(r'^(\w+)\(\)\s*\{',SOURCE,re.M)
                        if n not in ('main','validate_domains','valid_hostname','msg_err'))
        stubs+='\nclean_previous_install() { echo CLEANUP_REACHED; return 1; };\n'
        for panel,reality in [(b,'reality.example') for b in bad]+[('Panel.Example','panel.example')]:
            with self.subTest(panel=panel):
                result=shell((*names,'main'),'main',{'domain':panel,'reality_domain':reality,
                    'INSTALL_VISION':'n','CREATE_CLIENT':'n','INSTALL_SECURITY':'n','INSTALL_AWG':'n'},stubs)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',result.stdout)
                self.assertRegex(result.stderr,'(?i)domain|hostname')

    def test_supported_os_release_quoted_unquoted_and_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release=root/'os-release';marker=root/'executed'
            source=function('check_os').replace('/etc/os-release',str(release))
            for distro,version in (('ubuntu','24.04'),('ubuntu','26.04'),('debian','13')):
                for quote in ('','"',"'"):
                    with self.subTest(distro=distro,version=version,quote=quote):
                        release.write_text(f'ID={quote}{distro}{quote}\nVERSION_ID={quote}{version}{quote}')
                        r=subprocess.run(['bash','-u','-c','msg_err() { :; };\n'+source+'\ncheck_os; echo CLEANUP_REACHED'],capture_output=True,text=True)
                        self.assertEqual(r.returncode,0,r.stderr)
                        self.assertIn('CLEANUP_REACHED',r.stdout)
            for data in ('ID=ubuntu\nVERSION_ID=22.04\n','VERSION_ID=13\n',
                         'ID=debian-extra\nVERSION_ID=13\n','ID="debian\nVERSION_ID=13\n',
                         'ID=debian\nVERSION_ID="13\n',f'ID=$(touch {marker})\nVERSION_ID=13\n'):
                release.write_text(data)
                r=subprocess.run(['bash','-u','-c','msg_err() { :; };\n'+source+'\ncheck_os; echo CLEANUP_REACHED'],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',r.stdout)
                self.assertFalse(marker.exists())

    def test_tcp_port_allocation_repeats_occupied_ports_no_nc_and_late_vision(self):
        main=function('main')
        self.assertLess(main.index('preflight_panel_release'),main.index('make_port sub_port'))
        self.assertLess(main.index('make_port sub_port'),main.index('clean_previous_install'))
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            root=Path(directory);occupied.bind(('127.0.0.1',0));busy=occupied.getsockname()[1]
            # Deliberately bind without listen: a TCP connect probe would miss it.
            result=shell(('check_free',),'check_free "$BUSY"',{'BUSY':str(busy)},'nc() { return 127; };')
            self.assertEqual(result.returncode,0,result.stderr)
            counter=root/'counter';counter.write_text('0')
            stubs='''get_port() { local n; n=$(cat "$COUNTER"); echo $((n+1)) > "$COUNTER"; if ((n<2)); then echo "$BUSY"; else echo $((30000+(n-2)/2)); fi; }
nc() { echo NC_MUST_NOT_BE_USED >&2; return 127; }
'''
            body='make_port sub_port panel_port ws_port trojan_port mtr_backend_port || exit 1; make_port vision_port fallback_port || exit 1; printf "%s\\n" "$sub_port" "$panel_port" "$ws_port" "$trojan_port" "$mtr_backend_port" "$vision_port" "$fallback_port"'
            r=shell(('check_free','make_port'),body,{'COUNTER':str(counter),'BUSY':str(busy)},stubs)
            self.assertEqual(r.returncode,0,r.stderr)
            ports=list(map(int,r.stdout.split()))
            self.assertEqual(len(ports),7);self.assertEqual(len(set(ports)),7);self.assertNotIn(busy,ports)
            self.assertNotIn('NC_MUST_NOT_BE_USED',r.stderr)
            constant=shell(('check_free','make_port'),body,stubs='get_port() { echo 30000; }; nc() { return 127; };')
            self.assertEqual(constant.returncode,0,constant.stderr)
            repeated=list(map(int,constant.stdout.split()))
            self.assertEqual(len(repeated),7);self.assertEqual(len(set(repeated)),7)

        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.bind(('127.0.0.1',0))
            r=shell(('check_free',),'check_free "$PORT"',{'PORT':str(udp.getsockname()[1])},'nc() { return 127; };')
            self.assertEqual(r.returncode,1,'UDP occupancy must not reserve the TCP namespace')

    def test_port_exhaustion_and_probe_errors_stop_bounded(self):
        for probe in ('check_free() { return 0; };','python3() { return 127; };'):
            r=shell(('check_free','make_port'),'make_port selected; exit "$?"',
                    stubs='get_port() { echo 32000; };\n'+probe,timeout=4)
            self.assertNotEqual(r.returncode,0)
            self.assertRegex(r.stderr,'(?i)port|probe')

    def test_vision_nat_and_ipv4_only_do_not_require_matching_route_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            stubs='''curl() { if [[ "$*" == *-o* ]]; then printf 'pass\\n' > "${@: -1}"; fi; }
preflight_vision_artifacts() { :; }
get_server_ip() { IP6=''; echo ROUTE_LOOKUP >&2; }
python3() {
    if [[ $# == 6 && $1 == - ]]; then
        command python3 -c 'import socket,sys; socket.getaddrinfo=lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,"",("203.0.113.10",443))]; exec(sys.stdin.read())' "${@:2}"
    else command python3 "$@"; fi
}
'''
            for interface in ('203.0.113.10','10.0.0.10'):
                with self.subTest(interface=interface):
                    env={'PANEL_TAG':'v3.10.0','PANEL_STAGE':directory,'GITHUB_RAW':'https://example.invalid',
                         'INSTALL_VISION':'y','INSTALL_SECURITY':'n','CREATE_CLIENT':'n',
                         'domain':'panel.example','reality_domain':'reality.example','vision_domain':'vision.example',
                         'IP4':interface,'IP6':''}
                    r=shell(('valid_hostname','preflight_integrated_features'),
                            'preflight_integrated_features || exit 1; echo "$vision_domain"',env,stubs)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(r.stdout.strip(),'vision.example')
                    self.assertNotIn('ROUTE_LOOKUP',r.stderr)
            for bad in ('https://vision.example','panel.EXAMPLE','REALITY.example','vision.example.','bad_.example'):
                r=shell(('valid_hostname','preflight_integrated_features'),
                        'preflight_integrated_features && echo CLEANUP_REACHED', {**env,'vision_domain':bad},stubs)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',r.stdout)

    def test_ipv6_family_capability_and_exact_vision_artifacts(self):
        vision=helper('vision');real_socket=socket.socket
        for available in (True,False):
            def create(family,*args,**kwargs):
                if family==socket.AF_INET6 and not available:raise OSError(errno.EAFNOSUPPORT,'disabled')
                return real_socket(family,*args,**kwargs)
            with patch.object(vision.socket,'socket',side_effect=create):
                config=vision.acme_config('vision.example')
            self.assertEqual('listen [::]:80;' in config,available)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);site=root/'site';acme=root/'acme'
            site.write_text(vision.fallback_config('vision.example',12001))
            legacy=vision.MARKER+'server {\n    listen 80;\n    listen [::]:80;\n    server_name vision.example;\n    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; try_files $uri =404; }\n    location / { return 301 https://$host$request_uri; }\n}\n'
            for text in (legacy,legacy.replace('    listen [::]:80;\n','')):
                acme.write_text(text)
                with patch.object(vision,'ipv6_available',return_value=False):
                    self.assertEqual(vision.nginx_artifact_domain(site,acme),'vision.example')
                acme.write_text(text.replace('root /var/www/acme','root /foreign'))
                with self.assertRaises(ValueError):vision.nginx_artifact_domain(site,acme)

    def test_real_nginx_ipv4_main_and_vision_acme(self):
        nginx_ipv4_acme(simulate=True)

    def test_dns_checkpoint_writer_reader_roundtrip_and_security(self):
        security=helper('security')
        def command(*args,**kwargs):
            if args[1]=='is-active':return 'inactive'
            if args[1]=='is-enabled':return 'disabled'
            return ''
        targets=(None,'/run/systemd/resolve/stub-resolv.conf','../run/systemd/resolve/resolv.conf',
                 '/run/NetworkManager/resolv.conf','/run/resolvconf/resolv.conf','../run/custom-resolver/missing')
        for target in targets:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'etc').mkdir();resolv=root/'etc/resolv.conf'
                if target is None:resolv.write_text('nameserver 192.0.2.1\n')
                else:resolv.symlink_to(target)
                with patch.object(Path,'stat',root_stat),patch.object(security,'command',side_effect=command):
                    txn=security.Transaction(root,services=('systemd-resolved.service',),files=(security.FILES[-1],))
                    self.addCleanup(txn.temp.cleanup);checkpoint=root/'checkpoint';txn.save_dns(checkpoint)
                    loaded=security.Transaction.load_dns(checkpoint,root);self.addCleanup(loaded.temp.cleanup)
                    resolv.unlink();resolv.write_text('temporary DNS\n');loaded.rollback()
                    if target is None:self.assertEqual(resolv.read_text(),'nameserver 192.0.2.1\n')
                    else:self.assertTrue(resolv.is_symlink());self.assertEqual(os.readlink(resolv),target)
                    # The accepted reader must still reject unrelated objects/metadata/modes.
                    extra=checkpoint/'extra';extra.write_text('foreign')
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    extra.unlink();meta=checkpoint/'state.json';original=meta.read_text()
                    meta.write_text(original.replace('systemd-resolved.service','ssh.service'))
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    meta.write_text(original);meta.chmod(0o666)
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    meta.chmod(0o600);checkpoint.chmod(0o777)
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    checkpoint.chmod(0o700)
                    for bad_owner in (checkpoint,meta,checkpoint/'1'):
                        def wrong_owner(path,*args,**kwargs):
                            value=root_stat(path,*args,**kwargs)
                            if path==bad_owner:
                                fields=list(value);fields[4]=1000;value=os.stat_result(fields)
                            return value
                        with patch.object(Path,'stat',wrong_owner), self.assertRaises(ValueError):
                            security.Transaction.load_dns(checkpoint,root)


    def test_dns_real_rollback_failure_remains_unverified(self):
        security=helper('security')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'etc').mkdir();resolv=root/'etc/resolv.conf'
            target='/run/NetworkManager/resolv.conf';resolv.symlink_to(target)
            policy=root/security.FILES[-1].lstrip('/');policy.parent.mkdir(parents=True)
            def command(*args,**kwargs):
                if args[0]=='getent':raise OSError('controlled resolution failure')
                if args[1]=='is-active':return 'inactive'
                if args[1]=='is-enabled':return 'disabled'
                return ''
            with patch.object(Path,'stat',root_stat),patch.object(security,'command',side_effect=command):
                txn=security.Transaction(root,services=('systemd-resolved.service',),files=(security.FILES[-1],))
                self.addCleanup(txn.temp.cleanup);checkpoint=root/'checkpoint';txn.save_dns(checkpoint)
                resolv.unlink();resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf');policy.write_text(security.DOT)
                result=security.rollback_dns_checkpoint(checkpoint,root)
                self.assertEqual(result['status'],'failed_unverified')
                self.assertEqual(os.readlink(resolv),target)

    def test_vision_certificate_failure_reaches_acme_and_never_reports_ready(self):
        from certificate_fixtures import relocate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in ('etc/nginx/sites-available','etc/nginx/sites-enabled','etc/letsencrypt/renewal-hooks/deploy'):
                (root/path).mkdir(parents=True)
            stubs="""nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }
python3() { if [[ $1 == - ]]; then command python3 \"$@\"; else echo '# ACME fixture'; fi; }
certbot() { echo \"$1\" >> \"$MARKER\"; return 33; }
"""
            source='\n'.join(function(n) for n in ('get_port','check_free','make_port'))+'\n'+relocate(function('install_vision'),root)
            body='status=0; install_vision || status=$?; printf "%s|%s" "$status" "$VISION_RESULT"; exit "$status"'
            r=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\n'+body],
                env={**os.environ,'MARKER':str(root/'certbot'),'vision_domain':'vision.example','PANEL_STAGE':str(root)},capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual((root/'certbot').read_text().splitlines(),['certonly'])
            self.assertEqual(r.stdout,'1|failed_rolled_back')
            self.assertFalse((root/'etc/nginx/sites-available/vision-acme.conf').exists())

    def test_actual_vision_allocation_keeps_earlier_project_ports(self):
        from certificate_fixtures import relocate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);counter=root/'counter';counter.write_text('0')
            (root/'etc/nginx/sites-available').mkdir(parents=True)
            (root/'etc/letsencrypt/renewal-hooks/deploy').mkdir(parents=True)
            stubs="""get_port() { local n; n=$(cat \"$COUNTER\"); echo $((n+1)) > \"$COUNTER\"; echo $((35000+n/2)); }
nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }
python3() { if [[ $1 == - ]]; then command python3 \"$@\"; else return 1; fi; }
"""
            source='\n'.join(function(n) for n in ('check_free','make_port'))+'\n'+relocate(function('install_vision'),root)
            body='make_port sub_port panel_port ws_port trojan_port mtr_backend_port || exit 1; install_vision || :; printf "%s\\n" "${ALLOCATED_TCP_PORTS[@]}"'
            r=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\n'+body],
                env={**os.environ,'COUNTER':str(counter),'vision_domain':'vision.example','PANEL_STAGE':str(root)},capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            ports=list(map(int,r.stdout.split()));self.assertEqual(len(ports),7);self.assertEqual(len(set(ports)),7)


if __name__=='__main__':unittest.main()

"""Native systemd and authenticated DNS-over-TLS in an isolated disposable VM.

No Internet DoT dependency. Production resolver addresses exist only on container
loopback; their TLS servers use a generated test CA in this VM's trust store.
"""
import importlib.util
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest


class SecuritySystemd(unittest.TestCase):
    def test_real_security_strict_tls_and_rollback(self):
        if Path('/proc/1/comm').read_text().strip() != 'systemd':
            self.fail('Requires real systemd PID 1 in a disposable VM; never mocked PASS')
        from test_integrated_features import helper
        security = helper('security')
        run = lambda *args: subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=90)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cert, key = root/'cert.pem', root/'key.pem'
            run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=Test DNS CA', '-addext', 'subjectAltName=DNS:one.one.one.one,DNS:dns.google',
                '-addext', 'basicConstraints=critical,CA:TRUE', '-out', str(cert), '-keyout', str(key))
            ca = Path('/usr/local/share/ca-certificates/xui-ci-dot.crt'); ca.write_bytes(cert.read_bytes())
            # Offline fixture trusts its generated CA only. Avoid hashing every
            # public CA under TCG; hostname/chain verification stays real.
            Path('/etc/ca-certificates.conf').write_text('')
            run('update-ca-certificates','--fresh')
            # getaddrinfo/resolved need a non-loopback configured address. A
            # guest-only dummy interface supplies it without any outside network.
            run('modprobe','dummy')
            run('ip','link','add','xui-test','type','dummy')
            run('ip','address','add','192.0.2.10/24','dev','xui-test')
            run('ip','link','set','xui-test','up')
            seen, errors, stop = [], [], threading.Event()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
            servers = []
            for ip in ('1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4'):
                run('ip', 'address', 'add', ip+'/32', 'dev', 'lo')
                listener = socket.socket(); listener.bind((ip, 853)); listener.listen(); listener.settimeout(.5)
                servers.append(listener)
                def serve(listener=listener):
                    while not stop.is_set():
                        try:
                            conn, _ = listener.accept()
                        except socket.timeout: continue
                        except OSError: return
                        def answer(conn=conn):
                            try:
                                with context.wrap_socket(conn, server_side=True) as tls:
                                    tls.settimeout(5)
                                    while not stop.is_set():
                                        size = tls.recv(2)
                                        if not size: break
                                        if len(size)!=2: raise ValueError('Short DNS length')
                                        count = struct.unpack('!H', size)[0]; packet = b''
                                        while len(packet)<count: packet += tls.recv(count-len(packet))
                                        if stop.is_set(): break
                                        end=12
                                        while packet[end]: end += packet[end]+1
                                        end += 5
                                        typ=struct.unpack('!H', packet[end-4:end-2])[0]
                                        question=packet[12:end]
                                        addr=socket.inet_aton('203.0.113.7') if typ==1 else socket.inet_pton(socket.AF_INET6, '2001:db8::7') if typ==28 else None
                                        response=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(addr is not None),0,0)+question
                                        if addr: response += b'\xc0\x0c'+struct.pack('!HHIH',typ,1,1,len(addr))+addr
                                        seen.append((tls.version(), question))
                                        tls.sendall(struct.pack('!H',len(response))+response)
                            except (OSError, ssl.SSLError): pass
                            except Exception as exc: errors.append(str(exc))
                        threading.Thread(target=answer, daemon=True).start()
                threading.Thread(target=serve, daemon=True).start()
            self.addCleanup(stop.set)
            for listener in servers: self.addCleanup(listener.close)
            with socket.create_connection(('1.1.1.1',853),timeout=5) as plain:
                with ssl.create_default_context().wrap_socket(plain,server_hostname='one.one.one.one') as tls:
                    self.assertIn(tls.version(),('TLSv1.2','TLSv1.3'))
            # This test deliberately sets a standard baseline in its private VM.
            Path('/etc/resolv.conf').unlink(); Path('/etc/resolv.conf').symlink_to('/run/systemd/resolve/stub-resolv.conf')
            run('systemctl', 'enable', '--now', 'systemd-resolved', 'ssh')
            effective = run('/usr/sbin/sshd', '-T')
            before = {p: p.read_bytes() for p in Path('/etc/ssh').rglob('*') if p.is_file()}
            # Snapshot before applying the production security function, restore afterwards.
            snapshot = security.Transaction()
            self.addCleanup(snapshot.temp.cleanup)
            capture = subprocess.Popen(['tcpdump','-i','lo','-n','-U','-w',str(root/'dns.pcap'),
                        'dst port 53 and (dst host 1.1.1.1 or dst host 1.0.0.1 or dst host 8.8.8.8 or dst host 8.8.4.4)'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                result = security.configure()
                if result['status'] != 'configured': print('TLS queries observed:',len(seen),'server errors:',errors,flush=True)
                self.assertEqual(result['status'], 'configured', result)
                self.assertEqual(result['dot'], 'configured')
                self.assertTrue(seen, 'No actual TLS DNS query observed')
                self.assertFalse(errors, errors)
                self.assertTrue(all(version in ('TLSv1.2','TLSv1.3') for version,_ in seen))
                self.assertEqual(run('/usr/sbin/sshd','-T'), effective)
                self.assertEqual({p:p.read_bytes() for p in before}, before)
                for name,value in (('maxretry','5'),('findtime','1800'),('bantime','3600')):
                    self.assertEqual(run('fail2ban-client','get','sshd',name).strip(),value)
                run('fail2ban-client','status','sshd')
                # Real socket activation overrides sshd's configured port. This
                # fixture changes only its socket; production must merely detect it.
                socket_drop = Path('/etc/systemd/system/ssh.socket.d/99-xui-ci.conf')
                socket_drop.parent.mkdir(exist_ok=True)
                socket_drop.write_text('[Socket]\nListenStream=\nListenStream=127.0.0.1:2222\n')
                run('systemctl','stop','ssh.socket','ssh.service')
                run('systemctl','daemon-reload')
                run('systemctl','enable','--now','ssh.socket')
                with socket.create_connection(('127.0.0.1',2222),timeout=5) as ssh:
                    self.assertTrue(ssh.recv(200).startswith(b'SSH-2.0-'))
                self.assertEqual(security.configure()['status'],'configured')
                self.assertEqual(security.ssh_ports(effective,run('systemctl','show','ssh.socket','-p','Listen','--value')),[2222])
                self.assertIn('2222',run('fail2ban-client','-d'))
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
                # No silent downgrade when authenticated TLS endpoints become unavailable.
                stop.set()
                for listener in servers: listener.close()
                run('resolvectl','flush-caches')
                failure = subprocess.run(['timeout','20','resolvectl','query','--cache=no','unavailable.example'],capture_output=True)
                self.assertNotEqual(failure.returncode,0)
                capture.terminate(); capture.wait(timeout=10)
                snapshot.rollback()
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
                # Invoke production rollback after a real unavailable TLS upstream,
                # rather than relying only on a manually restored snapshot.
                failed = security.configure()
                self.assertEqual(failed['status'],'failed_rolled_back',failed)
                self.assertTrue(all(not Path(name).exists() for name in security.FILES))
                self.assertEqual(os.readlink('/etc/resolv.conf'),'/run/systemd/resolve/stub-resolv.conf')
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
            finally:
                if capture.poll() is None: capture.terminate(); capture.wait(timeout=10)
                if any((Path(name)).exists() for name in security.FILES): snapshot.rollback()
            plaintext = subprocess.check_output(['tcpdump','-nn','-r',str(root/'dns.pcap')],text=True,stderr=subprocess.DEVNULL,timeout=20)
            self.assertEqual(plaintext.strip(),'','Plaintext DNS reached an upstream')
            print('REAL systemd / sshd jail / timers / authenticated TLS DNS / no plaintext / rollback: PASS')

"""Pilot-only external DNS, DoT and DoH boundaries, never application mocks."""
import base64, json, socket, socketserver, ssl, struct, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
ROOT=Path('/pilot')
socket.setdefaulttimeout(10)

def reply(packet, address):
    end=12
    while packet[end]: end+=packet[end]+1
    end+=5
    typ=struct.unpack('!H',packet[end-4:end-2])[0]
    return packet[:2]+struct.pack('!5H',0x8180,1,int(typ==1),0,0)+packet[12:end]+(b'\xc0\x0c'+struct.pack('!HHIH',1,1,1,4)+socket.inet_aton(address) if typ==1 else b'')

def answer(packet, pebble=False):
    off=12;labels=[]
    while packet[off]:
        n=packet[off];off+=1;labels.append(packet[off:off+n].decode());off+=n
    name='.'.join(labels)
    if name.endswith('.example.test'): address='127.0.0.1' if pebble else '10.0.2.15'
    elif name in ('dns.cloudflare.com','dns.google','dns.quad9.net','adguardteam.github.io'):address='10.0.2.2'
    elif name in ('cloudflare.com','debian.org') or name.startswith('cold-'):
        address='203.0.113.7'
    else:
        # Only controlled health/origin domains are synthetic. Official package
        # and release hosts use the runner's normal resolver, also without a proxy.
        try:address=socket.getaddrinfo(name,443,socket.AF_INET,socket.SOCK_STREAM)[0][4][0]
        except socket.gaierror:
            return packet[:2]+struct.pack('!5H',0x8182,1,0,0,0)+packet[12:off+5]
    return reply(packet,address)

context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(ROOT/'fixture.crt',ROOT/'fixture.key')

def serve_dns(address,port,tls=False,pebble=False):
    class UDP(socketserver.BaseRequestHandler):
        def handle(self):
            packet,sock=self.request;sock.sendto(answer(packet,pebble),self.client_address)
    class TCP(socketserver.BaseRequestHandler):
        def handle(self):
            c=self.request
            try:
                c.settimeout(5)
                if tls:
                    if (ROOT/'dot-outage').exists():c.close();return
                    c=context.wrap_socket(c,server_side=True)
                def exact(n):
                    b=b''
                    while len(b)<n:
                        x=c.recv(n-len(b))
                        if not x:raise EOFError()
                        b+=x
                    return b
                while True:
                    size=struct.unpack('!H',exact(2))[0];packet=exact(size)
                    data=answer(packet,pebble);c.sendall(struct.pack('!H',len(data))+data)
                    with (ROOT/'dns-observations.log').open('a') as f:f.write(('TLS' if tls else 'TCP')+' query\n')
            except (OSError,EOFError,ssl.SSLError): pass
            finally:c.close()
    class TS(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
    tcp=TS((address,port),TCP);threading.Thread(target=tcp.serve_forever,daemon=True).start()
    if not tls:
        udp=socketserver.ThreadingUDPServer((address,port),UDP)
        threading.Thread(target=udp.serve_forever,daemon=True).start()

serve_dns('0.0.0.0',53);serve_dns('127.0.0.1',1053,pebble=True);serve_dns('0.0.0.0',853,True)
class HTTPS(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path=='/dns-query':
            raw=parse_qs(url.query).get('dns',[''])[0];data=answer(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
            self.send_response(200);self.send_header('Content-Type','application/dns-message')
        elif url.path=='/HostlistsRegistry/assets/filter_1.txt':
            data=b'! Isolated acceptance filter fixture\n';self.send_response(200)
        else: data=b'';self.send_response(404)
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        packet=self.rfile.read(int(self.headers['Content-Length']));data=answer(packet)
        self.send_response(200);self.send_header('Content-Type','application/dns-message');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
http=ThreadingHTTPServer(('0.0.0.0',443),HTTPS);http.socket=context.wrap_socket(http.socket,server_side=True)
threading.Thread(target=http.serve_forever,daemon=True).start()
class Origin(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        data=('FRESH-INSTALL-'+self.path).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers()
        self.wfile.write(data[:7]);self.wfile.flush();self.wfile.write(data[7:])
origin=ThreadingHTTPServer(('0.0.0.0',18081),Origin)
threading.Thread(target=origin.serve_forever,daemon=True).start()
(ROOT/'host-ready').touch()
threading.Event().wait()

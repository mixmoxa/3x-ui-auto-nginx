"""Small real HTTP/3 test client; distro aioquic is a test-only dependency."""
import asyncio
import ssl
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.h3.connection import H3Connection, H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated


class HTTP3(QuicConnectionProtocol):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.http=H3Connection(self._quic);self.pending={}

    def quic_event_received(self,event):
        if isinstance(event,ConnectionTerminated):
            for future,_,_ in self.pending.values():
                if not future.done():future.set_exception(ConnectionError('QUIC connection closed'))
        for response in self.http.handle_event(event):
            if isinstance(response,(HeadersReceived,DataReceived)) and response.stream_id in self.pending:
                future,headers,body=self.pending[response.stream_id]
                if isinstance(response,HeadersReceived):headers.extend(response.headers)
                else:body.extend(response.data)
                if response.stream_ended and not future.done():future.set_result((headers,bytes(body)))

    async def request(self,path,method,authority,extra,body):
        stream=self._quic.get_next_available_stream_id();future=asyncio.get_running_loop().create_future()
        self.pending[stream]=(future,[],bytearray())
        self.http.send_headers(stream,[(b':method',method.encode()),(b':scheme',b'https'),
            (b':authority',authority.encode()),(b':path',path.encode()),*extra],end_stream=not body)
        if body:self.http.send_data(stream,body,end_stream=True)
        self.transmit()
        headers,data=await asyncio.wait_for(future,10)
        return dict(headers),data,self._quic.tls._peer_certificate.serial_number


async def request(address,port,name,cafile,path='/',method='GET',authority=None,extra=(),body=b'',verify=True):
    config=QuicConfiguration(is_client=True,alpn_protocols=H3_ALPN,server_name=name,idle_timeout=5)
    config.load_verify_locations(cafile=str(cafile))
    if not verify:config.verify_mode=ssl.CERT_NONE  # Explicit adversarial test client only.
    async with connect(address,port,configuration=config,create_protocol=HTTP3) as client:
        return await client.request(path,method,authority or name,extra,body)

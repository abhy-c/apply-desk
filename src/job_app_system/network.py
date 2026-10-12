"""Bounded public-HTTPS downloads with DNS pinning and TLS hostname verification."""
import http.client, ipaddress, json, socket, ssl
from urllib.parse import urlsplit, urljoin
from .validation import public_url

MAX_REDIRECTS=5

def public_addresses(host):
    records=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('The hostname resolves to a private or non-public address')
    return addresses

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host,443,timeout=20,context=ssl.create_default_context())
        self.address=address
    def connect(self):
        connection=socket.create_connection((self.address,443),self.timeout)
        try: self.sock=self._context.wrap_socket(connection,server_hostname=self.host)
        except BaseException:
            connection.close(); raise

def download(url, *, max_bytes=2000000, content_types=None):
    for redirect in range(MAX_REDIRECTS+1):
        url=public_url(url,required=True)
        parsed=urlsplit(url)
        addresses=public_addresses(parsed.hostname)
        connection=PinnedHTTPSConnection(parsed.hostname,addresses[0])
        try:
            path=parsed.path or '/'
            if parsed.query: path+='?'+parsed.query
            connection.request('GET',path,headers={'User-Agent':'ApplyDesk/0.2','Accept':'application/json,text/html,application/xhtml+xml'})
            response=connection.getresponse()
            if response.status in {301,302,303,307,308}:
                location=response.getheader('Location')
                if not location: raise ValueError('Redirect has no destination')
                url=urljoin(url,location)
                continue
            if response.status!=200: raise ValueError(f'Employer server returned HTTP {response.status}')
            content_type=response.headers.get_content_type()
            if content_types and content_type not in content_types: raise ValueError('Unsupported response content type')
            body=response.read(max_bytes+1)
            if len(body)>max_bytes: raise ValueError('Response exceeds the import size limit')
            charset=response.headers.get_content_charset() or 'utf-8'
            return url,body.decode(charset,errors='replace')
        finally: connection.close()
    raise ValueError('Too many redirects')

def json_download(url):
    _,body=download(url,max_bytes=10000000,content_types={'application/json'})
    return json.loads(body)

"""Shared input validation; validation has no persistence or network side effects."""
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl
import ipaddress

SENSITIVE_QUERY_KEYS = {'token','access_token','api_key','apikey','password','secret','authorization','auth','code','signature','sig','x-amz-credential','x-amz-signature'}

def public_url(value, *, required=False):
    value = str(value or '').strip()
    if not value:
        if required: raise ValueError('A public HTTPS URL is required')
        return ''
    if len(value) > 4096 or any(ord(c) < 32 for c in value): raise ValueError('Invalid URL')
    parsed = urlsplit(value)
    host = (parsed.hostname or '').rstrip('.').lower()
    if any(c.isspace() for c in host) or '\\' in value: raise ValueError('Invalid URL hostname')
    if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None:
        raise ValueError('Use a public HTTPS URL without credentials')
    try: port = parsed.port
    except ValueError: raise ValueError('Invalid URL port')
    if port not in (None,443): raise ValueError('Only standard HTTPS URLs are supported')
    if host == 'localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host and ':' not in host:
        raise ValueError('Private URLs are not allowed')
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global: raise ValueError('Private URLs are not allowed')
    except ValueError as exc:
        if 'Private' in str(exc): raise
    if any(key.lower() in SENSITIVE_QUERY_KEYS for key,_ in parse_qsl(parsed.query)):
        raise ValueError('Use a public posting link without authentication query parameters')
    host = host.encode('idna').decode('ascii')
    netloc = '[' + host + ']' if ':' in host else host
    return urlunsplit(('https',netloc,parsed.path or '/',parsed.query,''))

def text(value, field, maximum=10000, required=False):
    if not isinstance(value, str): raise ValueError(f'{field} must be text')
    value = value.strip()
    if len(value)>maximum or '\x00' in value: raise ValueError(f'{field} is too long or invalid')
    if required and not value: raise ValueError(f'{field} is required')
    return value

def iso_date(value, field, *, allow_blank=True):
    value = text(value,field,10)
    if not value and allow_blank: return ''
    try:
        result = date.fromisoformat(value)
        if result.isoformat()!=value: raise ValueError()
    except ValueError: raise ValueError(f'{field} must be YYYY-MM-DD')
    return value

def job(row):
    result = dict(row)
    for key in ('company','role_title'): result[key]=text(row.get(key,''),key,500,True)
    result['posted_date']=iso_date(row.get('posted_date',''),'posted_date')
    result['role_url']=public_url(row.get('role_url',''))
    for key in ('location','domain_tags','seniority','source','role_id'): result[key]=text(row.get(key,''),key,1000)
    result['description']=text(row.get('description',''),'description',200000)
    for key,options,default in [('workplace',{'','remote','hybrid','onsite','on-site'},''),('status',{'open','closed','expired'},'open')]:
        value=text(row.get(key,default),key,30).lower()
        if value not in options: raise ValueError(f'Invalid {key}')
        result[key]=value
    return result

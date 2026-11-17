"""Token-bound principals. A UI username never grants authority by itself."""
import os,json,hmac
from urllib.parse import unquote
from ..modules.qgis_data import ApiError
def identity(header,username=''):
    token=header[7:] if header.startswith('Bearer ') else ''
    username=unquote(username)
    entries=[
        {'username':'qgis-user','aliases':['app_user','user'],'token':os.getenv('QGIS_USER_TOKEN',''),'role':'user','owner':'qgis-user'},
        {'username':'guest','aliases':['qgis-guest'],'token':os.getenv('QGIS_GUEST_TOKEN',''),'role':'guest','owner':'qgis-guest'},
        {'username':'analyst','aliases':['reader'],'token':os.getenv('DASHBOARD_TOKEN',''),'role':'reader','owner':'analyst'},
        {'username':'admin','aliases':['qgis-admin'],'token':os.getenv('QGIS_ADMIN_TOKEN',''),'role':'admin','owner':'qgis-admin'}]
    try:
        extra=json.loads(os.getenv('QGIS_IDENTITIES_JSON','[]'))
        if not isinstance(extra,list):raise ValueError()
        for entry in extra:
            if not isinstance(entry,dict) or not all(isinstance(entry.get(k),str) and entry[k] for k in ('username','token','role')):raise ValueError()
            if entry['role'] not in ('user','admin','guest','reader'):raise ValueError()
            if not isinstance(entry.get('owner',entry['username']),str) or not entry.get('owner',entry['username']):raise ValueError()
            if not isinstance(entry.get('aliases',[]),list) or not all(isinstance(v,str) for v in entry.get('aliases',[])):raise ValueError()
        entries+=extra
        tokens=[e['token'] for e in entries if e.get('token')]
        if len(tokens)!=len(set(tokens)):raise ValueError()
    except (ValueError,TypeError):raise ApiError(503,'Invalid principal configuration')
    for entry in entries:
        if entry.get('role') not in ('user','admin','guest','reader'):continue
        if username and username not in [entry['username'],*entry.get('aliases',[])]:continue
        if token and entry.get('token') and hmac.compare_digest(token.encode(),entry['token'].encode()):
            return entry['role'],entry.get('owner',entry['username'])
    raise ApiError(401,'Username/token mismatch or invalid token')

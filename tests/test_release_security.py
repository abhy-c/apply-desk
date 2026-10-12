import csv
import http.client
import json
import multiprocessing
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from job_app_system import web, network
from job_app_system.application import save_application_packet, load_application_packet, export_application_packet, save_profile
from job_app_system.initialization import initialize_workspace
from job_app_system.io import write_csv, read_jobs
from job_app_system.storage import atomic_text
from job_app_system.validation import public_url
from job_app_system.tool_imports import import_apify_jobs


@pytest.fixture
def local_api(tmp_path):
    initialize_workspace(tmp_path)
    web._safe_build(tmp_path/'data',tmp_path/'out')
    web.build_connection_rankings(tmp_path/'data',tmp_path/'out')
    server=web.LocalServer(('127.0.0.1',0),web._handler(tmp_path))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    port=server.server_address[1]
    cookie=''
    def request(method,path,payload=None,headers=None,authenticated=True):
        options={'Host':f'127.0.0.1:{port}'}
        if authenticated and cookie: options['Cookie']=cookie
        if method=='POST':
            options.update({'Origin':f'http://127.0.0.1:{port}','X-Apply-Desk-Request':'1','Content-Type':'application/json'})
        options.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        try:
            conn.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=options)
            response=conn.getresponse();body=response.read()
            return response.status,dict(response.getheaders()),body
        finally: conn.close()
    status,headers,_=request('GET','/',authenticated=False)
    assert status==200
    assert 'Set-Cookie' not in headers
    code=json.loads((tmp_path/'data/.session-key').read_text())['code']
    status,headers,_=request('POST','/api/session',{'code':code},authenticated=False)
    assert status==200
    cookie=headers['Set-Cookie'].split(';')[0]
    try: yield request,tmp_path
    finally: server.shutdown();server.server_close();thread.join()


def test_api_requires_session_and_rejects_foreign_callers(local_api):
    request,root=local_api
    original=(root/'data/jobs_seed.csv').read_bytes()
    assert request('GET','/api/state',authenticated=False)[0]==401
    assert request('POST','/api/session',{'code':'fictional-wrong-code'},authenticated=False)[0]==403
    assert request('GET','/api/state',headers={'Host':'untrusted.example'})[0]==403
    assert request('POST','/api/profile',{'full_name':'Injected'},headers={'Origin':'https://untrusted.example'})[0]==403
    assert request('POST','/api/profile',{'full_name':'Injected'},headers={'Content-Type':'text/plain'})[0]==415
    assert request('POST','/api/profile',{'full_name':'Injected'},headers={'X-Apply-Desk-Request':''})[0]==403
    assert not (root/'data/app_profile.json').exists()
    assert (root/'data/jobs_seed.csv').read_bytes()==original


def test_bootstrap_cookie_and_private_response_headers(local_api):
    request,root=local_api
    assert 'Set-Cookie' not in request('GET','/')[1]
    code=json.loads((root/'data/.session-key').read_text())['code']
    status,headers,_=request('POST','/api/session',{'code':code})
    assert status==200
    assert 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
    assert 'frame-ancestors' in headers['Content-Security-Policy']
    status,headers,_=request('GET','/api/state')
    assert status==200 and headers['Cache-Control']=='no-store'
    assert headers['X-Content-Type-Options']=='nosniff'


def test_no_automatic_plugin_read_and_explicit_opt_in(local_api,monkeypatch):
    request,_=local_api
    reads=[]
    monkeypatch.setattr(web,'read_job_apply_profile',lambda:reads.append(True) or {'connected':True,'profile':{'full_name':'Fictional'}})
    request('GET','/')
    assert request('GET','/api/job-apply-profile')[0]==200
    assert reads==[]
    assert request('POST','/api/job-apply-profile',{})[0]==400
    assert reads==[]
    assert request('POST','/api/job-apply-profile',{'consent':True})[0]==200
    assert reads==[True]


def test_state_get_is_read_only(local_api):
    request,root=local_api
    def snapshot():
        return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    before=snapshot()
    assert request('GET','/api/state?rebuild=1')[0]==200
    assert snapshot()==before


def test_invalid_job_does_not_change_storage_or_break_state(local_api):
    request,root=local_api
    before=(root/'data/jobs_seed.csv').read_bytes()
    payload={'company':'Example','role_title':'Product Manager','location':'United States','posted_date':'not-a-date','role_url':'https://example.com/job'}
    assert request('POST','/api/jobs',payload)[0]==400
    assert (root/'data/jobs_seed.csv').read_bytes()==before
    assert request('GET','/api/state')[0]==200


def test_legacy_invalid_row_is_excluded_and_reported(local_api):
    request,root=local_api
    with (root/'data/jobs_seed.csv').open('a') as f:
        f.write('invalid,Example,Product Manager,https://example.com/job,manual,invalid,United States,remote,b2b_saas,PM,open,Test\n')
    status,_,body=request('GET','/api/state')
    state=json.loads(body)
    assert status==200 and state['roles']==[]
    assert 'row 2' in state['validation_warnings'][0]


def test_json_shape_and_body_limits(local_api):
    request,_=local_api
    assert request('POST','/api/profile',[])[0]==400
    assert request('POST','/api/profile',{'full_name':'a'*10001})[0]==400
    assert request('POST','/api/profile',{},headers={'Content-Length':'1000001'})[0]==413


def test_listener_cannot_bind_to_network(tmp_path):
    with pytest.raises(ValueError,match='loopback'): web.serve(tmp_path,host='0.0.0.0')


def test_concurrent_saves_keep_every_action(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as executor:
        result=list(executor.map(lambda n:web._upsert_action(tmp_path,{'title':f'Fictional {n}'}),range(40)))
    assert len(result)==40
    assert len(web._actions(tmp_path))==40


def _process_save(directory,index):
    web._upsert_action(Path(directory),{'title':f'Fictional process {index}'})


def test_process_saves_share_the_workspace_lock(tmp_path):
    ctx=multiprocessing.get_context('spawn')
    workers=[ctx.Process(target=_process_save,args=(str(tmp_path),i)) for i in range(4)]
    for worker in workers: worker.start()
    for worker in workers:
        worker.join(15)
        assert worker.exitcode==0
    assert len(web._actions(tmp_path))==4


def test_atomic_replacement_failure_preserves_old_file(tmp_path,monkeypatch):
    path=tmp_path/'state.json';path.write_text('original')
    def fail(*args): raise OSError('Fictional interrupted replacement')
    with monkeypatch.context() as scoped:
        scoped.setattr('job_app_system.storage.os.replace',fail)
        with pytest.raises(OSError): atomic_text(path,'replacement')
    assert path.read_text()=='original'
    assert list(tmp_path.iterdir())==[path]


def test_profile_and_packet_files_are_private(tmp_path):
    save_profile(tmp_path,{'full_name':'Fictional'})
    if os.name!='nt':
        assert tmp_path.stat().st_mode & 0o777 == 0o700
        assert (tmp_path/'app_profile.json').stat().st_mode & 0o777 == 0o600


def test_distinct_ids_do_not_overwrite_packet_or_export(tmp_path):
    a='a'*72+'one';b='a'*72+'two'
    first={'role_id':a,'cover_letter':'Fictional A'};second={'role_id':b,'cover_letter':'Fictional B'}
    save_application_packet(tmp_path,first);save_application_packet(tmp_path,second)
    assert load_application_packet(tmp_path,a)['cover_letter']=='Fictional A'
    assert load_application_packet(tmp_path,b)['cover_letter']=='Fictional B'
    assert export_application_packet(tmp_path/'out',first)['path'] != export_application_packet(tmp_path/'out',second)['path']


def test_legacy_packet_collision_is_not_loaded(tmp_path):
    directory=tmp_path/'application_packets';directory.mkdir()
    (directory/'a.json').write_text(json.dumps({'role_id':'b','cover_letter':'Wrong identity'}))
    assert load_application_packet(tmp_path,'a') is None


@pytest.mark.parametrize('url',['javascript:void(0)','http://example.com/job','https://localhost./job','https://127.0.0.1/job','https://[::1]/job','https://user:password@example.com/job','https://example.com:8443/job','https://example.com/job?access_token=fictional'])
def test_invalid_urls_are_rejected(url):
    with pytest.raises(ValueError): public_url(url)


def test_private_dns_is_rejected_before_connect(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))])
    with pytest.raises(ValueError,match='private'): network.download('https://internal.example/job')


def test_dns_is_pinned_and_tls_uses_original_hostname(monkeypatch):
    observed={}
    class Context:
        def wrap_socket(self,connection,server_hostname): observed['hostname']=server_hostname;return connection
    class FakeSocket:
        def close(self): pass
    monkeypatch.setattr(socket,'create_connection',lambda address,timeout:observed.setdefault('address',address) and FakeSocket())
    conn=network.PinnedHTTPSConnection('careers.example','93.184.216.34');conn._context=Context();conn.connect()
    assert observed=={'address':('93.184.216.34',443),'hostname':'careers.example'}


def test_redirect_to_private_host_is_rejected(monkeypatch):
    monkeypatch.setattr(network,'public_addresses',lambda host:['93.184.216.34'])
    class Response:
        status=302
        def getheader(self,name): return 'https://127.0.0.1/job'
    class Connection:
        def __init__(self,*args): pass
        def request(self,*args,**kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(network,'PinnedHTTPSConnection',Connection)
    with pytest.raises(ValueError,match='Private'): network.download('https://careers.example/job')


@pytest.mark.parametrize('value',['=1+1','+1+1','-1+1','@SUM(1,2)',' \t=1+1'])
def test_spreadsheet_exports_escape_formulas_but_keep_source_values(tmp_path,value):
    source=tmp_path/'data/jobs_seed.csv';output=tmp_path/'out/roles_scored.csv'
    write_csv(source,[{'company':value}],['company']);write_csv(output,[{'company':value}],['company'])
    assert list(csv.DictReader(source.open()))[0]['company']==value
    assert list(csv.DictReader(output.open()))[0]['company']=="'"+value


def test_apify_import_validates_before_writing(tmp_path):
    source=tmp_path/'input.json';jobs=tmp_path/'data/jobs_seed.csv'
    source.write_text(json.dumps([{'company':'Example','title':'Product Manager','url':'javascript:void(0)','postedDate':'bad'}]))
    with pytest.raises(ValueError): import_apify_jobs(source,jobs)
    assert not jobs.exists()


def test_profile_preferences_change_ranking_and_exclusions():
    from datetime import date
    from job_app_system.models import Job
    from job_app_system.scoring import score_job
    today=date(2026,10,11)
    role=Job('fictional','Example','Senior Product Manager','https://example.com/job','manual',today,'Austin, TX','hybrid',{'fintech'},'Senior PM','open','Fictional')
    aligned={'target_titles':'Product Manager','target_locations':'Austin, TX','must_have':'fintech','avoid':''}
    different={'target_titles':'Program Manager','target_locations':'New York, NY','must_have':'edtech','avoid':''}
    assert score_job(role,None,today,aligned)['role_score']>score_job(role,None,today,different)['role_score']
    aligned['avoid']='Senior Product Manager'
    assert score_job(role,None,today,aligned)['role_eligible'] is False


def test_manual_ids_are_unique_even_for_identical_inputs(tmp_path):
    row={'company':'Example','role_title':'Product Manager','location':'United States','role_url':'https://example.com/job'}
    assert web._append_job(tmp_path,row)['role_id'] != web._append_job(tmp_path,row)['role_id']


def test_package_assets_are_available_as_resources():
    from importlib.resources import files
    assets=files('job_app_system').joinpath('assets')
    assert 'Apply Desk' in assets.joinpath('web/index.html').read_text()
    assert assets.joinpath('examples/jobs_seed.csv').read_text().startswith('role_id,')


def test_oversized_linkedin_archive_is_rejected(tmp_path,monkeypatch):
    import zipfile
    from job_app_system.connections import import_linkedin_export
    archive=tmp_path/'fictional.zip'
    with zipfile.ZipFile(archive,'w') as z: z.writestr('Connections.csv','First Name,Last Name\n')
    original=zipfile.ZipFile.infolist
    def oversized(self):
        members=original(self)
        members[0].file_size=20000001
        return members
    monkeypatch.setattr(zipfile.ZipFile,'infolist',oversized)
    with pytest.raises(ValueError,match='decompression'): import_linkedin_export(archive,tmp_path/'workspace')
    assert not (tmp_path/'workspace/data/linkedin_connections.csv').exists()


def test_release_allowlist_ignores_private_data_and_is_reproducible(tmp_path):
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('release_builder',root/'scripts/package_release.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    files=module.release_files(root)
    assert not any(name.startswith(('data/','out/','.git/','build/')) for name in files)
    assert module.build(root,tmp_path/'one')['sha256']==module.build(root,tmp_path/'two')['sha256']


def test_second_server_cannot_replace_active_workspace_code(local_api):
    _,root=local_api
    before=(root/'data/.session-key').read_bytes()
    with pytest.raises(ValueError,match='already owns'):
        web.LocalServer(('127.0.0.1',0),web._handler(root))
    assert (root/'data/.session-key').read_bytes()==before


def test_contact_evidence_rejects_authentication_links_before_saving(tmp_path):
    from job_app_system.connections import save_connection_review
    with pytest.raises(ValueError):
        save_connection_review(tmp_path,{'connection_id':'fictional','hiring_evidence_url':'https://example.com/job?access_token=fictional'})
    assert not (tmp_path/'connection_reviews.csv').exists()

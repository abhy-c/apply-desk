import json
from datetime import datetime,timezone,timedelta
import pytest
from job_app_system import portals as c,workspace as w


def add(root,url='https://example.wd5.myworkdayjobs.com/Careers?source=public'):
 return c.add(root,{'url':url,'label':'Example employer','browser':'chrome','confirmed':True})

def receipt(item,**extra):
 return {'id':item['id'],'revision':item['revision'],'observed_origin':item['origin'],'browser':'supported','page':'accessible','auth':'not_required','uploads':'supported','final_action_taken':False,'profile_read':False,'resume_uploaded':False,**extra}

@pytest.mark.parametrize('url,family',[
 ('https://www.linkedin.com/jobs/view/1','linkedin'),('https://job-boards.greenhouse.io/example','greenhouse'),
 ('https://jobs.ashbyhq.com/example','ashby'),('https://jobs.lever.co/example','lever'),
 ('https://ats.rippling.com/example','rippling'),('https://example.wd5.myworkdayjobs.com/jobs','workday'),
 ('https://linkedin.com.attacker.example/jobs','custom'),('https://myworkdayjobs.com.attacker.example/jobs','custom')])
def test_portal_family_uses_hostname_boundaries(url,family):assert c.identify(url)==family

def test_requires_consent_and_never_accepts_credentials(tmp_path):
 with pytest.raises(ValueError):c.add(tmp_path,{'url':'https://example.com','label':'Example'})
 with pytest.raises(ValueError):c.add(tmp_path,{'url':'https://example.com','label':'Example','confirmed':True,'password':'fictional-password'})
 with pytest.raises(ValueError):add(tmp_path,'https://example.com/?token=private')
 first=add(tmp_path);other=add(tmp_path,'https://other.wd5.myworkdayjobs.com/jobs')
 assert first['id']!=other['id'];assert first['entry_url'].endswith('/Careers');assert '?' not in first['entry_url']


def test_origin_changes_and_stale_choices_cannot_receive_receipt(tmp_path):
 item=add(tmp_path)
 with pytest.raises(ValueError,match='redirected'):c.receipt(tmp_path,receipt(item,observed_origin='https://another.example'))
 with pytest.raises(ValueError,match='changed'):c.receipt(tmp_path,receipt(item,revision='stale'))
 with pytest.raises(ValueError):c.receipt(tmp_path,receipt(item,profile_read=True))
 with pytest.raises(ValueError):c.receipt(tmp_path,receipt(item,details='Private page text'))
 assert c.state(tmp_path)['items'][0]['status']=='not_checked'


def test_preflight_is_separate_from_application_readiness_and_expires(tmp_path):
 item=add(tmp_path);c.receipt(tmp_path,receipt(item));assert c.state(tmp_path)['items'][0]['status']=='preflight_passed'
 assert not w.status(tmp_path)['resume_ready'];assert not w.read(tmp_path)['integration'].get('local_verified')
 s=w.read(tmp_path);s['portals'][0]['checked_at']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat();w.save(tmp_path,s)
 before=(tmp_path/'data'/w.STORE).read_bytes()
 assert c.state(tmp_path)['items'][0]['status']=='recheck_needed';assert (tmp_path/'data'/w.STORE).read_bytes()==before


def test_login_blocker_and_forget_do_not_modify_browser(tmp_path):
 item=add(tmp_path);assert c.receipt(tmp_path,receipt(item,auth='needs_login'))['status']=='needs_login'
 assert c.remove(tmp_path,{'id':item['id'],'confirmed':True})['browser_session_changed'] is False
 assert c.state(tmp_path)['items']==[]
 with pytest.raises(ValueError):c.receipt(tmp_path,receipt(item))


def test_diagnostics_contains_no_personal_settings_urls_or_paths(tmp_path):
 w.configure(tmp_path,{'focus':'PRIVATE-FOCUS','titles':'PRIVATE-TITLE','locations':'PRIVATE-LOCATION'})
 add(tmp_path)
 report=json.dumps(c.doctor(tmp_path))
 assert all(term not in report for term in ['PRIVATE-',str(tmp_path),'myworkdayjobs','Example employer','entry_url'])
 assert json.loads(report)['portal_count']==1


def test_duplicate_cancel_resume_and_terminal_requests(tmp_path):
 item=add(tmp_path);p={'kind':'portal_check','portal_id':item['id'],'confirmed':True}
 first=w.request(tmp_path,p);second=w.request(tmp_path,p);assert first['id']==second['id']
 with pytest.raises(ValueError):w.request_result(tmp_path,{'id':first['id'],'status':'complete'})
 w.request_result(tmp_path,{'id':first['id'],'status':'running'})
 w.request_result(tmp_path,{'id':first['id'],'status':'waiting_user','result':'Sign in yourself'})
 assert w.request_resume(tmp_path,{'id':first['id'],'confirmed':True})['id']==first['id']
 w.request_cancel(tmp_path,{'id':first['id'],'confirmed':True})
 with pytest.raises(ValueError):w.request_result(tmp_path,{'id':first['id'],'status':'running'})
 assert w.request(tmp_path,p)['id']!=first['id']
 assert len(w.read(tmp_path)['requests'])==2



def test_bad_json_types_and_corrupt_workspace_fail_clearly(tmp_path):
 with pytest.raises(ValueError):c.add(tmp_path,{'url':'https://example.com','label':'Example','browser':[],'confirmed':True})
 item=add(tmp_path)
 with pytest.raises(ValueError):c.receipt(tmp_path,receipt(item,auth=[]))
 (tmp_path/'data'/w.STORE).write_text('{broken JSON')
 report=c.doctor(tmp_path)
 assert report['workspace_readable'] is False
 assert 'broken JSON' not in json.dumps(report)

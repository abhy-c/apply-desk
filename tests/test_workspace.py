import json,zipfile
from datetime import date
from pathlib import Path
import pytest
from job_app_system import workspace as w,portable_resume as r

def config(root):
 w.configure(root,{'focus':'Finance','titles':'Financial Analyst','excluded_titles':'Product','locations':'London','sources_confirmed':True,'ranking_confirmed':True})
 w.source(root,{'name':'Example','url':'https://example.com/jobs','method':'codex','confirmed':True})

def listing(**extra):
 return {'role_id':'one','company':'Example','role_title':'Financial Analyst','role_url':'https://example.com/job','source':'test','location':'London','status':'open','description':'Own annual planning and forecasts.',**extra}

def test_setup_requires_all_inputs_without_personal_defaults(tmp_path):
 s=w.status(tmp_path);assert not s['search_ready'];assert s['workspace']['setup']=={}
 config(tmp_path);assert w.status(tmp_path)['search_ready'];assert not w.status(tmp_path)['resume_ready']

def test_user_focus_excludes_product_and_required_unknown_is_verification(tmp_path):
 config(tmp_path)
 w.set_rule(tmp_path,{'field':'salary','label':'Salary','operator':'minimum','value':'50000','mode':'required','confirmed':True})
 assert w.assess(tmp_path,listing())['verification_state']=='needs_verification'
 assert w.assess(tmp_path,listing(salary='60000'))['role_eligible']
 assert w.assess(tmp_path,listing(salary='40000'))['verification_state']=='excluded'
 assert w.assess(tmp_path,listing(role_title='Product Manager',salary='60000'))['verification_state']=='excluded'

def test_no_fixed_country_freshness_or_seniority(tmp_path):
 config(tmp_path);assert w.assess(tmp_path,listing(posted_date='2020-01-01',location='London'))['role_eligible']
 w.set_rule(tmp_path,{'field':'posted_date','label':'Freshness','operator':'maximum','value':'14','mode':'required','confirmed':True})
 assert not w.assess(tmp_path,listing(posted_date='2020-01-01'))['role_eligible']
 assert w.assess(tmp_path,listing())['verification_state']=='needs_verification'

def test_feedback_does_not_change_rules_and_approved_rule_can_undo(tmp_path):
 config(tmp_path);w.feedback(tmp_path,{'role_id':'one','decision':'reject','reason':'Too senior'})
 assert w.read(tmp_path)['rules']==[]
 p=w.improvement(tmp_path,{'kind':'rule','title':'Exclude directors','reason':'Recurring feedback','evidence':['one','two'],'validation':'Compare queue','undo':'Undo rule','change':{'field':'role_title','label':'Director exclusion','operator':'excludes','value':'Director','mode':'required'}})
 assert w.read(tmp_path)['rules']==[]
 with pytest.raises(ValueError):w.review_improvement(tmp_path,{'id':p['id'],'revision':'wrong','decision':'approved'})
 w.review_improvement(tmp_path,{'id':p['id'],'revision':p['revision'],'decision':'approved'})
 h=w.read(tmp_path)['history'][-1];w.undo(tmp_path,{'id':h['id'],'confirmed':True});assert w.read(tmp_path)['rules']==[]

def test_sources_are_not_working_until_checked_and_zero_matches_is_success(tmp_path):
 config(tmp_path);s=w.read(tmp_path)['sources'][0];assert s['state']=='untested'
 w.source_result(tmp_path,{'id':s['id'],'state':'working','usable':3,'matches':0,'evidence':'Read official jobs','coverage':'One employer board'})
 assert w.read(tmp_path)['sources'][0]['state']=='working'

def test_folder_inventory_does_not_read_contents_and_changed_file_rejected(tmp_path,monkeypatch):
 folder=tmp_path/'selected';folder.mkdir();p=folder/'story.txt';p.write_text('Private story')
 original=Path.read_bytes
 monkeypatch.setattr(Path,'read_bytes',lambda self: (_ for _ in ()).throw(AssertionError('Read during inventory')))
 items=r.inventory(tmp_path,{'folder':str(folder)})
 monkeypatch.setattr(Path,'read_bytes',original)
 p.write_text('Changed private story')
 with pytest.raises(ValueError):r.import_files(tmp_path,{'ids':[items[0]['id']],'consent':True})

def test_intake_and_qualitative_evidence_are_bound_to_current_rule(tmp_path):
 config(tmp_path)
 raw=listing(evidence='Official page retrieved',posted_date='2026-10-12',domain_tags='',seniority='',workplace='hybrid')
 id=w.intake(tmp_path,{'jobs':[raw]})['ids'][0]
 rule=w.set_rule(tmp_path,{'label':'Planning ownership','field':'ownership','operator':'qualitative','value':'Own planning','mode':'required','confirmed':True})
 row={**raw,'role_id':id,'source':'codex:selected'};row.pop('evidence')
 w.qualitative(tmp_path,{'role_id':id,'rule_id':rule['id'],'role':row,'result':'match','evidence':'Own annual planning','url':raw['role_url']})
 assert w.assess(tmp_path,row)['role_eligible']
 w.set_rule(tmp_path,{**rule,'value':'Own investment decisions','confirmed':True})
 assert w.assess(tmp_path,row)['verification_state']=='needs_verification'
 with pytest.raises(ValueError):w.qualitative(tmp_path,{'role_id':id,'rule_id':rule['id'],'role':row,'result':'match','evidence':'Invented fact','url':raw['role_url']})

def fixture_master(tmp_path):
 from lxml import etree
 root=etree.Element('{'+r.W+'}document',nsmap={'w':r.W});body=etree.SubElement(root,'{'+r.W+'}body');p=etree.SubElement(body,'{'+r.W+'}p')
 props=etree.SubElement(p,'{'+r.W+'}pPr');etree.SubElement(props,'{'+r.W+'}numPr')
 run=etree.SubElement(p,'{'+r.W+'}r');rp=etree.SubElement(run,'{'+r.W+'}rPr');etree.SubElement(rp,'{'+r.W+'}sz').set('{'+r.W+'}val','22')
 etree.SubElement(run,'{'+r.W+'}t').text='Built forecasts.'
 file=tmp_path/'master.docx'
 with zipfile.ZipFile(file,'w') as z:z.writestr('word/document.xml',etree.tostring(root));z.writestr('word/styles.xml',b'unchanged styles')
 r.save(tmp_path,{'master':{'docx':str(file),'sha256':r.digest(file),'pages':1,'bullets':[{'id':'0','text':'Built forecasts.'}]},'files':[],'facts':[],'proposals':[],'exports':[]})
 return file

def test_pending_tampered_and_changed_master_never_export(tmp_path,monkeypatch):
 file=fixture_master(tmp_path);fact=r.fact(tmp_path,{'text':'Built forecasts for annual planning','confirmed':True})
 p=r.propose(tmp_path,{'role_id':'one','slot_id':'0','text':'Built annual planning forecasts.','reason':'Specific scope','fact_ids':[fact['id']]})
 with pytest.raises(ValueError):r.generate(tmp_path,{'role_id':'one','confirmed':True})
 with pytest.raises(ValueError):r.review(tmp_path,{'id':p['id'],'revision':'stale','decision':'approved'})
 r.review(tmp_path,{'id':p['id'],'revision':p['revision'],'decision':'approved'})
 store=r.load(tmp_path);store['proposals'][0]['text']='Invented outcome';r.save(tmp_path,store)
 with pytest.raises(ValueError):r.generate(tmp_path,{'role_id':'one','confirmed':True})

def test_both_drafts_page_limit_format_preservation_and_application_only_handoff(tmp_path,monkeypatch):
 master=fixture_master(tmp_path);f=r.fact(tmp_path,{'text':'Built forecasts for annual planning','confirmed':True})
 proposal=r.propose(tmp_path,{'role_id':'one','slot_id':'0','text':'Built annual planning forecasts.','reason':'Specific scope','fact_ids':[f['id']]})
 r.review(tmp_path,{'id':proposal['id'],'revision':proposal['revision'],'decision':'approved'})
 monkeypatch.setattr(r,'render_word',lambda root,docx,pdf:Path(pdf).write_bytes(b'fictional PDF'))
 monkeypatch.setattr(r,'pdf_pages',lambda path:2)
 with pytest.raises(ValueError,match='exceeds'):r.generate(tmp_path,{'role_id':'one','confirmed':True})
 assert r.load(tmp_path)['exports']==[]
 monkeypatch.setattr(r,'pdf_pages',lambda path:1)
 export=r.generate(tmp_path,{'role_id':'one','confirmed':True})
 with zipfile.ZipFile(export['docx']) as z:assert z.read('word/styles.xml')==b'unchanged styles'
 with pytest.raises(ValueError):r.handoff(tmp_path,{'export_id':export['id'],'role_id':'one','job_url':'https://example.com/job'})
 r.visual_review(tmp_path,{'id':export['id'],'confirmed':True})
 w.intake(tmp_path,{'jobs':[listing(role_id='one',evidence='Official listing')]})
 # The fixture role retains its known application ID.
 import csv
 from job_app_system.adapters import JOB_FIELDS
 from job_app_system.io import write_csv
 write_csv(tmp_path/'data/jobs_seed.csv',[listing()],JOB_FIELDS)
 handoff=r.handoff(tmp_path,{'export_id':export['id'],'role_id':'one','job_url':'https://example.com/job'})
 assert handoff['application_only'] and handoff['preserve_saved_profile'] and handoff['stop_at_final_review']
 assert r.digest(master)==r.load(tmp_path)['master']['sha256']

def test_completed_search_queues_one_quiet_improvement_review(tmp_path):
 config(tmp_path)
 first=w.request(tmp_path,{'kind':'search'})
 w.request_result(tmp_path,{'id':first['id'],'status':'running'})
 w.request_result(tmp_path,{'id':first['id'],'status':'complete','result':'Retrieved and verified sources'})
 second=w.request(tmp_path,{'kind':'search'})
 w.request_result(tmp_path,{'id':second['id'],'status':'running'})
 w.request_result(tmp_path,{'id':second['id'],'status':'complete','result':'Checked again'})
 improvements=[x for x in w.read(tmp_path)['requests'] if x['kind']=='improve']
 assert len(improvements)==1 and improvements[0]['payload']['quiet'] is True
 assert w.read(tmp_path)['rules']==[]

def test_research_update_preserves_existing_application_role_id(tmp_path):
 import csv
 from job_app_system.adapters import JOB_FIELDS
 config(tmp_path);path=tmp_path/'data/jobs_seed.csv'
 row=listing(role_id='existing-history',posted_date='',workplace='hybrid',domain_tags='',seniority='')
 with path.open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=JOB_FIELDS);writer.writeheader();writer.writerow(row)
 result=w.intake(tmp_path,{'jobs':[listing(evidence='Official updated description')]})
 assert result['ids']==['existing-history']

def test_integration_cannot_be_verified_without_actual_passed_report(tmp_path):
 plugin=tmp_path/'plugin';(plugin/'.codex-plugin').mkdir(parents=True)
 (plugin/'.codex-plugin/plugin.json').write_text('{"name":"job-apply"}')
 for name in ['skills/job-apply/SKILL.md','skills/answer-memory/SKILL.md','scripts/job-apply-store.py','scripts/qa-replay.py']:
  p=plugin/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Fictional installed test helper')
 w.integration_check(tmp_path,{'plugin_root':str(plugin),'consent':True})
 with pytest.raises(ValueError,match='report'):
  w.integration_receipt(tmp_path,{'check':'local','run_id':'qa-run-20261012-12345678','evidence':'Claimed pass','final_action_taken':False})
 assert w.read(tmp_path)['integration']['local_verified'] is False

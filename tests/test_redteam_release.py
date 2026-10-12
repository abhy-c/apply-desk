"""Adversarial approval, destination and imported-document regression checks."""
import json,zipfile
from pathlib import Path
import pytest
from job_app_system import workspace as w,portable_resume as r
from test_workspace import fixture_master,listing,config
from job_app_system.adapters import JOB_FIELDS
from job_app_system.io import write_csv


def approved(tmp_path,text='Built annual planning forecasts.'):
 fixture_master(tmp_path)
 fact=r.fact(tmp_path,{'text':'Built forecasts for annual planning','confirmed':True})
 p=r.propose(tmp_path,{'role_id':'one','slot_id':'0','text':text,'reason':'Clarifies supported scope','fact_ids':[fact['id']]})
 r.review(tmp_path,{'id':p['id'],'revision':p['revision'],'decision':'approved'})
 return p,fact


def test_resume_cannot_be_redirected_to_a_different_job(tmp_path,monkeypatch):
 approved(tmp_path)
 monkeypatch.setattr(r,'render_word',lambda root,docx,pdf:Path(pdf).write_bytes(b'test PDF'))
 monkeypatch.setattr(r,'pdf_pages',lambda path:1)
 export=r.generate(tmp_path,{'role_id':'one','confirmed':True})
 r.visual_review(tmp_path,{'id':export['id'],'confirmed':True})
 write_csv(tmp_path/'data/jobs_seed.csv',[listing()],JOB_FIELDS)
 p={'export_id':export['id'],'role_id':'one','job_url':'https://example.com/another-employer'}
 with pytest.raises(ValueError,match='differs'):r.handoff(tmp_path,p)
 p['job_url']=''
 with pytest.raises(ValueError):r.handoff(tmp_path,p)
 p['job_url']=listing()['role_url']
 assert r.handoff(tmp_path,p)['job_url']==p['job_url']
 write_csv(tmp_path/'data/jobs_seed.csv',[listing(status='closed')],JOB_FIELDS)
 with pytest.raises(ValueError,match='open'):r.handoff(tmp_path,p)


def test_competing_wording_needs_explicit_withdrawal(tmp_path):
 first,fact=approved(tmp_path)
 second=r.propose(tmp_path,{'role_id':'one','slot_id':'0','text':'Built forecasts supporting annual planning.','reason':'Alternative exact wording','fact_ids':[fact['id']]})
 with pytest.raises(ValueError,match='already'):r.review(tmp_path,{'id':second['id'],'revision':second['revision'],'decision':'approved'})
 assert r.load(tmp_path)['proposals'][0]['status']=='approved'
 r.review(tmp_path,{'id':first['id'],'revision':first['revision'],'decision':'withdrawn'})
 r.review(tmp_path,{'id':second['id'],'revision':second['revision'],'decision':'approved'})
 assert [p['text'] for p in r.load(tmp_path)['proposals'] if p['status']=='approved']==[second['text']]


@pytest.mark.parametrize('value',['nan','inf','-inf'])
def test_numeric_rules_reject_non_finite_thresholds(tmp_path,value):
 with pytest.raises(ValueError,match='Numeric'):w.set_rule(tmp_path,{'field':'salary','label':'Salary','operator':'minimum','value':value,'mode':'required','confirmed':True})


def test_non_finite_listing_is_unknown_not_a_pass(tmp_path):
 config(tmp_path)
 w.set_rule(tmp_path,{'field':'salary','label':'Salary','operator':'minimum','value':'50000','mode':'required','confirmed':True})
 assert w.assess(tmp_path,listing(salary='inf'))['verification_state']=='needs_verification'


@pytest.mark.parametrize('relationship',['attachedTemplate','image','oleObject'])
def test_docx_remote_loads_rejected_before_word(tmp_path,relationship):
 master=fixture_master(tmp_path)
 with zipfile.ZipFile(master,'a') as z:
  z.writestr('word/_rels/document.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{relationship}" TargetMode="External" Target="https://example.com/track"/></Relationships>')
 with pytest.raises(ValueError,match='remote-loading'):r.read_docx(master)


def test_normal_contact_hyperlink_is_preserved(tmp_path):
 master=fixture_master(tmp_path)
 with zipfile.ZipFile(master,'a') as z:
  z.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" TargetMode="External" Target="https://example.com/profile"/></Relationships>')
 assert r.master_bullets(master)[0]['text']=='Built forecasts.'


def test_improvement_requires_exact_change(tmp_path):
 with pytest.raises(ValueError,match='exact'):w.improvement(tmp_path,{'kind':'rule','title':'Better fit','reason':'Feedback','evidence':'Two rejections','validation':'Compare results','undo':'Undo rule'})


def test_plugin_update_invalidates_verification_without_writing_on_read(tmp_path):
 plugin=tmp_path/'plugin';(plugin/'.codex-plugin').mkdir(parents=True)
 (plugin/'.codex-plugin/plugin.json').write_text('{"name":"job-apply"}')
 for name in ['skills/job-apply/SKILL.md','skills/answer-memory/SKILL.md','scripts/job-apply-store.py','scripts/qa-replay.py']:
  p=plugin/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Fictional helper')
 w.integration_check(tmp_path,{'plugin_root':str(plugin),'consent':True})
 s=w.read(tmp_path);s['integration']['local_verified']=True;w.save(tmp_path,s)
 (plugin/'scripts/qa-replay.py').write_text('Updated helper')
 before=(tmp_path/'data'/w.STORE).read_bytes()
 assert not w.status(tmp_path)['workspace']['integration']['local_verified']
 assert (tmp_path/'data'/w.STORE).read_bytes()==before
 with pytest.raises(ValueError,match='changed'):w.integration_receipt(tmp_path,{'check':'real','consent':True,'evidence':'Claimed test','final_action_taken':False})


def test_resume_readiness_reports_missing_dependencies(tmp_path,monkeypatch):
 fixture_master(tmp_path);r.fact(tmp_path,{'text':'Built forecasts','confirmed':True})
 monkeypatch.setattr(r,'renderer',lambda:'word-macos')
 monkeypatch.setattr(r,'deps',lambda:(_ for _ in ()).throw(ValueError('Missing')))
 assert 'Resume dependencies (install the resume extra)' in r.resume_status(tmp_path)['missing']


@pytest.mark.parametrize('part',['word/document.xml','word/header1.xml'])
def test_external_fields_in_body_or_header_are_blocked(tmp_path,part):
 master=fixture_master(tmp_path)
 # Create a fresh archive so duplicate-part rejection is not the reason for this failure.
 with zipfile.ZipFile(master) as z:members={name:z.read(name) for name in z.namelist()}
 members[part]=f'<w:document xmlns:w="{r.W}"><w:p><w:r><w:instrText>INCLUDE</w:instrText></w:r><w:r><w:instrText>TEXT "https://example.com/private"</w:instrText></w:r></w:p></w:document>'.encode()
 with zipfile.ZipFile(master,'w') as z:
  for name,data in members.items():z.writestr(name,data)
 with pytest.raises(ValueError,match='external-loading'):r.read_docx(master)


def test_embedded_payload_is_blocked(tmp_path):
 master=fixture_master(tmp_path)
 with zipfile.ZipFile(master,'a') as z:z.writestr('word/embeddings/oleObject1.bin',b'fictional embedded payload')
 with pytest.raises(ValueError,match='embedded'):r.read_docx(master)



def test_withdrawn_bullet_cannot_be_handed_off_in_old_export(tmp_path,monkeypatch):
 proposal,_=approved(tmp_path)
 monkeypatch.setattr(r,'render_word',lambda root,docx,pdf:Path(pdf).write_bytes(b'test PDF'))
 monkeypatch.setattr(r,'pdf_pages',lambda path:1)
 export=r.generate(tmp_path,{'role_id':'one','confirmed':True})
 r.visual_review(tmp_path,{'id':export['id'],'confirmed':True})
 write_csv(tmp_path/'data/jobs_seed.csv',[listing()],JOB_FIELDS)
 p={'export_id':export['id'],'role_id':'one','job_url':listing()['role_url']}
 assert r.handoff(tmp_path,p)['application_only']
 r.review(tmp_path,{'id':proposal['id'],'revision':proposal['revision'],'decision':'withdrawn'})
 with pytest.raises(ValueError,match='withdrawn'):r.handoff(tmp_path,p)

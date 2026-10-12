"""Private, origin-scoped browser preflights. No passwords, cookies or ATS API keys."""
from __future__ import annotations
import hashlib, json, platform, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .storage import transaction
from .validation import public_url
from . import workspace as w

VERSION='0.4.0'
FAMILIES=[{'id':x,'name':name,'note':note} for x,name,note in [
 ('linkedin','LinkedIn Easy Apply','Sign in yourself in the browser Codex will use.'),
 ('greenhouse','Greenhouse','Some forms need no account; embedded employer forms can differ.'),
 ('ashby','Ashby','Some forms need no account. Verify the resume field, not the autofill field.'),
 ('lever','Lever','Some forms need no account; inspect custom questions.'),
 ('rippling','Rippling','Resume parsing needs checking against your approved facts.'),
 ('workday','Workday','Accounts and logins can be separate for each employer.'),
 ('custom','Other employer portal','Manual guidance until the actual form and tooling are checked.')]]

def identify(url):
 host=urlsplit(public_url(url,required=True)).hostname
 if host in {'linkedin.com','www.linkedin.com'}:return 'linkedin'
 if host in {'boards.greenhouse.io','job-boards.greenhouse.io'}:return 'greenhouse'
 if host=='jobs.ashbyhq.com':return 'ashby'
 if host=='jobs.lever.co':return 'lever'
 if host=='rippling.com' or host.endswith('.rippling.com'):return 'rippling'
 if host.endswith('.myworkdayjobs.com'):return 'workday'
 return 'custom'

def add(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm this portal and browser choice')
 if set(p)-{'url','label','browser','confirmed'}:raise ValueError('Portal setup does not accept credentials or session data')
 url=public_url(p.get('url',''),required=True);parsed=urlsplit(url)
 # Only a public entry path is retained; no query/fragment or browser session material.
 entry=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''));origin=f'{parsed.scheme}://{parsed.netloc}'
 label=str(p.get('label','')).strip()
 if not label or len(label)>200:raise ValueError('Name this employer portal (up to 200 characters)')
 browser=p.get('browser','host')
 if not isinstance(browser,str) or browser not in {'host','chrome','iab'}:raise ValueError('Choose the host browser, Chrome or in-app browser')
 id=hashlib.sha256(entry.encode()).hexdigest()[:24]
 item={'id':id,'label':label,'entry_url':entry,'origin':origin,'family':identify(entry),'browser':browser,'status':'not_checked','revision':w.fingerprint({'entry':entry,'browser':browser}),'at':w.now()}
 with transaction(Path(root)/'data'):
  s=w.read(root);old=next((x for x in s.get('portals',[]) if x['id']==id),None)
  if old and old['revision']==item['revision'] and old.get('status')!='removed':return old
  s['portals']=[x for x in s.get('portals',[]) if x['id']!=id]+[item];w.save(root,s)
 return item

def receipt(root,p):
 allowed={'id','revision','observed_origin','browser','page','auth','uploads','final_action_taken','profile_read','resume_uploaded'}
 if set(p)-allowed:raise ValueError('Connection receipts accept only redacted check states')
 if p.get('final_action_taken') is not False or p.get('profile_read') is not False or p.get('resume_uploaded') is not False:raise ValueError('Preflight must not read profiles, upload resumes or submit')
 origin=public_url(p.get('observed_origin',''),required=True)
 parsed=urlsplit(origin)
 if parsed.path!='/' or parsed.query:raise ValueError('Record only the observed origin, not page contents')
 values={k:p.get(k,'unknown') for k in ('browser','page','auth','uploads')}
 choices={'browser':{'supported','missing','unknown'},'page':{'accessible','blocked','unknown'},'auth':{'signed_in','not_required','needs_login','unknown'},'uploads':{'supported','manual','unknown'}}
 if any(not isinstance(value,str) or value not in choices[k] for k,value in values.items()):raise ValueError('Invalid portal check state')
 with transaction(Path(root)/'data'):
  s=w.read(root);item=next((x for x in s.get('portals',[]) if x['id']==p.get('id') and x['status']!='removed'),None)
  if not item or item['revision']!=p.get('revision'):raise ValueError('Portal choice changed; check it again')
  if origin.rstrip('/')!=item['origin']:raise ValueError('The portal redirected to another origin; ask before adding that destination')
  checks={**values,'final_action_taken':False,'profile_read':False,'resume_uploaded':False}
  ready=values['browser']=='supported' and values['page']=='accessible' and values['uploads']=='supported' and values['auth'] in {'signed_in','not_required'}
  status='preflight_passed' if ready else 'needs_login' if values['auth']=='needs_login' else 'manual_step' if values['uploads']=='manual' else 'blocked'
  integration=w.status(root,s)['workspace'].get('integration',{})
  item.update(status=status,checks=checks,checked_at=w.now(),plugin_revision=integration.get('plugin_revision',''));w.save(root,s)
 return item

def remove(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm forgetting this portal check')
 with transaction(Path(root)/'data'):
  s=w.read(root);item=next((x for x in s.get('portals',[]) if x['id']==p.get('id')),None)
  if not item:raise ValueError('Unknown portal')
  item['status']='removed';item['checks']={};item['removed_at']=w.now();w.save(root,s)
 return {'removed':True,'browser_session_changed':False}

def state(root,s=None):
 s=s or w.read(root);items=[]
 for original in s.get('portals',[]):
  if original['status']=='removed':continue
  item=dict(original)
  if item.get('checked_at'):
   integration=s.get('integration',{})
   try:expired=datetime.fromisoformat(item['checked_at'])<datetime.now(timezone.utc)-timedelta(days=7)
   except (ValueError,TypeError):expired=True
   if expired or item.get('plugin_revision')!=integration.get('plugin_revision','') or integration.get('status','').startswith('Job Apply changed'):
    item['status']='recheck_needed'
  items.append(item)
 return {'families':FAMILIES,'items':items,'notice':'A preflight checks page access and browser capabilities only. Recheck login and the actual form before every application.'}

def doctor(root,p=None):
 """Safe to share: no paths, URLs, file contents, answers, labels or credentials."""
 from . import portable_resume as r
 p=p or {}
 if p:raise ValueError('Diagnostics accepts no personal inputs')
 try:r.deps();extras=True
 except ValueError:extras=False
 try:ready=w.status(root);readable=True
 except (ValueError,OSError,KeyError,TypeError):ready={'workspace':{},'search_ready':False,'resume_ready':False};readable=False
 integration=ready['workspace'].get('integration',{})
 return {'version':VERSION,'python':'.'.join(map(str,sys.version_info[:3])),'os':platform.system(),
  'python_supported':sys.version_info>=(3,11),'resume_dependencies':extras,'renderer':r.renderer() or 'unavailable',
  'workspace_readable':readable,'job_search_ready':ready['search_ready'],'resume_ready':ready['resume_ready'],
  'job_apply_local_check':bool(integration.get('local_verified')),'portal_count':len(state(root,ready['workspace'])['items']) if readable else 0,
  'automatic_submission':False,'telemetry':False,'browser_check':'Run a portal preflight in Codex; the backend cannot inspect your browser session.'}

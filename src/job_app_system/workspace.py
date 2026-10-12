"""User-owned setup, evidence-backed ranking and approval-only improvement history."""
from __future__ import annotations
import csv, hashlib, json, math, re, uuid
from datetime import date, datetime, timezone
from pathlib import Path
from .storage import transaction, atomic_json
from .validation import public_url

STORE = 'apply_desk_workspace.json'
CRITERIA = [
 ('location','Location','location'), ('workplace','Remote, hybrid or on-site','workplace'),
 ('freshness','Posting age','posted_date'), ('salary','Salary floor','salary'),
 ('authorization','Work authorization and sponsorship','authorization'),
 ('seniority','Seniority','seniority'), ('domain','Industry or domain','domain_tags'),
 ('company_size','Company size','employee_band'), ('connections','Connections','connections'),
 ('hiring_manager','Named hiring manager','hiring_manager'),
]

def now(): return datetime.now(timezone.utc).isoformat()
def fingerprint(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def read(root):
 p=Path(root)/'data'/STORE
 return json.loads(p.read_text()) if p.exists() else {'version':1,'setup':{},'rules':[], 'sources':[], 'assessments':{},'feedback':[], 'improvements':[], 'requests':[], 'history':[],'integration':{},'role_details':{}}
def save(root,s): atomic_json(Path(root)/'data'/STORE,s)
def terms(value): return [x.strip().lower() for x in re.split('[,;\n]',str(value)) if x.strip()]

def status(root,s=None):
 s=s or read(root); setup=s['setup']; missing=[]
 integration=s.get('integration',{})
 if integration.get('plugin_revision') and integration.get('plugin_root'):
  try:current=plugin_fingerprint(Path(integration['plugin_root']))
  except (OSError,ValueError):current=None
  if current!=integration['plugin_revision']:
   s={**s,'integration':{**integration,'local_verified':False,'real_site_verified':False,'status':'Job Apply changed; configure and check again'}}
 for key,label in [('focus','Role focus'),('titles','Confirmed related titles'),('locations','Location preferences')]:
  if not setup.get(key): missing.append(label)
 if not setup.get('sources_confirmed') or not s['sources']:missing.append('Reviewed source configuration')
 if not setup.get('ranking_confirmed'):missing.append('Ranking criteria review')
 from .portable_resume import resume_status
 resume=resume_status(root)
 return {'search_ready':not missing,'search_missing':missing,'resume_ready':not resume['missing'],
         'resume_missing':resume['missing'],'research':'thorough','scheduling_reminder':'Set up recurring searches later in Codex when you are ready.',
         'criteria':[{'id':a,'label':b,'field':c} for a,b,c in CRITERIA], 'workspace':s, 'resume':resume,
         'portals':__import__('job_app_system.portals',fromlist=['state']).state(root,s),
         'verification_queue':json.loads((Path(root)/'out/roles_needs_verification.json').read_text()) if (Path(root)/'out/roles_needs_verification.json').exists() else []}

def configure(root,p):
 with transaction(Path(root)/'data'):
  s=read(root)
  if p.get('expected_revision') and p['expected_revision']!=fingerprint(s['setup']):raise ValueError('Setup changed; refresh before saving')
  prior_titles=s['setup'].get('titles','')
  allowed={'focus','titles','excluded_titles','locations','sources_confirmed','ranking_confirmed','scheduling_reminded'}
  for key,value in p.items():
   if key not in allowed:continue
   if key in {'sources_confirmed','ranking_confirmed','scheduling_reminded'}:
    if not isinstance(value,bool):raise ValueError('Confirmation must be true or false')
   elif not isinstance(value,str) or len(value)>4000:raise ValueError('Invalid setup field')
   s['setup'][key]=value.strip() if isinstance(value,str) else value
  if prior_titles and 'titles' in p and p['titles']!=prior_titles:s['setup']['ranking_engine']='user'
  s['setup']['research']='thorough'
  save(root,s)
 return status(root,s)

def validate_rule(p):
 if p.get('mode') not in {'required','preferred','ignore'}:raise ValueError('Choose Required, Preferred or Ignore')
 field=str(p.get('field','')).strip();label=str(p.get('label','')).strip()
 if not field or not label:raise ValueError('Rule field and label are required')
 op=p.get('operator','contains')
 if op not in {'contains','excludes','minimum','maximum','qualitative'}:raise ValueError('Invalid rule operator')
 weight=int(p.get('weight',5))
 if not 1<=weight<=10:raise ValueError('Importance must be 1 to 10')
 value=str(p.get('value','')).strip()
 if p['mode']!='ignore' and not value:raise ValueError('Provide the criterion')
 if op in {'minimum','maximum'}:
  try:
   if not math.isfinite(float(value)):raise ValueError()
  except ValueError:raise ValueError('Numeric rule needs a number') from None
 return {'id':str(p.get('id') or uuid.uuid4().hex),'field':field[:100],'label':label[:200], 'operator':op,'value':value[:4000],'mode':p['mode'],'weight':weight}

def set_rule(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm the exact rule before applying')
 rule=validate_rule(p)
 with transaction(Path(root)/'data'):
  s=read(root);previous=next((r for r in s['rules'] if r['id']==rule['id']),None)
  s['history'].append({'id':uuid.uuid4().hex,'kind':'rule','rule_id':rule['id'],'before':previous,'after':rule,'engine_before':s['setup'].get('ranking_engine','user'),'at':now()})
  s['setup']['ranking_engine']='user'
  s['rules']=[r for r in s['rules'] if r['id']!=rule['id']]+[rule];save(root,s)
 return rule

def source(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm adding this source')
 method=p.get('method','manual')
 if method not in {'feed','codex','manual'}:raise ValueError('Invalid source method')
 item={'id':str(p.get('id') or uuid.uuid4().hex),'name':str(p.get('name','')).strip()[:200],
       'url':public_url(p.get('url','')),'method':method,'why':str(p.get('why',''))[:2000],
       'state':'untested','last_checked':'','usable':0,'matches':0,'error':''}
 if not item['name']:raise ValueError('Source name is required')
 with transaction(Path(root)/'data'):
  s=read(root);s['sources']=[x for x in s['sources'] if x['id']!=item['id']]+[item];save(root,s)
 return item

def source_result(root,p):
 with transaction(Path(root)/'data'):
  s=read(root);item=next((x for x in s['sources'] if x['id']==p.get('id')),None)
  if item is None:raise ValueError('Unknown source')
  state=p.get('state');usable=int(p.get('usable',0));matches=int(p.get('matches',0))
  if state not in {'working','blocked','failed'} or min(usable,matches)<0 or matches>usable:raise ValueError('Invalid source result')
  if not p.get('evidence') or not p.get('coverage'):raise ValueError('Record check evidence and coverage')
  item.update(state=state,usable=usable,matches=matches,last_checked=now(),error=str(p.get('error',''))[:2000], evidence=str(p['evidence'])[:4000],coverage=str(p['coverage'])[:4000]);save(root,s)
 return item

def title_matches(title,setup):
 title=str(title).lower()
 if any(x in title for x in terms(setup.get('excluded_titles',''))):return False
 titles=terms(setup.get('titles',''))
 return any(x in title for x in titles) if titles else False

def assess(root,row,s=None,today=None):
 s=s or read(root);today=today or date.today();score=0;reasons=[];missing=[];failed=[]
 row={**row,**s.get('role_details',{}).get(str(row.get('role_id','')),{})}
 setup=s['setup']
 if not title_matches(row.get('role_title',''),setup):failed.append('Outside confirmed role focus')
 if row.get('status','open')!='open':failed.append('Role is closed')
 prior=[x for x in s.get('feedback',[]) if x['role_id']==str(row.get('role_id',''))]
 if prior and prior[-1]['decision']=='reject':failed.append('Rejected by user: '+prior[-1].get('reason',''))
 # No hard-coded country, role family, seniority or freshness gates.
 for rule in s['rules']:
  if rule['mode']=='ignore':continue
  field=rule['field'];raw=row.get(field);op=rule['operator'];value=rule['value'];result=None;proof=''
  if field=='location' and not value:value=setup.get('locations','')
  if op=='qualitative':
   item=s['assessments'].get(str(row.get('role_id','')),{}).get(rule['id'],{})
   bound=fingerprint({'rule':rule,'role':row})
   if item.get('basis')==bound and item.get('evidence') and item.get('url') and item.get('result') in {'match','no_match'}:
    result=item['result']=='match';proof=item['evidence']
  elif raw not in (None,''):
   if op in {'contains','excludes'}:
    result=any(t in str(raw).lower() for t in terms(value));result=not result if op=='excludes' else result
    proof=str(raw)
   else:
    try:
     number=(today-date.fromisoformat(str(raw)[:10])).days if field=='posted_date' else float(raw)
     if not math.isfinite(number):raise ValueError('Non-finite listing value')
     if field=='posted_date' and number<0:result=False
     else:result=number>=float(value) if op=='minimum' else number<=float(value)
     proof=str(raw)
    except (ValueError,TypeError):pass
  if result is None:
   missing.append(rule['label'])
  elif result:
   score+=rule['weight']*10;reasons.append(rule['label']+': '+proof)
  elif rule['mode']=='required':failed.append(rule['label'])
 state='excluded' if failed else 'needs_verification' if any(r['label'] in missing and r['mode']=='required' for r in s['rules']) else 'ranked'
 return {'role_score':score,'role_tier':'High-fit apply first' if score>=70 else 'Review fit','role_score_reasons':'; '.join(reasons),
         'role_eligible':state=='ranked','verification_state':state,'verification_missing':missing,'excluded_reasons':failed,
         'role_age_days':'','freshness_bucket':'User-defined ranking'}

def role_record(root,role_id):
 """Resolve a role from imported records, preferring the latest Codex evidence."""
 stored=None
 for name in ('jobs_seed.csv','jobs_fetched.csv','jobs_discovered.csv','jobs_codex.csv'):
  path=Path(root)/'data'/name
  if path.exists():
   with path.open(newline='',encoding='utf-8-sig') as handle:
    candidate=next((x for x in csv.DictReader(handle) if x.get('role_id')==role_id),None)
    if candidate:stored=candidate
 return stored


def qualitative(root,p):
 from .io import read_jobs
 with transaction(Path(root)/'data'):
  s=read(root);rule=next((r for r in s['rules'] if r['id']==p.get('rule_id')),None)
  if not rule or rule['operator']!='qualitative':raise ValueError('Unknown qualitative rule')
  row=p.get('role')
  if not isinstance(row,dict) or row.get('role_id')!=p.get('role_id'):raise ValueError('Exact role evidence is required')
  stored=role_record(root,p['role_id'])
  if stored is None:raise ValueError('Import the job before assessing it')
  from .io import read_jobs
  row={k:stored.get(k,'') for k in ('role_id','role_title','company','role_url','source','posted_date','location','workplace','domain_tags','seniority','status','description')}
  row.update(s.get('role_details',{}).get(p['role_id'],{}))
  evidence=str(p.get('evidence',''))
  if not evidence.strip() or evidence not in str(row.get('description','')):raise ValueError('Cite exact listing text')
  if p.get('result') not in {'match','no_match','unknown'}:raise ValueError('Invalid assessment')
  item={'result':p['result'],'evidence':evidence,'url':public_url(p.get('url','')),'basis':fingerprint({'rule':rule,'role':row}),'at':now()}
  s['assessments'].setdefault(p['role_id'],{})[rule['id']]=item;save(root,s)
 return item

def feedback(root,p):
 if p.get('decision') not in {'accept','reject','verify'}:raise ValueError('Invalid feedback')
 item={'id':uuid.uuid4().hex,'role_id':str(p.get('role_id',''))[:200],'decision':p['decision'],'reason':str(p.get('reason',''))[:4000],'at':now()}
 with transaction(Path(root)/'data'):
  s=read(root);s['feedback'].append(item);save(root,s)
 return item

def improvement(root,p):
 if p.get('kind') not in {'rule','source','plugin','code'}:raise ValueError('Invalid improvement kind')
 if not all(p.get(k) for k in ['title','reason','evidence','validation','undo']):raise ValueError('Explain evidence, validation and undo')
 if not isinstance(p.get('change'),dict) or not p['change']:raise ValueError('Provide the exact proposed change')
 if p['kind']=='rule':validate_rule(p['change'])
 if p['kind']=='source':public_url(p['change'].get('url',''),required=True)
 item={k:p.get(k) for k in ['kind','title','reason','evidence','validation','undo','change','access','cost']}
 item.update(id=uuid.uuid4().hex,status='pending',at=now());item['revision']=fingerprint(item)
 with transaction(Path(root)/'data'):
  s=read(root);s['improvements'].append(item);save(root,s)
 return item

def review_improvement(root,p):
 with transaction(Path(root)/'data'):
  s=read(root);item=next((x for x in s['improvements'] if x['id']==p.get('id')),None)
  if not item or item['status']!='pending' or item['revision']!=p.get('revision') or fingerprint({k:v for k,v in item.items() if k!='revision'})!=item['revision']:raise ValueError('Proposal changed; review again')
  if p.get('decision') not in {'approved','rejected'}:raise ValueError('Choose approve or reject')
  if p['decision']=='approved' and item['kind']=='rule':
   change=validate_rule(item['change']);previous=next((r for r in s['rules'] if r['id']==change['id']),None)
   s['history'].append({'id':uuid.uuid4().hex,'kind':'rule','rule_id':change['id'],'before':previous,'after':change,'engine_before':s['setup'].get('ranking_engine','user'),'at':now()})
   s['setup']['ranking_engine']='user'
   s['rules']=[r for r in s['rules'] if r['id']!=change['id']]+[change]
  elif p['decision']=='approved' and item['kind']=='source':
   # Source addition is executed through the same validated consent boundary.
   change=dict(item['change']);change['confirmed']=True
   source(root,change);s=read(root);item=next(x for x in s['improvements'] if x['id']==p['id'])
  item.update(status=p['decision'],reviewed_at=now())
  if p['decision']=='approved' and item['kind'] in {'code','plugin'}:
   s['requests'].append({'id':uuid.uuid4().hex,'kind':'improve','status':'pending','at':now(),'role_id':'','payload':{'approved_improvement':item['id'],'revision':item['revision']}})
  save(root,s)
 return item

def undo(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm undo')
 with transaction(Path(root)/'data'):
  s=read(root);h=next((x for x in s['history'] if x['id']==p.get('id')),None)
  if not h or h.get('undone'):raise ValueError('Unknown or already undone change')
  current=next((x for x in s['rules'] if x['id']==h['rule_id']),None)
  if current!=h['after']:raise ValueError('A later edit exists; review that edit first')
  s['rules']=[x for x in s['rules'] if x['id']!=h['rule_id']]
  if h['before']:s['rules'].append(h['before'])
  h['undone']=now()
  if h.get('engine_before')=='legacy' and not any(not x.get('undone') for x in s['history']):s['setup']['ranking_engine']='legacy'
  save(root,s)
 return {'undone':True}

def request(root,p):
 kind=p.get('kind')
 if kind not in {'setup','search','resume','improve','job_apply_check','job_apply','portal_check'}:raise ValueError('Unknown Codex workflow')
 readiness=status(root)
 if kind=='search' and not readiness['search_ready']:raise ValueError('Complete job-search setup first')
 if kind=='resume' and not readiness['resume_ready']:raise ValueError('Complete resume setup first')
 if kind=='job_apply' and p.get('confirmed') is not True:raise ValueError('Confirm sharing this resume and job URL')
 with transaction(Path(root)/'data'):
  s=read(root)
  if kind=='portal_check':
   if p.get('confirmed') is not True:raise ValueError('Confirm opening this portal for a read-only preflight')
   portal=next((x for x in s.get('portals',[]) if x['id']==p.get('portal_id') and x['status']!='removed'),None)
   if not portal:raise ValueError('Choose a configured portal')
   p={'kind':kind,'portal_id':portal['id'],'portal_revision':portal['revision'],'confirmed':True}
  validated_handoff=None
  if kind=='job_apply':
   from .portable_resume import handoff
   validated_handoff=handoff(root,p)
  basis=fingerprint(p)
  prior=next((x for x in s['requests'] if x['kind']==kind and x['status'] in {'pending','running','waiting_user'} and x.get('request_basis')==basis),None)
  if prior:return request_prompt(root,prior)
  item={'id':uuid.uuid4().hex,'kind':kind,'status':'pending','at':now(),'role_id':str(p.get('role_id',''))[:200], 'payload':p,'request_basis':basis}
  if validated_handoff is not None:item['handoff']=validated_handoff
  s['requests'].append(item);save(root,s)
 return request_prompt(root,item)

def request_prompt(root,item):
 return {**item,'prompt':f'Use $apply-desk:apply-desk in workspace {Path(root).resolve()} to complete request {item["id"]}. Read its current state through python -m job_app_system.workspace_cli state. Honor cancellation and waiting_user; recheck before each external action. Never approve proposals or submit applications.'}

def request_cancel(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm cancelling this request')
 return request_result(root,{'id':p.get('id'),'status':'cancelled','result':'Cancelled by user; stop further work and keep existing files.'})

def request_resume(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm resuming this waiting request')
 with transaction(Path(root)/'data'):
  s=read(root);item=next((x for x in s['requests'] if x['id']==p.get('id')),None)
  if not item or item['status']!='waiting_user':raise ValueError('Only a request waiting for you can resume')
  item.update(status='pending',updated_at=now());save(root,s)
 return request_prompt(root,item)


def request_result(root,p):
 with transaction(Path(root)/'data'):
  s=read(root);item=next((x for x in s['requests'] if x['id']==p.get('id')),None)
  if not item:raise ValueError('Unknown request')
  transitions={'pending':{'running','failed','cancelled'},'running':{'waiting_user','complete','failed','cancelled'},'waiting_user':{'running','failed','cancelled'},'complete':set(),'failed':set(),'cancelled':set()}
  if p.get('status')==item['status']:return item
  if p.get('status') not in transitions.get(item['status'],set()):raise ValueError('Invalid request transition; terminal requests cannot restart')
  item.update(status=p['status'],result=str(p.get('result',''))[:10000],updated_at=now())
  if p['status']=='complete' and item['kind'] in {'search','resume'} and not any(x['kind']=='improve' and x['status']=='pending' for x in s['requests']):
   s['requests'].append({'id':uuid.uuid4().hex,'kind':'improve','status':'pending','at':now(),'role_id':item.get('role_id',''),'payload':{'after_request':item['id'],'quiet':True}})
  save(root,s)
 return item


def intake(root,p):
    """Codex imports verified listing evidence; generic intake has no role-family defaults."""
    from .adapters import JOB_FIELDS
    from .io import write_csv
    from .validation import job as validate_job
    records=p.get('jobs',[])
    if not isinstance(records,list) or len(records)>500:raise ValueError('Provide up to 500 job records')
    from .discovery_import import _canonical_url
    known={}
    for name in ('jobs_seed.csv','jobs_fetched.csv','jobs_discovered.csv','jobs_codex.csv'):
        path=Path(root)/'data'/name
        if path.exists():
            with path.open(newline='') as handle:
                for row in csv.DictReader(handle):
                    if row.get('role_url'):known[_canonical_url(row['role_url'])]=row['role_id']
    prepared=[]
    for record in records:
        if not isinstance(record,dict) or not record.get('evidence'):raise ValueError('Every listing needs source evidence')
        url=public_url(record.get('role_url',''))
        if not url:raise ValueError('Job URL is required')
        row=dict(record);row['role_url']=url;row['role_id']=known.get(_canonical_url(url)) or 'job:'+hashlib.sha256(_canonical_url(url).encode()).hexdigest()[:24]
        row['source']='codex:'+str(p.get('source_id','selected'))
        row=validate_job(row)
        if not row.get('description'):raise ValueError('Preserve full listing text')
        prepared.append((row,record))
    with transaction(Path(root)/'data'):
        s=read(root);path=Path(root)/'data/jobs_codex.csv'
        current={}
        if path.exists():
            with path.open(newline='') as f:current={x['role_id']:x for x in csv.DictReader(f)}
        for row,record in prepared:
            current[row['role_id']]=row
            s.setdefault('role_details',{})[row['role_id']]={k:record[k] for k in ('salary','authorization','connections','hiring_manager','employee_band','evidence','date_basis') if k in record}
        write_csv(path,current.values(),JOB_FIELDS);save(root,s)
    return {'imported':len(prepared),'ids':[x[0]['role_id'] for x in prepared]}


def plugin_fingerprint(plugin):
 required=['.codex-plugin/plugin.json','skills/job-apply/SKILL.md','skills/answer-memory/SKILL.md','scripts/job-apply-store.py','scripts/qa-replay.py']
 if any(not (plugin/x).is_file() for x in required):raise ValueError('Installed plugin lacks the isolated check capability')
 return fingerprint({x:hashlib.sha256((plugin/x).read_bytes()).hexdigest() for x in required})


def integration_check(root,p):
    """A local adapter check and a real-site check are separate evidence-bearing receipts."""
    if p.get('consent') is not True:raise ValueError('Confirm checking Job Apply')
    plugin=Path(str(p.get('plugin_root',''))).expanduser().resolve()
    manifest=plugin/'.codex-plugin/plugin.json'
    if not manifest.is_file() or json.loads(manifest.read_text()).get('name')!='job-apply':raise ValueError('Select the installed Job Apply plugin')
    revision=plugin_fingerprint(plugin)
    receipt={'plugin_root':str(plugin),'plugin_revision':revision,
             'status':'Installed; local pipeline check pending','at':now(),'local_verified':False,'real_site_verified':False}
    with transaction(Path(root)/'data'):
        s=read(root);s['integration']=receipt;save(root,s)
    return receipt


def integration_receipt(root,p):
    if p.get('check') not in {'local','real'} or not p.get('evidence'):raise ValueError('Record the actual check evidence')
    with transaction(Path(root)/'data'):
        s=read(root);item=s['integration']
        if not item.get('plugin_root'):raise ValueError('Check installed plugin first')
        if plugin_fingerprint(Path(item['plugin_root']))!=item['plugin_revision']:raise ValueError('Job Apply changed; configure and check again')
        if p.get('check')=='local':
            run_id=str(p.get('run_id',''))
            if not re.fullmatch(r'qa-run-[0-9]{8}-[0-9a-f]{8}',run_id):raise ValueError('Provide the actual isolated replay run ID')
            folder=Path(item['plugin_root'])/'qa/runs'/run_id
            report_path=folder/'report.json'
            if folder.is_symlink() or report_path.is_symlink() or not report_path.is_file():raise ValueError('Replay report is unavailable')
            report=json.loads(report_path.read_text())
            required={'final-action-untouched','history-started-reviewed','required-fields-filled','resume-filename-matched','resume-uploaded','review-reached','session-present','session-value-free'}
            if report.get('status')!='passed' or any(report.get('assertions',{}).get(key)!='passed' for key in required):raise ValueError('Isolated replay did not pass all required checks')
            p={**p,'evidence':{'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),'assertions':report['assertions'],'fixture':report.get('fixtureId'),'pipeline':p.get('pipeline',{})}}
        if p.get('check')=='real' and p.get('consent') is not True:raise ValueError('Confirm real application check')
        if p.get('final_action_taken') is not False:raise ValueError('Check must stop before submission')
        item[p['check']+'_verified']=True;item[p['check']+'_evidence']=p['evidence'];item[p['check']+'_checked_at']=now()
        item['status']='Local pipeline verified; real site check optional' if not item['real_site_verified'] else 'Local and selected real site verified'
        save(root,s)
    return item


def integration_choice(root,p):
    if p.get('choice') not in {'skip','existing','install'}:raise ValueError('Choose install, existing tools or skip')
    with transaction(Path(root)/'data'):
        s=read(root);s['integration']['choice']=p['choice'];s['integration']['choice_at']=now();save(root,s)
    return s['integration']

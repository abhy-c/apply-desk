"""Private user-selected masters, exact-language approvals and immutable DOCX formatting."""
from __future__ import annotations
import difflib, hashlib, json, os, platform, re, shutil, subprocess, tempfile, uuid, zipfile
from pathlib import Path
from .storage import transaction, atomic_json
from .workspace import fingerprint, now
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE='{http://www.w3.org/XML/1998/namespace}space'
STORE='resume_workspace.json'

def load(root):
 p=Path(root)/'data'/STORE
 return json.loads(p.read_text()) if p.exists() else {'master':{},'files':[],'facts':[],'proposals':[],'exports':[],'folder':''}
def save(root,s):atomic_json(Path(root)/'data'/STORE,s)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def deps():
 try:
  from lxml import etree
  from pypdf import PdfReader
  return etree,PdfReader
 except ImportError:raise ValueError('Resume generation requires lxml and pypdf. Install the resume extra.') from None

def renderer():
 if platform.system()=='Darwin' and Path('/Applications/Microsoft Word.app').exists():return 'word-macos'
 return ''

def pdf_pages(path):return len(deps()[1](str(path)).pages)

def resume_status(root):
 s=load(root);m=s['master'];missing=[]
 if not m:missing.append('Editable Word master')
 elif not Path(m['docx']).exists() or digest(m['docx'])!=m['sha256']:missing.append('Master changed; register and review it again')
 if not s['facts']:missing.append('Confirmed supporting facts')
 try:deps()
 except ValueError:missing.append('Resume dependencies (install the resume extra)')
 if not renderer():missing.append('Supported PDF renderer (Microsoft Word on macOS)')
 return {'missing':missing,'master':m,'renderer':renderer(),'facts':s['facts'],'proposals':s['proposals'],'exports':s['exports'],
         'reference_note':'A matching PDF is recommended; otherwise Word renders the master to establish its page count.'}

def validate_docx_package(archive):
 """Reject active/remote-loading parts before any native Word opening."""
 etree,_=deps();parser=etree.XMLParser(resolve_entities=False,no_network=True)
 if len(set(archive.namelist()))!=len(archive.namelist()):raise ValueError('Ambiguous duplicate DOCX parts')
 for name in archive.namelist():
  lowered=name.lower()
  if 'vbaproject' in lowered or lowered.startswith('word/embeddings/'):
   raise ValueError('Master contains active or embedded content; provide a clean Word master')
  if lowered.endswith('.rels'):
   tree=etree.fromstring(archive.read(name),parser)
   for relation in tree:
    if relation.get('TargetMode','').lower()=='external' and not relation.get('Type','').endswith('/hyperlink'):
     raise ValueError('Master contains a remote-loading relationship; provide a self-contained Word master')
  if re.fullmatch(r'word/(?:document|header[0-9]*|footer[0-9]*|footnotes|endnotes|comments)\.xml',lowered):
   tree=etree.fromstring(archive.read(name),parser)
   if tree.find('.//{'+W+'}altChunk') is not None:
    raise ValueError('Master contains imported active content; provide a clean Word master')
   instructions=[node.get('{'+W+'}instr','') for node in tree.iter()]
   instructions.extend(''.join(node.text or '' for node in paragraph.iter('{'+W+'}instrText')) for paragraph in tree.iter('{'+W+'}p'))
   if any(re.search(r'\b(?:DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|LINK)\b',instruction,re.I) for instruction in instructions):
    raise ValueError('Master contains an external-loading field; provide a self-contained Word master')


def read_docx(path):
 etree,_=deps()
 with zipfile.ZipFile(path) as z:
  if len(z.infolist())>1000 or sum(x.file_size for x in z.infolist())>50_000_000:raise ValueError('DOCX exceeds import limits')
  validate_docx_package(z)
  raw=z.read('word/document.xml')
 root=etree.fromstring(raw,etree.XMLParser(resolve_entities=False,no_network=True))
 return root,root.findall('.//{'+W+'}p')

def text(p):return ''.join(t.text or '' for t in p.iter('{'+W+'}t'))
def master_bullets(path):
 root,paragraphs=read_docx(path);out=[]
 for i,p in enumerate(paragraphs):
  value=text(p)
  style=p.find('{'+W+'}pPr/{'+W+'}pStyle')
  numbered=p.find('{'+W+'}pPr/{'+W+'}numPr') is not None
  if value.strip() and (numbered or (style is not None and 'list' in str(style.get('{'+W+'}val','')).lower())):
   out.append({'id':str(i),'text':value,'paragraph':i,'context':' / '.join(text(x) for x in paragraphs[max(0,i-3):i] if text(x).strip())})
 return out

def render_word(root,docx,pdf):
 if renderer()!='word-macos':raise ValueError('Supported Microsoft Word renderer is unavailable')
 script=Path(__file__).resolve().parent/'assets/export_word_pdf.applescript'
 if not script.exists():script=Path(root)/'scripts/export_word_pdf.applescript'
 # Launch Services opens only the selected file and grants Word its normal file access.
 # One private render folder avoids requesting access to a new output directory each time.
 work=Path(root)/'data/resume_sources';work.mkdir(parents=True,exist_ok=True,mode=0o700)
 token=uuid.uuid4().hex;working_docx=work/('word-render-'+token+'.docx');staging=work/('word-render-'+token+'.pdf')
 shutil.copyfile(docx,working_docx);working_docx.chmod(0o600)
 try:
  subprocess.run(['open','-a','Microsoft Word',str(working_docx.resolve())],check=True,capture_output=True,timeout=10)
  subprocess.run(['osascript',str(script),str(working_docx.resolve()),str(staging.resolve())],check=True,capture_output=True,timeout=45)
  if not staging.is_file():raise ValueError('Word did not create a PDF')
  staging.replace(pdf)
 except subprocess.TimeoutExpired:
  raise ValueError('Word export timed out. Resolve any Word access dialog for the private render folder, then retry. No verified PDF was produced.') from None
 except subprocess.CalledProcessError:
  raise ValueError('Word export failed. Check Word file access and Automation permission, then retry.') from None
 finally:
  working_docx.unlink(missing_ok=True)
  staging.unlink(missing_ok=True)


def register(root,p):
 if p.get('consent') is not True:raise ValueError('Confirm reading your selected master')
 source=Path(str(p.get('docx',''))).expanduser()
 if source.is_symlink() or not source.is_file() or source.suffix.lower()!='.docx':raise ValueError('Choose an editable Word master')
 if source.stat().st_size>20_000_000:raise ValueError('Master is too large')
 root=Path(root);private=root/'data/resume_sources';private.mkdir(parents=True,exist_ok=True,mode=0o700)
 sha=digest(source);target=private/(sha+'.docx')
 if not target.exists():shutil.copyfile(source,target);target.chmod(0o600)
 bullets=master_bullets(target)
 if not bullets:raise ValueError('No native bullet paragraphs found; ask Codex to map the master before continuing')
 reference=str(p.get('pdf','')).strip();ref=private/(sha+'.pdf')
 # Derive baseline from the actual Word master. A supplied PDF cannot override its page count.
 render_word(root,target,ref);pages=pdf_pages(ref)
 if reference:
  srcpdf=Path(reference).expanduser()
  if not srcpdf.is_file() or srcpdf.suffix.lower()!='.pdf':raise ValueError('Choose a matching PDF')
  if pdf_pages(srcpdf)!=pages:raise ValueError('Reference PDF page count differs from the Word master')
  shutil.copyfile(srcpdf,private/(sha+'.reference.pdf'))
 with transaction(root/'data'):
  s=load(root);s['master']={'docx':str(target.resolve()),'pdf':str(ref.resolve()),'sha256':sha,'pdf_sha256':digest(ref),'pages':pages,'bullets':bullets,'registered_at':now()}
  save(root,s)
 return resume_status(root)

def inventory(root,p):
 folder=Path(str(p.get('folder',''))).expanduser().resolve()
 if not folder.is_dir():raise ValueError('Choose a folder')
 entries=[]
 for path in sorted(folder.rglob('*')):
  if len(entries)>1000:raise ValueError('Folder has too many documents; choose a smaller folder')
  if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.docx','.pdf','.txt','.md'}:continue
  stat=path.stat();identity={'path':str(path),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
  entries.append({**identity,'id':fingerprint(identity)})
 # Inventory filenames and metadata only; no contents are read until selection.
 with transaction(Path(root)/'data'):
  s=load(root);s['folder']=str(folder);s['inventory']=entries;save(root,s)
 return entries

def import_files(root,p):
 if p.get('consent') is not True or not isinstance(p.get('ids'),list):raise ValueError('Confirm selected files')
 with transaction(Path(root)/'data'):
  s=load(root);items={x['id']:x for x in s.get('inventory',[])};prepared=[]
  for id in p['ids']:
   if id not in items:raise ValueError('Unknown file; scan again')
   item=items[id];path=Path(item['path']);stat=path.stat()
   if path.is_symlink() or stat.st_size!=item['size'] or stat.st_mtime_ns!=item['mtime_ns']:raise ValueError('File changed; review its new version')
   if stat.st_size>20_000_000:raise ValueError('Supporting file too large')
   sha=digest(path);target=Path(root)/'data/resume_sources'/(sha+path.suffix.lower());target.parent.mkdir(parents=True,exist_ok=True)
   if not target.exists():shutil.copyfile(path,target);target.chmod(0o600)
   if path.suffix.lower()=='.docx':content='\n'.join(text(x) for x in read_docx(target)[1])
   elif path.suffix.lower()=='.pdf':content='\n'.join(x.extract_text() or '' for x in deps()[1](str(target)).pages)
   else:content=target.read_text()
   prepared.append({'id':sha,'name':path.name,'path':str(target.resolve()),'sha256':sha,'text':content,'confirmed_at':now()})
  s['files']=[x for x in s['files'] if x['id'] not in {f['id'] for f in prepared}]+prepared;save(root,s)
 return {'imported':len(prepared)}

def fact(root,p):
 if p.get('confirmed') is not True or not str(p.get('text','')).strip():raise ValueError('Confirm the supporting fact')
 item={'id':uuid.uuid4().hex,'text':str(p['text'])[:10000],'context':str(p.get('context',''))[:1000],'at':now()}
 with transaction(Path(root)/'data'):
  s=load(root);s['facts'].append(item);save(root,s)
 return item

def diff(before,after):
 a=re.findall(r'\s+|\w+|[^\w\s]',before);b=re.findall(r'\s+|\w+|[^\w\s]',after);out=[]
 for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
  if op in {'replace','delete'}:out.append({'kind':'removed','text':''.join(a[i:j])})
  if op=='equal':out.append({'kind':'equal','text':''.join(b[k:l])})
  elif op in {'replace','insert'}:out.append({'kind':'added','text':''.join(b[k:l])})
 return out

def propose(root,p):
 with transaction(Path(root)/'data'):
  s=load(root);m=s['master'];slot=next((x for x in m.get('bullets',[]) if x['id']==str(p.get('slot_id'))),None)
  if not slot or digest(m['docx'])!=m['sha256']:raise ValueError('Unknown or changed master bullet')
  wording=str(p.get('text','')).strip();reason=str(p.get('reason','')).strip();role=str(p.get('role_id','')).strip()
  if not wording or wording==slot['text'] or not reason or not role:raise ValueError('Provide improved wording, role and explanation')
  if len(wording)>2000:raise ValueError('Bullet is too long')
  evidence_ids=p.get('fact_ids',[])
  evidence=[x for x in s['facts'] if x['id'] in evidence_ids]
  if len(evidence)!=len(set(evidence_ids)) or not evidence:raise ValueError('Use confirmed supporting facts')
  item={'id':uuid.uuid4().hex,'role_id':role,'slot_id':slot['id'],'original':slot['text'],'text':wording,'reason':reason,'facts':evidence,
        'master_sha256':m['sha256'],'destination_context':slot.get('context',''),'diff':diff(slot['text'],wording),'status':'pending','at':now()}
  item['revision']=fingerprint(item);s['proposals'].append(item);save(root,s)
 return item

def review(root,p):
 with transaction(Path(root)/'data'):
  s=load(root);item=next((x for x in s['proposals'] if x['id']==p.get('id')),None)
  if item and item['status']=='approved' and p.get('decision')=='withdrawn':
   body={k:v for k,v in item.items() if k not in {'revision','reviewed_at','approved_revision'}};body['status']='pending'
   if p.get('revision')!=item['approved_revision'] or fingerprint(body)!=item['approved_revision']:raise ValueError('Approved version changed; review again')
   item['status']='withdrawn';item['withdrawn_at']=now();save(root,s);return item
  if not item or item['status']!='pending' or p.get('revision')!=item['revision']:raise ValueError('Proposal changed; review again')
  body={k:v for k,v in item.items() if k!='revision'}
  if fingerprint(body)!=item['revision'] or item['master_sha256']!=s['master']['sha256']:raise ValueError('Evidence or master changed; review again')
  if p.get('decision') not in {'approved','rejected'}:raise ValueError('Approve or reject')
  if p['decision']=='approved' and any(x['id']!=item['id'] and x['status']=='approved' and x['role_id']==item['role_id'] and x['slot_id']==item['slot_id'] and x['master_sha256']==item['master_sha256'] for x in s['proposals']):
   raise ValueError('This bullet already has approved wording; explicitly replace it through a new reviewed version')
  item['status']=p['decision'];item['reviewed_at']=now();item['approved_revision']=item['revision'] if p['decision']=='approved' else ''
  save(root,s)
 return item

def patch(master,target,changes):
 etree,_=deps();root,paragraphs=read_docx(master)
 for slot_id,wording in changes.items():
  p=paragraphs[int(slot_id)];runs=p.findall('{'+W+'}r');nodes=list(p.iter('{'+W+'}t'))
  if not nodes or p.find('.//{'+W+'}hyperlink') is not None:raise ValueError('Complex bullet needs explicit formatting mapping')
  # Preserve every run, run property, hyperlink, paragraph property, table and package part.
  # Preserve token emphasis when equal; reject edits that span conflicting character formatting.
  signatures=[]
  for node in nodes:
   run=node.getparent();rpr=run.find('{'+W+'}rPr');signatures.append(etree.tostring(rpr) if rpr is not None else b'')
  if len(set(signatures))>1:raise ValueError('Mixed emphasis bullet requires a reviewed run mapping before generation')
  nodes[0].text=wording;nodes[0].set(XML_SPACE,'preserve')
  for node in nodes[1:]:node.text=''
 payload=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
 with zipfile.ZipFile(master) as src,zipfile.ZipFile(target,'w') as dst:
  for info in src.infolist():dst.writestr(info,payload if info.filename=='word/document.xml' else src.read(info.filename))
 # All non-text formatting and every other package member must be identical.
 before,_=read_docx(master);after,_=read_docx(target)
 for tree in (before,after):
  for n in tree.iter('{'+W+'}t'):n.text='';n.attrib.pop(XML_SPACE,None)
 if etree.tostring(before)!=etree.tostring(after):raise ValueError('Formatting integrity check failed')

def generate(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm generating both drafts')
 root=Path(root)
 with transaction(root/'data'):
  s=load(root);m=s['master'];role=str(p.get('role_id','')).strip()
  if not role or not m or digest(m['docx'])!=m['sha256']:raise ValueError('Select a role and unchanged master')
  if not s['facts']:raise ValueError('Confirm supporting facts first')
  proposals=[x for x in s['proposals'] if x['role_id']==role and x['master_sha256']==m['sha256']]
  if any(x['status']=='pending' for x in proposals):raise ValueError('Review pending changes before generation')
  changes={}
  for item in proposals:
   if item['status']=='approved':
    body={k:v for k,v in item.items() if k not in {'revision','reviewed_at','approved_revision'}};body['status']='pending'
    if fingerprint(body)!=item['approved_revision']:raise ValueError('Approved wording or evidence changed')
    if item['slot_id'] in changes:raise ValueError('Conflicting approved versions for one bullet; review them before generation')
    changes[item['slot_id']]=item['text']
  export_id=uuid.uuid4().hex;dest=root/'out/resumes'/export_id;dest.mkdir(parents=True,mode=0o700)
  stem=str(p.get('filename','resume'))
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',stem):raise ValueError('Invalid resume filename')
  docx=dest/(stem+'.docx');pdf=dest/(stem+'.pdf')
  if changes:patch(m['docx'],docx,changes)
  else:shutil.copyfile(m['docx'],docx)
  render_word(root,docx,pdf);pages=pdf_pages(pdf)
  if pages>m['pages']:
   shutil.rmtree(dest);raise ValueError('Resume exceeds master page count. Approve shorter wording; formatting stays locked.')
  item={'id':export_id,'role_id':role,'docx':str(docx.resolve()),'pdf':str(pdf.resolve()),'docx_sha256':digest(docx),'pdf_sha256':digest(pdf),
        'pages':pages,'master_sha256':m['sha256'],'proposals':[x['id'] for x in proposals if x['status']=='approved'],'at':now(),'visual_review':'pending'}
  s['exports'].append(item);save(root,s)
 return item

def visual_review(root,p):
 if p.get('confirmed') is not True:raise ValueError('Confirm visual inspection of every page against the master')
 with transaction(Path(root)/'data'):
  s=load(root);item=next((x for x in s['exports'] if x['id']==p.get('id')),None)
  if not item or digest(item['docx'])!=item['docx_sha256'] or digest(item['pdf'])!=item['pdf_sha256']:raise ValueError('Generated files changed')
  item['visual_review']='approved';item['visually_reviewed_at']=now();save(root,s)
 return item

def handoff(root,p):
 from .validation import public_url
 from .workspace import role_record
 s=load(root);item=next((x for x in s['exports'] if x['id']==p.get('export_id')),None)
 if not item or item['role_id']!=p.get('role_id') or item['visual_review']!='approved':raise ValueError('Select this role’s visually verified resume')
 if item['master_sha256']!=s['master'].get('sha256'):raise ValueError('Master version changed; generate and review again')
 approved_ids={x['id'] for x in s['proposals'] if x['status']=='approved'}
 if not set(item['proposals']).issubset(approved_ids):raise ValueError('Resume approval withdrawn; generate and review again')
 if digest(item['docx'])!=item['docx_sha256'] or digest(item['pdf'])!=item['pdf_sha256']:raise ValueError('Resume changed; generate and review again')
 role=role_record(root,item['role_id'])
 if not role or role.get('status','open')!='open':raise ValueError('Select a current open imported role')
 url=public_url(p.get('job_url',''),required=True)
 if url!=public_url(role.get('role_url',''),required=True):raise ValueError('Job URL differs from the selected role; review again')
 return {'resume_path':item['pdf'],'resume_sha256':item['pdf_sha256'],'job_url':url,'role_id':item['role_id'],
         'application_only':True,'preserve_saved_profile':True,'stop_at_final_review':True}

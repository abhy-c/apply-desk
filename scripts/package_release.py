"""Build a reproducible, source-only archive and a clean browser-upload folder.

Only the named schemas/assets, Python modules, tests, docs and scripts are included.
This command never copies data, outputs, credentials, Git history or build caches.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ASSETS=Path('src/job_app_system/assets')
ROOT_FILES=['README.md','LICENSE','AGENTS.md','.gitignore','pyproject.toml','requirements-dev-lock.txt']
SCHEMAS=['ats_sources.csv','companies.csv','contacts_seed.csv','jobs_seed.csv','target_companies.csv','discovery_sources.json']
PATTERNS=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',r'AKIA[0-9A-Z]{16}',r'AIza[0-9A-Za-z_-]{30,}',r'sk-[A-Za-z0-9_-]{25,}']

def release_files(root):
    paths=[Path(name) for name in ROOT_FILES]
    paths.extend(p.relative_to(root) for p in sorted((root/'src/job_app_system').glob('*.py')))
    paths.extend(p.relative_to(root) for p in sorted((root/'tests').glob('test_*.py')))
    paths.extend(p.relative_to(root) for p in sorted((root/'scripts').glob('*.py')))
    paths.extend([Path('.github/workflows/test.yml'),ASSETS/'web/index.html',ASSETS/'web/app.js',ASSETS/'web/app.css'])
    paths.extend(ASSETS/'examples'/name for name in SCHEMAS)
    result={}
    for path in sorted(paths):
        source=root/path
        if source.is_symlink() or not source.is_file(): raise ValueError(f'Invalid source file: {path}')
        content=source.read_bytes(); text=content.decode('utf-8')
        if any(re.search(pattern,text) for pattern in PATTERNS): raise ValueError(f'Credential pattern in {path}')
        if any('/'+name+'/' in text for name in ('Users','home')): raise ValueError(f'Personal absolute path in {path}')
        for email in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):
            if not email.endswith(('@example.com','@example.invalid','@users.noreply.github.com')): raise ValueError(f'Non-example email in {path}')
        if path.parent==ASSETS/'examples' and path.suffix=='.csv':
            if len(list(csv.reader(text.splitlines())))!=1: raise ValueError(f'Example contains data rows: {path}')
        result[path.as_posix()]=content
    return result


def build(root,output):
    content=release_files(root)
    version=tomllib.loads(content['pyproject.toml'].decode())['project']['version']
    manifest={'version':version,'files':[{'path':name,'sha256':hashlib.sha256(data).hexdigest()} for name,data in content.items()]}
    content['RELEASE_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output.mkdir(parents=True,exist_ok=True)
    upload=output/'github-upload'
    if upload.exists(): raise ValueError('Output upload folder already exists; choose a fresh output directory')
    upload.mkdir()
    archive=output/f'apply-desk-v{version}.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(content.items()):
            target=upload/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            info=zipfile.ZipInfo('apply-desk/'+name,date_time=(2000,1,1,0,0,0))
            info.create_system=3;info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    report={'version':version,'files':len(content),'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (output/'package-check.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'dist/public-release')
    args=parser.parse_args()
    print(json.dumps(build(ROOT,args.output),indent=2))

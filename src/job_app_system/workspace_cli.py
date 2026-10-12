"""Codex bridge: private JSON inputs, no API keys or embedded AI provider."""
import argparse,json
from pathlib import Path
from . import workspace as w, portable_resume as r, portals as c
ACTIONS={'doctor':c.doctor,'portal-add':c.add,'portal-receipt':c.receipt,'portal-remove':c.remove,'request-cancel':w.request_cancel,'request-resume':w.request_resume,'intake':w.intake,'integration-choice':w.integration_choice,'integration-check':w.integration_check,'integration-receipt':w.integration_receipt,'setup':w.configure,'rule':w.set_rule,'source':w.source,'source-result':w.source_result,
 'assessment':w.qualitative,'feedback':w.feedback,'improvement':w.improvement,'improvement-review':w.review_improvement,
 'undo':w.undo,'request':w.request,'request-result':w.request_result,
 'master':r.register,'inventory':r.inventory,'import-files':r.import_files,'fact':r.fact,
 'proposal':r.propose,'proposal-review':r.review,'generate':r.generate,'visual-review':r.visual_review}

def dispatch(root,action,payload):
 if action=='state':return w.status(root)
 if action=='resume-state':return r.load(root)
 if action not in ACTIONS:raise ValueError('Unknown workspace action')
 return ACTIONS[action](root,payload)

def main():
 parser=argparse.ArgumentParser(description='Apply Desk Codex workspace bridge')
 parser.add_argument('action',choices=['state','resume-state',*ACTIONS]);parser.add_argument('--workspace',type=Path,default=Path.cwd());parser.add_argument('--input',type=Path)
 args=parser.parse_args();payload=json.loads(args.input.read_text()) if args.input else {}
 if not isinstance(payload,dict):raise SystemExit('Input must be a JSON object')
 try:result=dispatch(args.workspace,args.action,payload)
 except (ValueError,OSError) as exc:raise SystemExit(str(exc)) from None
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

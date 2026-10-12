# Private workspace bridge

Use the workspace virtual environment's Python or a host-provided Python 3.11+ runtime. Check the version; do not assume the system python3 is recent enough. Install Apply Desk's Python package in the user's environment, or set PYTHONPATH to the confirmed code checkout's src directory when operating an existing local service. Never hard-code another owner's Python or workspace path. Run commands from their workspace or pass `--workspace` explicitly. Input is a private JSON file created with file tools, not shell interpolation:

```
python -m job_app_system.workspace_cli <action> --workspace <workspace> --input <private-json>
```

`state` returns setup, rules, sources, feedback, improvement proposals, requests and readiness. `resume-state` returns only the selected master, selected source snapshots, confirmed facts, bullet proposals and exports. Read personal contents only after their selection/consent. Delete temporary JSON inputs when no longer needed. Never print workspace codes or personal data into public reports.

Actions and key inputs:
- `setup`: focus, titles (comma-separated confirmed title phrases), excluded_titles, locations, sources_confirmed, ranking_confirmed. Preserve previous values; flags are true only after human review.
- `source`: name, url (public HTTPS), method (feed/codex/manual), why, confirmed. User approval required, one source at a time.
- `source-result`: id, state (working/blocked/failed), usable, matches, evidence, coverage, error. Record actual retrieved evidence, not inferred availability.
- `rule`: id when editing, label, field, operator (contains/excludes/minimum/maximum/qualitative), value, mode (required/preferred/ignore), weight 1–10, confirmed. Only run after human approval of that exact change.
- `intake`: source_id, jobs. Each job needs company, role_title, role_url, description (complete listing), location, workplace, posted_date (blank if unknown), status, evidence. Optional salary (numeric annual amount), authorization (verbatim), connections, hiring_manager, employee_band, domain_tags, seniority, date_basis. Preserve evidence; never invent missing metadata. It returns stable role IDs.
- `assessment`: role_id, rule_id, role (exact listing identity), result (match/no_match/unknown), evidence (exact quotation from stored description), url. Stale role or rule revisions invalidate the assessment.
- `feedback`: role_id, decision (accept/reject/verify), reason. This never edits a rule.
- `request-result`: id, status (running/waiting_user/complete/failed), result. Do not claim complete until required outputs exist.
- `improvement`: kind (rule/source/plugin/code), title, reason, evidence, validation, undo, change, access, cost. Remains pending for human review.
- `master`, `inventory`, `import-files`, `fact`, `proposal`, `generate`: see resume reference. `proposal-review`, `improvement-review`, `rule`, `undo`, and `visual-review` are human approval boundaries; never call them to impersonate approval.
- `integration-check`: plugin_root, consent. Reads installed plugin code and marks it installed, not tested.
- `integration-receipt`: check (local/real), evidence (actual replay/report), final_action_taken false, consent for real checks. Only record verified after observing the result.

After intake/assessments, run `python -m job_app_system.cli build` in the workspace. The main queue excludes failed required rules; missing required facts go to Needs verification. Role focus is an explicit title scope. All country/freshness/seniority preferences are user-owned rules.

Connection actions: portal-add (label, public url, browser host/chrome/iab, confirmed), portal-receipt (redacted fields in portals.md), portal-remove (id, confirmed), doctor (no inputs). Portal choices persist only reviewed public entry paths and browser choices; no session material. request-cancel and request-resume need id and human confirmed. Repeated active requests with the same payload reuse their existing ID; do not start parallel work on that ID. No automatic retry of external actions; inspect the actual current page and existing sessions before a human-authorized new attempt.

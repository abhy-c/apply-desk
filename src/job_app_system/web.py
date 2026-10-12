from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text, instance_lock

from uuid import uuid4
import secrets
import hmac
import threading
from http.cookies import SimpleCookie

import csv
import json
import mimetypes
import urllib.error
from datetime import date, datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .validation import job as validate_job, text, iso_date, public_url
from .initialization import initialize_workspace

from .adapters import JOB_FIELDS, fetch_enabled_ats_sources
from .application import (
    build_packet_with_saved_draft,
    export_application_packet,
    load_profile,
    read_application_reviews,
    save_application_packet,
    save_profile,
    slugify,
    upsert_application_review,
)
from .connections import (
    build_connection_rankings,
    connection_stats,
    linkedin_source_status,
    refresh_linkedin_export,
    save_connection_review,
)
from .companies import SPONSORSHIP_DISCLAIMER, build_target_company_rows
from .discovery_import import import_official_job_urls
from .manual_discovery import discovery_state
from .job_apply_link import read_job_apply_profile
from .pipeline import build
from .io import job_warnings
from .resume_customization import build_tailored_resume, rank_resume_plan, resume_templates
from .bullet_library import create_proposal, draft_inventory, import_selected_drafts, library_state, review_bullets, review_proposal
from .workflow import (
    ENRICHMENT_QUEUE_FIELDS,
    WEEKLY_QUEUE_FIELDS,
    build_enrichment_queue,
    build_weekly_queue,
    ensure_workflow_files,
)


APP_TITLE = "Apply Desk"
LEGALTECH_SPONSORSHIP_DISCLAIMER = (
    "Employer LCA history is not role-level sponsorship approval. Every opening remains verify-before-tailoring "
    "unless its own posting affirmatively states sponsorship support."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = Path(__file__).resolve().parent / "assets/web"
ATS_SOURCE_FIELDS = ["enabled", "company", "ats", "slug", "domain_tags", "location_hint"]
ACTION_FIELDS = [
    "action_id",
    "title",
    "company",
    "action_type",
    "priority",
    "due_date",
    "next_step",
    "notes",
    "status",
    "created_at",
    "updated_at",
]
SUPPORTED_ATS = {"ashby", "greenhouse", "lever"}


def serve(project_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {'127.0.0.1','localhost'}:
        raise ValueError('Apply Desk only supports a loopback listener')
    initialize_workspace(project_dir)
    _safe_build(project_dir / 'data', project_dir / 'out')
    build_connection_rankings(project_dir / 'data', project_dir / 'out')
    handler = _handler(project_dir.resolve())
    server = LocalServer(('127.0.0.1', port), handler)
    print(f"{APP_TITLE} running at http://{host}:{port}")
    print("Unlock with the private workspace code. In another terminal in this workspace, run: python -m job_app_system.cli unlock-code")
    server.serve_forever()


def _handler(project_dir: Path) -> type[BaseHTTPRequestHandler]:
    session = secrets.token_urlsafe(32)
    pairing_code = secrets.token_urlsafe(32)
    class ApplyDeskHandler(BaseHTTPRequestHandler):
        server_version = "ApplyDesk/0.2"
        data_directory=project_dir / 'data'

        @classmethod
        def prepare_workspace_code(cls):
            atomic_json(cls.data_directory / '.session-key',{'code':pairing_code})

        def do_GET(self) -> None:
            if not self._authorized(): return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._serve_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path.startswith("/assets/"):
                self._serve_file(WEB_ROOT / Path(parsed.path.removeprefix("/assets/")).name)
                return
            if parsed.path == "/api/state":
                try:
                    self._json(_state(project_dir, rebuild=False))
                except (ValueError, OSError, KeyError) as exc:
                    self._json({'error':'Workspace data could not be read; review the imported files.'}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/job-apply-profile":
                self._json({'connected':False,'message':'Local profile access is off. Use the profile button to read your details explicitly.'})
                return
            if parsed.path == "/api/health":
                self._json({"ok": True, "app": APP_TITLE})
                return
            if parsed.path == "/api/discovery-status":
                self._json(discovery_state(project_dir))
                return
            if parsed.path == "/api/cover-letter-file":
                from .application import slugify
                role_id = parse_qs(parsed.query).get("role_id", [""])[0]
                path = project_dir / "out/cover_letters" / (slugify(role_id) + ".pdf")
                if path.exists():
                    self._serve_file(path, "application/pdf")
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/resume-master":
                self._json({"error": "Resume templates are not included in the public preview."}, status=HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/resume-library":
                try:
                    self._json({"library": library_state(project_dir), "inventory": draft_inventory(project_dir)})
                except (ValueError, OSError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_HEAD(self) -> None:
            if not self._authorized(): return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._serve_file(WEB_ROOT / "index.html", "text/html; charset=utf-8", include_body=False)
                return
            if parsed.path.startswith("/assets/"):
                self._serve_file(WEB_ROOT / Path(parsed.path.removeprefix("/assets/")).name, include_body=False)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._authorized(write=True): return
            try:
                parsed = urlparse(self.path)
                payload = self._read_json()
                if parsed.path == '/api/session':
                    code=payload.get('code','')
                    if not isinstance(code,str) or not hmac.compare_digest(code,pairing_code):
                        self._json({'error':'Invalid workspace code'},status=HTTPStatus.FORBIDDEN)
                        return
                    self._bootstrap=True
                    self._json({'unlocked':True})
                    return
                if parsed.path == '/api/job-apply-profile':
                    if payload.get('consent') is not True: raise ValueError('Explicit profile access is required')
                    self._json(read_job_apply_profile())
                    return
                if parsed.path == "/api/resume-library/proposal":
                    self._json({"proposal": create_proposal(project_dir, payload)})
                    return
                if parsed.path == "/api/resume-library/proposal-review":
                    self._json({"library": review_proposal(project_dir, payload)})
                    return
                if parsed.path == "/api/resume-library/import":
                    file_ids = payload.get("file_ids", [])
                    if not isinstance(file_ids, list):
                        raise ValueError("file_ids must be a list of selected drafts")
                    self._json(import_selected_drafts(project_dir, file_ids))
                    return
                if parsed.path == "/api/resume-library/review":
                    updates = payload.get("updates", [])
                    if not isinstance(updates, list):
                        raise ValueError("updates must be a list")
                    self._json({"library": review_bullets(project_dir, updates)})
                    return
                if parsed.path == "/api/profile":
                    profile=save_profile(project_dir / 'data',payload)
                    _safe_build(project_dir / 'data',project_dir / 'out')
                    self._json({'profile':profile})
                    return
                if parsed.path == "/api/jobs":
                    self._json({"job": _append_job(project_dir / "data", payload), "state": _state(project_dir)})
                    return
                if parsed.path == "/api/ats-source":
                    row = _upsert_ats_source(project_dir / "data", payload)
                    self._json({"source": row, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/ats-source-delete":
                    removed = _delete_ats_source(project_dir / "data", str(payload.get("key", "")))
                    self._json({"removed": removed, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/fetch-ats":
                    count = fetch_enabled_ats_sources(
                        project_dir / "data" / "ats_sources.csv",
                        project_dir / "data" / "jobs_fetched.csv",
                    )
                    self._json({"fetched": count, "state": _state(project_dir, rebuild=True)})
                    return
                if parsed.path == "/api/discovery-import":
                    raw_urls = payload.get("urls", "")
                    if isinstance(raw_urls, list):
                        raw_urls = "\n".join(str(url) for url in raw_urls)
                    result = import_official_job_urls(project_dir / "data", str(raw_urls))
                    self._json({"import": result, "state": _state(project_dir, rebuild=True)})
                    return
                if parsed.path == "/api/linkedin-refresh":
                    counts = refresh_linkedin_export(project_dir)
                    build_connection_rankings(project_dir / "data", project_dir / "out")
                    self._json({"imported": counts, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/connection-review":
                    review = save_connection_review(project_dir / "data", payload)
                    build_connection_rankings(project_dir / "data", project_dir / "out")
                    self._json({"review": review, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/application-packet":
                    packet = _application_packet(project_dir, str(payload.get("role_id", "")))
                    self._json({"packet": packet})
                    return
                if parsed.path == "/api/cover-letter-export":
                    from .cover_letters import export_letter
                    # Resolve identity from the stored role; take only the edited letter from the request.
                    packet = _application_packet(project_dir, str(payload.get("role_id", "")))
                    packet["cover_letter"] = str(payload.get("cover_letter", packet["cover_letter"]))
                    self._json({"cover_letter": export_letter(project_dir, packet)})
                    return
                if parsed.path == "/api/application-packet/save":
                    packet = save_application_packet(project_dir / "data", payload)
                    self._json({"packet": packet, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/application-packet/export":
                    packet = save_application_packet(project_dir / "data", payload)
                    export = export_application_packet(project_dir / "out", packet)
                    packet["exported_at"] = export["exported_at"]
                    save_application_packet(project_dir / "data", packet)
                    self._json({"packet": packet, "export": export})
                    return
                if parsed.path == "/api/resume-plan":
                    role = _role(project_dir, str(payload.get("role_id", "")))
                    plan = rank_resume_plan(project_dir, role, str(payload.get("template_id", "pm")))
                    self._json({"plan": plan})
                    return
                if parsed.path == "/api/resume-export":
                    role = _role(project_dir, str(payload.get("role_id", "")))
                    replacements = payload.get("replacements", {})
                    selected_candidates = payload.get("selected_candidates", {})
                    if not isinstance(replacements, dict) or not isinstance(selected_candidates, dict):
                        raise ValueError("replacements and selected_candidates must be objects")
                    result = build_tailored_resume(
                        project_dir,
                        role,
                        str(payload.get("template_id", "pm")),
                        {str(key): str(value) for key, value in replacements.items()},
                        {str(key): str(value) for key, value in selected_candidates.items()},
                        export_pdf=str(payload.get("export_pdf", "true")).lower() not in {"0", "false", "no"},
                    )
                    self._json({"resume": result})
                    return
                if parsed.path == "/api/application-status":
                    row = upsert_application_review(
                        project_dir / "data",
                        role_id=str(payload.get("role_id", "")),
                        status=str(payload.get("status", "saved")),
                        decision=str(payload.get("decision", "")),
                        notes=str(payload.get("notes", "")),
                    )
                    self._json({"review": row, "state": _state(project_dir)})
                    return
                if parsed.path == "/api/action":
                    action = _upsert_action(project_dir / "data", payload)
                    self._json({"action": action, "state": _state(project_dir, rebuild=False)})
                    return
                if parsed.path == "/api/rebuild":
                    self._json({"state": _state(project_dir, rebuild=True)})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except RequestError as exc:
                self._json({'error':str(exc)}, status=exc.status)
            except (json.JSONDecodeError, ValueError, UnicodeError) as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._json({"error": f"Operation failed: {exc}"}, status=HTTPStatus.BAD_GATEWAY)

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def end_headers(self):
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if getattr(self,'_bootstrap',False):
                self.send_header('Set-Cookie',f'applydesk_session={session}; HttpOnly; SameSite=Strict; Path=/')
                self._bootstrap=False
            super().end_headers()

        def _authorized(self, write=False):
            port=self.server.server_address[1]
            host=self.headers.get('Host','')
            allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
            if host not in allowed:
                self._json({'error':'Invalid local Host'},status=HTTPStatus.FORBIDDEN); return False
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+host:
                self._json({'error':'Cross-origin requests are forbidden'},status=HTTPStatus.FORBIDDEN); return False
            path=urlparse(self.path).path
            if path=='/' or path.startswith('/assets/'):
                # Public bootstrap/assets contain no applicant data; framing is blocked by CSP.
                return True
            if self.headers.get('Sec-Fetch-Site')=='cross-site':
                self._json({'error':'Cross-site requests are forbidden'},status=HTTPStatus.FORBIDDEN); return False
            if write and path=='/api/session':
                if origin!='http://'+host or self.headers.get('X-Apply-Desk-Request')!='1':
                    self._json({'error':'A same-origin request is required'},status=HTTPStatus.FORBIDDEN); return False
                if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                    self._json({'error':'JSON content type is required'},status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE); return False
                return True
            try:
                cookies=SimpleCookie(self.headers.get('Cookie',''))
                cookie=cookies.get('applydesk_session')
                valid=cookie is not None and hmac.compare_digest(cookie.value,session)
            except Exception: valid=False
            if not valid:
                self._json({'error':'Open the local dashboard to establish a session'},status=HTTPStatus.UNAUTHORIZED); return False
            if write:
                if origin!='http://'+host or self.headers.get('X-Apply-Desk-Request')!='1':
                    self._json({'error':'A same-origin dashboard request is required'},status=HTTPStatus.FORBIDDEN); return False
                if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                    self._json({'error':'JSON content type is required'},status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE); return False
            return True

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, object]:
            if self.headers.get('Transfer-Encoding'): raise RequestError('Unsupported request transfer encoding',HTTPStatus.BAD_REQUEST)
            try: length=int(self.headers.get('Content-Length','0'))
            except ValueError: raise ValueError('Invalid content length')
            if length<=0: raise ValueError('A JSON object is required')
            if length>1000000: raise RequestError('Request is too large',HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            raw=self.rfile.read(length)
            if len(raw)!=length: raise ValueError('Incomplete request body')
            payload=json.loads(raw.decode('utf-8'))
            if not isinstance(payload,dict): raise ValueError('A JSON object is required')
            return payload

        def _json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _serve_file(self, path: Path, content_type: str | None = None, include_body: bool = True) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            encoded = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "text/plain")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if include_body:
                self.wfile.write(encoded)

    return ApplyDeskHandler


@transactional('project_dir', 'project')
def _state(project_dir: Path, rebuild: bool = True) -> dict[str, object]:
    data_dir = project_dir / "data"
    out_dir = project_dir / "out"
    if rebuild:
        ensure_workflow_files(data_dir)
        _safe_build(data_dir, out_dir)
        build_connection_rankings(data_dir, out_dir)

    roles = _read_rows(out_dir / "roles_scored.csv")
    contacts = _read_rows(out_dir / "contacts_scored.csv")
    weekly_queue = _read_rows(out_dir / "weekly_queue.csv")
    application_reviews = read_application_reviews(data_dir)
    actions = _actions(data_dir)
    profile = load_profile(data_dir)
    ats_sources = _ats_sources(data_dir)
    discovery_sources = _discovery_sources(data_dir)
    fetched_jobs = _read_rows(data_dir / "jobs_fetched.csv")
    legaltech_roles = _read_rows(data_dir / "legaltech_roles.csv")
    connections_ranked = _read_rows(out_dir / "connections_ranked.csv")
    network_stats = connection_stats(connections_ranked)
    target_companies, company_stats = build_target_company_rows(
        data_dir,
        out_dir,
        connections_ranked,
        roles,
        ats_sources,
    )

    roles = [_merge_review(row, application_reviews) for row in roles]
    high_fit_roles = [row for row in roles if row.get("role_tier") == "High-fit apply first"]
    applied_roles = [row for row in roles if row.get("application_status") == "applied"]
    needs_review = [row for row in roles if row.get("application_status") in {"", "saved", "ready_to_apply"}]
    open_actions = [row for row in actions if row.get("status") != "done"]
    due_actions = [row for row in open_actions if _is_due(row.get("due_date", ""))]
    feed = _feed_status(data_dir)

    return {
        "profile": profile,
        "validation_warnings": job_warnings(data_dir),
        "stats": {
            "roles": len(roles),
            "high_fit": len(high_fit_roles),
            "contacts": len(contacts),
            "weekly_queue": len(weekly_queue),
            "applied": len(applied_roles),
            "needs_review": len(needs_review),
            "ats_sources": len(ats_sources),
            "ats_enabled": len([row for row in ats_sources if row.get("enabled") == "true"]),
            "discovery_sources": len(discovery_sources),
            "source_count": len(ats_sources) + len(discovery_sources),
            "fetched_roles": len(fetched_jobs),
            "open_actions": len(open_actions),
            "due_actions": len(due_actions),
        },
        "roles": roles[:80],
        "contacts": contacts[:40],
        "weekly_queue": weekly_queue[:20],
        "connections_ranked": connections_ranked,
        "network_stats": network_stats,
        "target_companies": target_companies,
        "company_stats": company_stats,
        "sponsorship_disclaimer": SPONSORSHIP_DISCLAIMER,
        "legaltech_roles": legaltech_roles,
        "legaltech_stats": _legaltech_stats(legaltech_roles),
        "legaltech_sponsorship_disclaimer": LEGALTECH_SPONSORSHIP_DISCLAIMER,
        "linkedin_source": linkedin_source_status(project_dir),
        "application_reviews": application_reviews,
        "actions": actions,
        "focus": {
            "feed": feed,
            "roles": _focus_roles(roles),
            "outreach": weekly_queue[:5],
        },
        "ats_sources": ats_sources,
        "discovery_sources": discovery_sources,
        "discovery_status": discovery_state(project_dir),
        "resume_templates": resume_templates(project_dir),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _legaltech_stats(roles: list[dict[str, str]]) -> dict[str, int]:
    return {
        "total": len(roles),
        "priority": sum(row.get("fit_tier") == "Priority" for row in roles),
        "fresh_week": sum(int(row.get("role_age_days", "99") or 99) <= 7 for row in roles),
        "sponsor_evidence": sum(
            row.get("sponsorship_status") in {"role_confirmed", "employer_history"} for row in roles
        ),
    }


@transactional('data_dir', 'data')
def _safe_build(data_dir: Path, out_dir: Path) -> None:
    counts = build(data_dir, out_dir)
    if counts["contacts"]:
        build_enrichment_queue(data_dir, out_dir)
        build_weekly_queue(data_dir, out_dir)
    else:
        _write_rows(out_dir / "fullenrich_queue.csv", [], ENRICHMENT_QUEUE_FIELDS)
        _write_rows(out_dir / "weekly_queue.csv", [], WEEKLY_QUEUE_FIELDS)


@transactional('data_dir', 'data')
def _append_job(data_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "jobs_seed.csv"
    existing = _read_rows(path)
    company = str(payload.get("company", "")).strip()
    role_title = str(payload.get("role_title", "")).strip()
    if not company or not role_title:
        raise ValueError("company and role_title are required")

    row = {
        "role_id": f"manual_{uuid4().hex}",
        "company": company,
        "role_title": role_title,
        "role_url": str(payload.get("role_url", "")).strip(),
        "source": str(payload.get("source", "manual")).strip() or "manual",
        "posted_date": str(payload.get("posted_date", date.today().isoformat())).strip(),
        "location": str(payload.get("location", "")).strip(),
        "workplace": str(payload.get("workplace", "")).strip().lower(),
        "domain_tags": str(payload.get("domain_tags", "")).strip(),
        "seniority": str(payload.get("seniority", "PM")).strip() or "PM",
        "status": str(payload.get("status", "open")).strip().lower() or "open",
        "description": str(payload.get("description", "")).strip(),
    }
    row = validate_job(row)
    _write_rows(path, [*existing, row], JOB_FIELDS)
    return row


def _actions(data_dir: Path) -> list[dict[str, str]]:
    path = data_dir / "actions.csv"
    if not path.exists():
        return []
    return sorted(_read_rows(path), key=_action_sort_key)


@transactional('data_dir', 'data')
def _upsert_action(data_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("action title is required")

    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "actions.csv"
    existing = _actions(data_dir)
    now = datetime.now(timezone.utc).isoformat()
    action_id = str(payload.get("action_id", "")).strip() or f"action_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    previous = next((row for row in existing if row.get("action_id") == action_id), {})
    action = {
        "action_id": action_id,
        "title": title,
        "company": str(payload.get("company", "")).strip(),
        "action_type": str(payload.get("action_type", "relationship")).strip() or "relationship",
        "priority": str(payload.get("priority", "normal")).strip() or "normal",
        "due_date": str(payload.get("due_date", "")).strip(),
        "next_step": str(payload.get("next_step", "")).strip(),
        "notes": str(payload.get("notes", "")).strip(),
        "status": str(payload.get("status", previous.get("status", "open"))).strip() or "open",
        "created_at": previous.get("created_at", now),
        "updated_at": now,
    }
    action['title']=text(action['title'],'title',1000,True)
    action['due_date']=iso_date(action['due_date'],'due_date')
    if action['priority'] not in {'high','normal','low'}: raise ValueError('Invalid priority')
    if action['status'] not in {'open','done'}: raise ValueError('Invalid action status')
    for key in ('company','next_step','notes'): action[key]=text(action[key],key,10000)
    rows = [row for row in existing if row.get("action_id") != action_id]
    rows.append(action)
    rows.sort(key=_action_sort_key)
    _write_rows(path, rows, ACTION_FIELDS)
    return action


def _action_sort_key(row: dict[str, str]) -> tuple[int, int, str, str]:
    status = 1 if row.get("status") == "done" else 0
    priority = {"high": 0, "normal": 1, "low": 2}.get(row.get("priority", "normal"), 1)
    due = row.get("due_date", "") or "9999-12-31"
    return (status, priority, due, row.get("title", "").lower())


def _is_due(value: str) -> bool:
    if not value:
        return False
    try:
        return date.fromisoformat(value[:10]) <= date.today()
    except ValueError:
        return False


def _feed_status(data_dir: Path) -> dict[str, object]:
    path = data_dir / "jobs_fetched.csv"
    if not path.exists() or not path.stat().st_size:
        return {"state": "empty", "message": "No fetched role snapshot yet."}
    updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    age_days = (date.today() - updated.date()).days
    if age_days > 1:
        return {
            "state": "stale",
            "message": f"Role feed is {age_days} days old. Refresh sources before prioritizing applications.",
            "updated_at": updated.isoformat(),
        }
    return {"state": "current", "message": "Role feed is current.", "updated_at": updated.isoformat()}


def _focus_roles(roles: list[dict[str, str]], limit: int = 5, per_company_limit: int = 2) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    company_counts: dict[str, int] = {}
    for role in roles:
        if role.get("application_status") not in {"", "saved", "ready_to_apply"}:
            continue
        company = role.get("company", "").strip().lower()
        if company_counts.get(company, 0) >= per_company_limit:
            continue
        selected.append(role)
        company_counts[company] = company_counts.get(company, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _application_packet(project_dir: Path, role_id: str) -> dict[str, object]:
    role = _role(project_dir, role_id)
    return build_packet_with_saved_draft(project_dir / "data", load_profile(project_dir / "data"), role)


def _role(project_dir: Path, role_id: str) -> dict[str, str]:
    if not role_id:
        raise ValueError("role_id is required")
    _safe_build(project_dir / "data", project_dir / "out")
    roles = _read_rows(project_dir / "out" / "roles_scored.csv")
    role = next((row for row in roles if row.get("role_id") == role_id), None)
    if not role:
        raise ValueError(f"Unknown role_id: {role_id}")
    return role


def _ats_sources(data_dir: Path) -> list[dict[str, str]]:
    rows = _read_rows(data_dir / "ats_sources.csv")
    return [_source_with_key(row) for row in rows]


def _discovery_sources(data_dir: Path) -> list[dict[str, object]]:
    path = data_dir / "discovery_sources.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("discovery_sources.json must contain a list")
    return [row for row in payload if isinstance(row, dict)]


@transactional('data_dir', 'data')
def _upsert_ats_source(data_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "ats_sources.csv"
    rows = _read_rows(path)
    row = _normalize_ats_source(payload)
    row_key = _source_key(row)
    original_key = str(payload.get("original_key", payload.get("key", ""))).strip()
    if not row_key:
        raise ValueError("ats and slug are required")

    updated: list[dict[str, str]] = []
    replaced = False
    for existing in rows:
        existing_key = _source_key(existing)
        if existing_key == original_key or existing_key == row_key:
            if not replaced:
                updated.append(row)
                replaced = True
            continue
        updated.append(existing)
    if not replaced:
        updated.append(row)

    updated.sort(key=lambda item: (item.get("enabled", "") != "true", item.get("company", "").lower()))
    _write_rows(path, updated, ATS_SOURCE_FIELDS)
    return _source_with_key(row)


@transactional('data_dir', 'data')
def _delete_ats_source(data_dir: Path, key: str) -> bool:
    path = data_dir / "ats_sources.csv"
    rows = _read_rows(path)
    kept = [row for row in rows if _source_key(row) != key]
    _write_rows(path, kept, ATS_SOURCE_FIELDS)
    return len(kept) != len(rows)


def _normalize_ats_source(payload: dict[str, object]) -> dict[str, str]:
    ats = str(payload.get("ats", "")).strip().lower()
    if ats not in SUPPORTED_ATS:
        raise ValueError(f"ats must be one of: {', '.join(sorted(SUPPORTED_ATS))}")
    company = str(payload.get("company", "")).strip()
    slug = str(payload.get("slug", "")).strip()
    if not company or not slug:
        raise ValueError("company and slug are required")
    enabled_value = payload.get("enabled", "")
    enabled = "true" if str(enabled_value).strip().lower() in {"1", "true", "yes", "on"} else "false"
    return {
        "enabled": enabled,
        "company": company,
        "ats": ats,
        "slug": slug,
        "domain_tags": str(payload.get("domain_tags", "")).strip(),
        "location_hint": str(payload.get("location_hint", "")).strip(),
    }


def _source_with_key(row: dict[str, str]) -> dict[str, str]:
    normalized = {field: row.get(field, "") for field in ATS_SOURCE_FIELDS}
    normalized["enabled"] = "true" if normalized.get("enabled", "").strip().lower() in {"1", "true", "yes"} else "false"
    normalized["key"] = _source_key(normalized)
    return normalized


def _source_key(row: dict[str, str]) -> str:
    ats = row.get("ats", "").strip().lower()
    slug = row.get("slug", "").strip().lower()
    return f"{ats}:{slug}" if ats and slug else ""


def _merge_review(row: dict[str, str], reviews: dict[str, dict[str, str]]) -> dict[str, str]:
    review = reviews.get(row.get("role_id", ""), {})
    merged = dict(row)
    merged["application_status"] = review.get("status", "")
    merged["application_decision"] = review.get("decision", "")
    merged["application_notes"] = review.get("notes", "")
    return merged


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    atomic_csv(path, rows, fieldnames, spreadsheet_safe=path.name in {'connections_ranked.csv','weekly_queue.csv','fullenrich_queue.csv'})


class RequestError(ValueError):
    def __init__(self,message,status):
        super().__init__(message); self.status=status

class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self._workers=threading.BoundedSemaphore(16)
        self._lease=None
        super().__init__(*args,**kwargs)
        lease=instance_lock(self.RequestHandlerClass.data_directory)
        try:
            lease.__enter__()
            self._lease=lease
            self.RequestHandlerClass.prepare_workspace_code()
        except BaseException:
            self.server_close(); raise
    def server_close(self):
        super().server_close()
        if self._lease is not None:
            self._lease.__exit__(None,None,None)
            self._lease=None
    def process_request(self,request,client_address):
        if not self._workers.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request,client_address)
        except BaseException:
            self._workers.release(); raise
    def process_request_thread(self,request,client_address):
        try: super().process_request_thread(request,client_address)
        finally: self._workers.release()

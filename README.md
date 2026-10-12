# Apply Desk

A local workspace for keeping a job search moving: find roles, review fit, prepare application notes, track decisions, and follow up with people in one place.

Apply Desk runs on your computer. Your profile, contacts, application drafts, and exports stay in local files. The dashboard works without an AI API key or a Codex subscription.

**This is an early public preview.** It includes the dashboard and sourcing workflow. The original app's personal resume templates, bullet library, and formatted Word/PDF exports are excluded. Bring your own resume and submit applications manually.

## What you can do

- Review a ranked queue of fresh US product roles.
- Add jobs manually or import official employer posting URLs.
- Configure Ashby, Greenhouse, and Lever sources, then refresh them on demand.
- Track application status, next steps, and follow-up actions.
- Edit application notes and screening answers, then export a Markdown packet.
- Import your own LinkedIn data-export ZIP locally to review connections. The app never logs in to LinkedIn or sends messages.
- Browse a directory of job boards. Directory links are manual discovery sources, not working automated collectors.

## Download and run

Install Python 3.11 or newer. Download this repository with **Code → Download ZIP**, extract it, and open a terminal in the extracted folder. Or clone it:

```bash
git clone https://github.com/abhy-c/apply-desk.git
cd apply-desk
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m job_app_system.cli init
python -m job_app_system.cli serve --port 8767
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m job_app_system.cli init
python -m job_app_system.cli serve --port 8767
```

Open [Apply Desk on localhost](http://127.0.0.1:8767). In a second terminal, activate the same environment, change into your workspace folder, and run:

```bash
python -m job_app_system.cli unlock-code
```

Paste that private code into **Unlock your local workspace**. It changes when the server restarts. Keep it private. Keep the server running while using the dashboard. Press Ctrl+C in the terminal to stop it. If that port is already in use, choose another with `--port`.

Dashboard assets and empty schemas are bundled in the Python package. Both editable source installs and normal wheel installs work. Run `init` and `serve` from the folder where you want your private workspace data. The public runtime uses only Python’s standard library; no runtime dependencies or AI API keys are required. A desktop installer and hosted multi-user service are not provided.

## First use

1. Open **Profile** and enter your name, preferences, and factual application answers.
2. Use **Add role** to enter a real posting with its publication date and US location.
3. Open **Sources** to add a company's ATS type and slug. Enable it, then refresh. For example, the slug is the last company segment in `jobs.lever.co/companyname`.
4. Open a role in **Roles** to edit application notes, save a draft, export a packet, or update its status.
5. Add follow-up tasks in **Focus**.

Start with an empty workspace. The `init` command copies header-only CSVs and the public discovery directory from the bundled package assets into your ignored `data/` folder. Running setup again preserves existing files.

## Current limits

The ATS collectors currently retrieve product roles. The scorer uses your saved target titles, preferred locations, domain tags, and excluded title keywords. Use commas for titles/domains and semicolons for locations, for example `Austin, TX; United States remote`. Matching is based on explicit text and domain tags, not an AI interpretation of your experience. Open, confirmed-US roles published within 21 days are eligible; undated, older, and future-dated roles are excluded. Saving your profile rebuilds scores. Location/domain preferences adjust ranking; excluded title keywords make matching roles ineligible. The US location and 21-day freshness gates still apply.

Official URL intake uses stricter gates: a supported structured `JobPosting`, confirmed US location, publication within 14 days, and no explicit exclusion of sponsorship. Some employer pages cannot be imported. You can still enter an eligible role manually with verified details.

Drafts are simple local templates. They do not generate verified personal experience or infer your background. Add your own evidence and review every answer before use. Resume tailoring, bullet approvals, and formatted cover-letter PDFs are unavailable in this preview. The legal-tech and company views start empty; no private research datasets are bundled.

There is no scheduled discovery, automatic application submission, captcha handling, or automatic outreach. Optional Google Sheets commands require a separately installed and authenticated `gws` CLI. The Job Apply profile link requires the separately installed Job Apply plugin. It is off by default and reads the listed personal fields only when you click **Read my local profile**. No personal profile is loaded automatically.

## Local data and privacy

- `data/`: your profile, source configuration, contacts, reviews, and saved drafts.
- `out/`: generated rankings and exported packets.
- `src/job_app_system/assets/examples/`: public empty schemas and the discovery directory.

`data/`, `out/`, local config, logs, environment files, workspace codes, resumes, and archives are ignored by Git. These files are not included in the public release. Back up your working files yourself. The server permits only loopback, checks the local Host and request origin, and requires a per-run session for private APIs. One server may own a workspace at a time. The public dashboard page does not grant access to your data. Entering the owner-only workspace code establishes an HttpOnly session cookie; it expires when the browser session ends and becomes invalid when the server restarts. Mutating API calls require same-origin JSON dashboard requests. This is a single-user local app, not a hosted-service login system.

ATS refresh and official URL import make requests to employer websites when you invoke them. Core dashboard use does not require connecting an email or social account.

## Development

```bash
python -m pip install -r requirements-dev-lock.txt
python -m pip install -e .
python -m job_app_system.cli init
python -m pytest
```

The backend uses Python's HTTP server and CSV/JSON files. The frontend uses plain HTML, CSS, and JavaScript.

- `src/job_app_system/`: sourcing, ranking, local state, and server.
- `src/job_app_system/assets/web/`: dashboard UI.
- `tests/`: adapter, scoring, workflow, and application-packet checks.

## Save integrity and imports

Save operations hold a shared thread/process lock across the full read/modify/write and replace complete files atomically. This preserves the existing CSV/JSON formats. It does not provide database-style rollback of an entire multi-file rebuild. GET state requests do not rewrite rankings. Invalid new input is rejected before saving; malformed legacy job rows are excluded with a dashboard warning, preserving their source file for repair.

Private workspace directories/files use owner-only permissions on POSIX systems. Windows relies on the user's workspace ACLs. Application packets use hashes of the full role ID so long IDs do not collide. Original values remain in source files; spreadsheet CSV exports neutralize formula-like cells.

Official-page and ATS downloads enforce HTTPS, validate resolved addresses, pin connections to a validated public IP with normal TLS hostname verification, and repeat checks on redirects. Credential-bearing URLs and known authentication query parameters are rejected. Private/intranet job pages are not supported.

Requests are limited to 1 MB, the server caps workers at 16, and connection reads time out. LinkedIn import limits the compressed archive to 100 MB, total uncompressed contents to 50 MB, each member to 20 MB, and member count to 1,000. Large exports may need a ZIP containing only Connections.csv, Profile.csv and messages.csv. Network views show 200 matches at a time; use search to narrow results. Message content is used locally for derived signals and is not written to the connection table. Your original ZIP remains at the path you selected.

## Build a shareable source release

```bash
python scripts/package_release.py --output dist/public-release
```

The command selects only named source/assets/schema files, rejects example CSV data rows and common credential/personal-path patterns, and produces a reproducible ZIP, a manifest, and a clean `github-upload` folder. Choose a fresh output directory for each build. Do not upload the working folder: Git ignore rules do not sanitize manual browser uploads. Pattern checks are safeguards, not proof that arbitrary future edits contain no private information.

## License

MIT. See [LICENSE](LICENSE).

# Apply Desk

Find relevant jobs, decide which ones deserve your time, and prepare resume drafts—with your own Codex setup.

Apply Desk combines two parts:

- **A Codex plugin:** instructions that help Codex interview you, research jobs, explain rankings and improve resume bullets.
- **A local dashboard:** a page on your computer where you review jobs, manage preferences, approve changes and download drafts.

You bring your own role interests, location preferences, resume and supporting stories. The download starts blank. It uses your Codex engine and available tools; Apply Desk does not require a separate AI API key.

**Public preview:** job search works with Python 3.11 or newer. Exact Word/PDF resume generation currently requires **Microsoft Word installed on a Mac**. Windows users can use the dashboard and job-search workflow, but the built-in resume export stays unavailable. The Linux dashboard can run with Python; access to Codex and its tools depends on your host.

## Contents

1. [What you need](#1-what-you-need)
2. [Download and open Apply Desk](#2-download-and-open-apply-desk)
3. [Ask Codex to install it](#3-ask-codex-to-install-it)
4. [Complete your personal setup](#4-complete-your-personal-setup)
5. [Run your first job search](#5-run-your-first-job-search)
6. [Review changes and generate a resume](#6-review-changes-and-generate-a-resume)
7. [Use Job Apply or Simplify](#7-use-job-apply-or-simplify)
8. [Come back later and set up scheduling](#8-come-back-later-and-set-up-scheduling)
9. [Privacy, permissions and backups](#9-privacy-permissions-and-backups)
10. [Troubleshooting](#10-troubleshooting)
11. [Manual installation](#11-manual-installation)
12. [For contributors](#12-for-contributors)

## 1. What you need

Start with Codex installed, signed in and working. You do not need to know how to code, have a GitHub account, install Git or Node.js, or buy another AI subscription for Apply Desk itself. Your normal Codex usage and limits still apply.

| Item | When you need it | How to get it |
| --- | --- | --- |
| This download | Always | Follow Step 2. |
| Python 3.11 or newer | To run the dashboard | Codex can check for a suitable existing runtime. If none is available, it can guide you through [Python's official download page](https://www.python.org/downloads/). |
| Internet access and Codex web tools | To research current jobs | Codex checks which tools your setup provides and explains any missing access. |
| Microsoft Word on macOS | For verified Word/PDF generation | Install and activate Word yourself if you want this feature. Apply Desk does not include Word or its license. |
| Your editable `.docx` resume | For resume proposals and generation | Use the resume whose formatting you want to preserve. Its matching PDF is recommended. |
| Job Apply or Simplify | Optional application filling | Add either later; see Step 7. |

**You can finish job-search setup first and add your resume later.** Each feature shows its own missing requirements. Installing the plugin alone does not start the dashboard or complete your personal setup.

## 2. Download and open Apply Desk

1. Open the [Apply Desk GitHub repository](https://github.com/abhy-c/apply-desk).
2. Select the green **Code** button, then **Download ZIP**. You can do this without signing in to GitHub.
3. Extract the ZIP. On a Mac, double-click it. On Windows, right-click it and choose **Extract All**.
4. Move the extracted folder somewhere you will keep it, such as Documents. You may rename it `ApplyDesk`. This is your **workspace**: the folder where Apply Desk runs and saves your private settings.
5. Open that folder as a project/folder in Codex and start a chat there. Select the folder containing this `README.md`, `pyproject.toml`, `src` and `skills`—not the ZIP itself or an outer folder containing another extracted folder.

Keep your workspace outside the installed plugin cache. For help with Codex's folder/project controls, see the [official quickstart](https://learn.chatgpt.com/docs/quickstart).

**Checkpoint:** Codex can see this README and confirm that the plugin and dashboard source files are present. You have not supplied any personal resume files yet.

## 3. Ask Codex to install it

### Recommended: let Codex handle the technical steps

Paste this message into the chat you opened in the extracted folder:

```text
Set up Apply Desk from this folder for me. I am new to this and have only
Codex installed. Read README.md first and explain each step briefly.

Check my operating system and find a suitable Python 3.11+ runtime.
If it is missing, guide me to the official Python installer and wait for
me to install it. Create a private .venv environment in this folder and
install this package with its resume extra there, without changing my
system-wide Python packages.

Register this folder's local plugin marketplace and install
apply-desk@apply-desk-plugins using the supported tools available in my
Codex setup. Do not assume the codex terminal command is installed.
If I need to use the Plugins interface or restart Codex, tell me exactly
what to do. Verify the plugin is available in a new chat.

Initialize this folder as my workspace, start the local dashboard on
port 8767, and help me unlock it using its private workspace code.
Keep the server running and tell me how to stop or restart it.

Show which features are ready and which need more setup. Do not read
personal documents, configure recurring searches or submit applications
until I choose those steps.
```

Codex may ask you to approve package installation, local file changes or plugin setup. Read what each request does. If your host cannot perform a step, use the [manual instructions](#11-manual-installation) or ask Codex to guide you through them. This message is a setup request, not an installer that runs when you open the README.

For a local marketplace, the supported registration command is `codex plugin marketplace add .` from the extracted folder **when that command is available**. The desktop plugin interface can also discover a project's included marketplace. After a refresh/restart, choose the `apply-desk-plugins` source in the Plugins Directory and install **Apply Desk**. Interface availability can vary by Codex host; see [OpenAI's plugin installation guidance](https://developers.openai.com/plugins/build/plugins).

### Open and unlock the dashboard

1. With the server running, open [http://127.0.0.1:8767](http://127.0.0.1:8767).
2. Enter the workspace code at **Unlock your local workspace**. Codex can help retrieve it privately; the manual command is below.
3. Keep the process/terminal running while using the dashboard.

The address `127.0.0.1` means **your own computer**. It is not a public website. The workspace code is a local access code, not your Codex or GitHub password, and changes after a server restart.

**Checkpoint:** you can open the dashboard, unlock it, and see **Setup & improvements**. A new workspace should say setup is incomplete. An empty job list is expected at this point.

## 4. Complete your personal setup

Start a **new Codex chat in the same workspace** after installing the plugin. Paste:

```text
Use $apply-desk:apply-desk to set up my workspace. Ask one question at a
time, explain unfamiliar terms, and follow up until my answers are clear.
Start with job search. Show exactly what is missing for each feature.
Do not use anyone else's roles, preferences, resume or personal details.
```

The `$apply-desk:apply-desk` text names the plugin's main skill. You enter it in a Codex chat, not in a terminal. The plugin includes a **grill-me** setup interview that asks follow-up questions instead of filling gaps with guesses. For longer resume stories, voice answers are welcome if your Codex host supports them.

### Job-search questions

Codex will help you confirm:

1. **Role focus:** the kind of work you want, related job titles to include, and misleading titles to exclude. There is no default product-role focus.
2. **Locations:** countries/cities and remote, hybrid or on-site preferences. Work authorization and sponsorship questions are separate; you can skip them.
3. **Sources:** job boards, employer career pages and other places to search. Review included sources, add your own, and ask Codex to research useful additional sources. It offers additions one at a time.
4. **Ranking:** how to prioritize jobs. Review location, workplace, posting age, salary, authorization, seniority, industry, company size, connections and hiring-manager information one by one. Keep as many criteria as you want and add your own.

For each ranking rule, choose:

| Choice | Meaning |
| --- | --- |
| **Required** | The job must meet this rule. If the needed information is unknown, it needs verification. |
| **Preferred** | Matching improves the ranking. Set its importance from 1 to 10. |
| **Ignore** | Do not use this criterion to rank jobs. |

### Resume questions—when you are ready

Choose your editable Word master, preferably its matching PDF, and the facts/stories supporting your experience. A **master resume** is the approved document whose layout Apply Desk must preserve. A PDF alone cannot supply an editable Word master.

You can choose individual supporting files or a folder. A folder scan first lists filenames and metadata; select which files Codex may read. Newly added or changed files need another review. Codex asks follow-ups and confirms facts before proposing resume changes.

**Checkpoint:** **Job search setup complete** means focus, titles, locations, sources and ranking have been reviewed. **Resume setup complete** requires your Word master, confirmed facts, the resume software dependencies and a supported renderer. The dashboard names anything still missing; one feature being ready does not mean both are ready.

## 5. Run your first job search

1. Click **Find jobs now** in the dashboard.
2. Copy the displayed request prompt and paste it into Codex in the **same workspace**. Some buttons copy the prompt for you; it remains visible if clipboard access fails.
3. Let Codex research the configured sources, preserve listing evidence, import results and rebuild the rankings.
4. Refresh the dashboard to review the results and source checks.

**The dashboard does not launch Codex automatically.** The displayed prompt connects your dashboard request to the Codex chat that performs it. Use this same pattern for other research and improvement requests.

### Understand the results

- **Ranked jobs** meet your known required rules and are ordered using your chosen preferences.
- **Needs verification** contains jobs whose required information is missing. Codex researches the gaps thoroughly; missing salary or sponsorship is not silently treated as a pass.
- **Excluded jobs** failed a required rule, fall outside your confirmed scope or were rejected by you.

A job rejection applies to that job. It does not automatically change your rules. Repeated feedback can lead to an explained improvement proposal; you decide whether to approve it.

### Understand source status

**Working** means a recorded check succeeded. **Working, no matches** means the check succeeded but found nothing matching your preferences. **Untested**, **Blocked** and **Failed** do not mean a source was searched successfully.

An included source link is a place to look, not necessarily an automatic feed. Ashby, Greenhouse and Lever feeds need specific employer-board configuration; ask Codex to configure and test your chosen boards. Some websites need your login, payment or CAPTCHA handling. Codex records these blockers and continues with accessible sources. Search coverage is shown; no run is promised to find every job on the internet.

**Checkpoint:** you have either jobs to review or an explanation of the sources checked, zero matches, blockers and unresolved gaps.

## 6. Review changes and generate a resume

This feature currently needs **Microsoft Word on macOS**. Word may ask for access to the workspace's private rendering folder or for Automation permission during setup. Resolve the displayed request for the selected workspace; Review and approve the request yourself before continuing.

1. Select a job in **Setup & improvements** and request resume proposals. Paste the displayed prompt into Codex.
2. Review **only the bullets proposed for improvement**. Codex approaches them as a career coach: each proposal shows highlighted edits, a reason, destination context and supporting facts. All other bullets carry through unchanged.
3. Approve the exact wording or reject it. If a claim needs more evidence, answer the follow-up first. Nothing should invent ownership, tools or metrics.
4. Once all pending proposals for that role are reviewed, click **Generate Word + PDF**. This button performs the local export in one action; it does not need another chat prompt.
5. Download both drafts and inspect every page against your master. Check text, layout, links and page count.
6. Mark the pair visually checked only after that inspection.

Apply Desk copies your Word master and preserves fonts, sizes, emphasis, spacing, margins, bullets, tables, hyperlinks and section order. The resume cannot exceed the master's page count. If text overflows, approve shorter wording; it will not shrink the formatting to force a fit.

To revise an approved bullet, choose **Withdraw approval to revise**, then review and approve the replacement. An older export containing withdrawn wording is blocked from Job Apply handoff. Masters with active/embedded or remote-loading content are rejected; ordinary contact hyperlinks are supported. Complex mixed-emphasis edits may remain blocked until their formatting is supported—do not bypass that check.

**Checkpoint:** you have a role-specific `.docx` and matching `.pdf` whose content you approved and whose pages you checked. These are drafts, not submitted applications.

## 7. Use Job Apply or Simplify

Both are optional. You can download the resume and apply yourself without installing either.

### NeonWatty Job Apply

[Job Apply](https://github.com/neonwatty/job-apply-plugin) helps Codex fill application forms using reviewed resume/profile data, reuse confirmed answers and resume unfinished applications. Supported portals and form behavior can vary.

After setup, Apply Desk shows its companion-tool link. The **Application portals** panel is available earlier so you can prepare browser access separately. Ask Codex:

```text
Help me install NeonWatty Job Apply from the linked project, following its
current instructions. Configure its connection to Apply Desk and run the
isolated fictional-data check. Preserve my default profile and resume.
Show what passed and what remains unverified. Do not submit an application.
```

The **Configure and check Job Apply** request also needs its displayed prompt pasted into Codex. A compatible installed version is checked with fictional data first. If the installed version lacks that check, status stays unverified. A real-site check is a separate choice requiring your consent. Updating Job Apply requires checking the connection again.

To use your approved resume:

1. Click **Fill application with this resume** beside the visually checked export.
2. Confirm the employer, role and job URL shown.
3. Paste the displayed handoff prompt into Codex.
4. Codex uses Job Apply to upload that exact approved PDF and fill the selected application. You do not need to transfer the resume manually.
5. Review the filled form. Handle login, MFA, CAPTCHA and sensitive questions when asked. **You perform the final submission.**

The tailored resume is for this application only. Job Apply's saved default resume/profile remain unchanged unless you separately authorize a change. Unsupported per-application handoffs stay blocked.

### Prepare an employer portal, recheck before each application

1. In **Application portals**, name the employer, paste its public career/application link and choose the browser you actually use. Existing Chrome and the Codex in-app browser have separate logins.
2. Click **Save portal choice**, then **Guide me through connection**. Confirm the site shown and paste the displayed prompt into Codex.
3. Codex opens the approved page for a **read-only preflight**: can it read the page, is login needed, and does its browser tool support uploads? This step does not read your applicant profile, fill fields or upload a resume.
4. Handle sign-in, account creation, MFA and CAPTCHA yourself. While your input is needed, the request is **Waiting for you**. Once you finish, click **Resume after my input** and paste that prompt into Codex.
5. Review the saved status. **Preflight passed** means page/browser access was observed, not that an application was tested. Blockers and manual steps stay visible.

Workday can require a separate account per employer. A redirect to another site needs another approved portal choice. The known guided families are LinkedIn Easy Apply, Greenhouse, Ashby, Lever, Rippling and Workday; other portals offer manual guidance. Checks become stale after seven days or a Job Apply revision change. The actual form and authentication are still rechecked before every application. **Forget this portal check** removes the active saved check, without signing out of your browser.

Active requests have **Cancel request** controls. Cancellation stops further work at Codex's next state check, keeps completed files and does not undo earlier external actions. Repeated clicks reuse the same active request. Completed, failed and cancelled requests cannot silently restart; a new attempt needs a new user request.

**Check setup and show safe support report** reports versions, dependencies, readiness and counts without private contents, paths, URLs or credentials. Preview it before sharing. See [Security and privacy](SECURITY.md) for each feature's access requirements.

### Simplify Copilot

Apply Desk also pairs well with [Simplify Copilot's free autofill feature](https://simplify.jobs/copilot). Follow Simplify's own installation instructions, use your reviewed resume, and check the filled answers before submitting. This is an optional companion; Apply Desk does not install it or automatically send it your files.

## 8. Come back later and set up scheduling

Your preferences and drafts stay in the workspace when you stop the server.

To return, open the same folder in Codex and say:

```text
Restart my existing Apply Desk dashboard and help me unlock it.
Preserve my saved setup and files. Do not create a new workspace.
```

To stop a manually launched server, press **Ctrl+C** in its terminal. Closing that terminal or restarting your computer also stops it. The README setup does not install a background service.

**Remember to set up scheduling later.** Once a manual search works, ask Codex to help choose a recurring schedule, workspace and notification preferences using your host's supported scheduling feature. Scheduling is not enabled automatically and may depend on your host's tools and ability to access this local folder.

After searches or resume work, **Improvements available** may offer better rules, sources or tools based on your feedback and research. Review the exact change, evidence, access/cost, validation and undo instructions. Nothing installs or rewrites itself silently. Ranking-rule changes have built-in Undo; other changes may require the manual reversal steps shown.

## 9. Privacy, permissions and backups

Your workspace contains:

| Folder | What it holds |
| --- | --- |
| `data/` | Private settings, source checks, selected document copies, facts, approvals and request history. |
| `out/` | Ranked results and generated documents. |
| `.venv/` | The Python environment used to run the app. |
| `skills/` and `src/` | The reusable plugin instructions and app code supplied in the download. |

Selected information is processed by the Codex engine and tools you use. **Stored locally does not mean AI processing is offline.** Applying can share approved information with an employer; that step requires your confirmation. Source websites and optional tools may have their own account requirements.

Keep the dashboard on its local address. Do not publish your live workspace, private folders, workspace code or generated resumes to GitHub. The project's ignore rules are helpful, but browser uploads can still include files you select manually.

For backups, copy the whole workspace to a private location while the app is stopped. That backup contains personal information. Before updating, ask Codex to preserve `data/` and `out/`, back up the current folder, update the code and recheck the app. Keep a copy of your original resume outside the workspace too.

## 10. Troubleshooting

| What you see | What to do |
| --- | --- |
| “Site can't be reached” at the local address | Ask Codex to restart the server in your existing folder. A browser bookmark alone does not start it. |
| The workspace code is rejected | Retrieve the current code after the latest restart. Use the same address/port as the running server. |
| Apply Desk is missing from Codex | Check the marketplace registration and plugin installation. Refresh/restart the host if needed, then open a new chat. Ask Codex to verify the actual installed skill. |
| `codex: command not found` | The desktop app does not guarantee that terminal command is available. Use the plugin interface or ask Codex to locate a supported installation method; do not install random software to fix it. |
| Python is missing or too old | Ask Codex to check a suitable runtime, or install Python 3.11+ from its official site. Restart the terminal after installation. |
| `No module named job_app_system` | You are using the wrong Python environment or the package was not installed. Run with the workspace's `.venv` Python, as below. |
| “Address already in use” / port 8767 is busy | Stop an older Apply Desk server, or ask Codex to choose another port and use that same port in the browser. |
| Setup stays incomplete | Read the listed missing items. Confirm them individually; do not mark unanswered questions complete. |
| No jobs appear | Run a search through Codex, then inspect source checks, coverage, scope and Needs verification. Adding a link alone does not collect jobs. |
| Word export times out | Resolve Word's displayed file-access/Automation dialog and retry. A timeout is not a verified PDF. |
| Resume export is unavailable on Windows/Linux | This preview's exact renderer requires Word on macOS. Job search remains usable; do not treat an alternative export as verified master formatting. |
| Pending changes or overflow block generation | Review pending proposals or approve shorter text. Keep the master's formatting. |
| An application handoff is blocked | Check that the role is still open, the URL matches, the drafts are unchanged, their approvals remain valid and visual review is complete. |

When asking for help, share the error message and operating system. Remove personal content, file paths, passwords and workspace codes from public screenshots or issues.

## 11. Manual installation

Use this if you prefer typing commands or Codex cannot run setup. A **terminal** is an app for entering commands: Terminal on a Mac, or PowerShell on Windows. Enter one line at a time and wait for it to finish. Do not type the backtick markers around a code block.

First install Python 3.11+ if needed, then open a terminal **inside the extracted Apply Desk folder**. Ask Codex to give you the exact `cd` command for your folder; paths containing spaces must be quoted. All commands below assume that folder is the current directory.

### macOS

Check the Python version, create a private environment, install the package and initialize your blank workspace:

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[resume]'
.venv/bin/python -m job_app_system.cli init
.venv/bin/python -m job_app_system.cli serve --port 8767
```

If the version shown is below 3.11, stop and choose a suitable interpreter with Codex before continuing. The final command keeps running while the dashboard is open.

Open a **second terminal in the same folder**, leaving the first running:

```bash
.venv/bin/python -m job_app_system.cli unlock-code
```

Enter the code it prints at [http://127.0.0.1:8767](http://127.0.0.1:8767). Keep it private. To start the app another day, run the `serve` command again; initialization and package installation are not needed every time.

### Windows PowerShell

Check the Python version. If the `py` command is unavailable, ask Codex for the correct command for your installed Python instead of assuming installation failed.

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[resume]"
.\.venv\Scripts\python.exe -m job_app_system.cli init
.\.venv\Scripts\python.exe -m job_app_system.cli serve --port 8767
```

Use Python 3.11 or newer. In a second PowerShell window in the same folder:

```powershell
.\.venv\Scripts\python.exe -m job_app_system.cli unlock-code
```

Open the same local dashboard address and enter the code. These commands use the environment directly; you do not need to activate scripts or weaken PowerShell's execution policy. Windows job search works, but the built-in exact resume renderer remains unavailable.

### Install the plugin separately

The Python commands above install the dashboard, **not the Codex plugin**. If the `codex` terminal command is available, run these from the extracted folder:

```bash
codex plugin marketplace add .
codex plugin add apply-desk@apply-desk-plugins
```

Otherwise, use the desktop Plugins Directory with this project's included marketplace, following Step 3. Start a new chat and verify that `$apply-desk:apply-desk` is available. Do not store private workspace data in the installed plugin cache.

Linux users with a suitable Codex host can use the macOS-style Python commands; exact Word/PDF export is not supported there in this preview.

## 12. For contributors

The backend uses Python and private CSV/JSON files; the dashboard uses plain HTML/CSS/JavaScript. Codex provides reasoning and research through skills and a JSON command bridge. Core dashboard use has no third-party Python runtime dependencies; the resume extra provides lxml and pypdf.

This is a single-user local service. Private APIs use a per-run session, same-origin checks and bounded requests. Persistence uses locks and atomic file replacement, with no multi-file database rollback. HTTPS downloads validate public addresses and redirects. Optional profile reads and integrations require consent.

To develop and package a clean release:

```bash
python -m pip install -r requirements-dev-lock.txt
python -m pip install -e '.[resume]'
python -m pytest
python scripts/package_release.py --output dist/public-release
```

Use a fresh output folder each time. The release builder includes only selected source, generic skills, empty CSV schemas, public source links and documentation; it checks common secrets and personal paths, then creates a reproducible ZIP and SHA256 manifest. Publish the frozen `github-upload` contents, including its hidden plugin/marketplace folders. Do not run the app or tests inside that frozen snapshot.

The package declares an onboarding skill for hosts supporting install-time setup; the manual prompts remain available. See [Changes](CHANGELOG.md), [Contributing](CONTRIBUTING.md) and [Security](SECURITY.md).

Apply Desk is distributed through this repository's marketplace. It is not an approved universal-directory listing. MIT license; see [LICENSE](LICENSE).

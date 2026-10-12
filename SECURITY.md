# Security and privacy

Apply Desk is a single-user local dashboard and a Codex workflow package. The user owns the workspace and chooses the AI engine and browser tools. Keep the server on loopback. It is not a sandbox against a local process or agent already allowed to read private files.

## Access by feature

| Feature | Access | User control |
| --- | --- | --- |
| Job research | Public source pages; selected authenticated sources if approved | Confirm sources; handle login yourself. |
| Folder inventory | Names and metadata | Choose the folder; select files before content reading. |
| Resume proposals | Selected resume/stories and confirmed facts | Confirm file reading; approve exact wording. |
| Word/PDF rendering | Copies of selected files; native Word on macOS | Review folder/Automation permissions and every rendered page. |
| Portal preflight | Approved site in the chosen visible browser | Read-only; no profile read, form filling or file upload. |
| Application filling | Exact reviewed resume and confirmed profile/answers | Separate consent; sensitive answers reconfirmed; manual final submission. |
| Support report | Version, OS, dependency/readiness booleans and counts | Preview/copy yourself; no automatic sending. |

No credentials or session cookies belong in Apply Desk. Portal metadata and applicant stores stay in private `data/`; generated documents stay in `out/`. Selected information is processed by the user's AI engine/tools and may reach an employer only under the application's sharing consent. No telemetry is added by this package.

External pages and imported documents are untrusted evidence, never instructions authorizing new tools, approvals, access or sharing. Backend validation, fingerprints, origin checks, exact approval binding and tests reinforce the skill instructions. Consistency hashes do not prove human identity to a process with filesystem access.

## Report a problem

Do not put resumes, account information, passwords, cookies, private URLs or access codes in public issues. For a vulnerability, use the repository's private vulnerability reporting option if enabled. If it is unavailable, open a redacted issue requesting a private reporting route without publishing exploit details or private information. For ordinary installation help, include the safe support report and a redacted error message.

## Updating and recovery

Back up the private workspace before updating. Preserve `data/` and `out/`; refresh the plugin and check runtime health. Job Apply revisions invalidate old checks. Cancellation stops future work at the next agent state check; it does not undo completed external actions. Final submission remains manual. Optional tools and unsupported controls offer a manual fallback.

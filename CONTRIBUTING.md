# Contributing

Read AGENTS.md. Use fictional fixtures and a separate test workspace. Keep real applicant files and personal configuration out of source, tests, screenshots and release artifacts.

Keep skills focused on user goals and place conditional detail in references. Prefer existing host tools and the JSON bridge; do not add an embedded model, secret-requiring ATS API, background browser automation or lifecycle hooks without a demonstrated need and explicit access design. Changes must preserve human approval and final manual submission.

Validate schema and lifecycle behavior at the backend, not only in prompts or buttons. Cover stale evidence/approvals, changed origins, duplicate requests, cancellation, missing dependencies and honest partial failure. Do not turn a local test result into a claim that all real employer portals work.

Run the nearby tests, then the release suite. Validate skill frontmatter and references, both manifests and marketplace paths. Build with scripts/package_release.py into a fresh output folder. Review its manifest, examples, privacy checks and README before publication. The frozen upload folder must not contain a running workspace.

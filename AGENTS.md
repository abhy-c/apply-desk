# Apply Desk public preview

Keep applicant data in ignored `data/` and generated files in ignored `out/`.
Never commit real resumes, contact exports, credentials, application packets, or local settings.
Use fictional examples in tests. Preserve user approval before external submissions or outreach.
Run `python -m pytest` after behavior changes.
The public preview excludes the original owner's private resume templates and tailoring configuration.

## Release integrity

- Private HTTP APIs require an owner-held workspace code and a per-run session. Keep the listener on loopback and validate Host, Origin, content type and payload bounds.
- Hold the workspace transaction around complete read/modify/write operations. Use atomic persistence helpers; state GET requests must not change stored rankings.
- External downloads use the shared HTTPS/DNS-pinning implementation. Validate data before persistence and preserve evidence from rejected legacy rows.
- Personal integrations are opt-in. Do not read an external profile during page initialization.
- Generate upload files with `scripts/package_release.py`. Do not run the app, install packages, or run tests in the frozen upload folder.

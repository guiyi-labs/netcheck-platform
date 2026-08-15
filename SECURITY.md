# Security Policy

## Supported Versions

NetCheck Platform is pre-1.0. Security fixes are applied only to the latest
release line on the `main` branch. Older releases are not maintained.

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest| :x:                |

## Reporting a Vulnerability

The NetCheck team treats security reports as the highest-priority work.
**Do not open public GitHub issues for security problems.**

Report vulnerabilities by one of the following private channels:

1. **GitHub Security Advisory** (preferred): use
   `Security` -> `Report a vulnerability` on the repository. This keeps the
   conversation private and allows the maintainers to request CVE IDs through
   GitHub.
2. **Encrypted email**: send a PGP-encrypted report to
   `security@netcheck.local`. The current public key fingerprint is published
   in the release notes of the most recent release.

Please include the following information so we can reproduce and triage the
report quickly:

- Affected version (git tag or commit SHA).
- Component (backend API, collector, frontend, CI workflow, dependency).
- Step-by-step reproduction, including any required device or network state.
- Observed impact and any proof of concept.
- Suggested fix or mitigation, if any.

### Disclosure timeline

| Stage                         | Target       |
|-------------------------------|--------------|
| Acknowledgement of receipt    | 1 business day |
| Initial triage and severity   | 5 business days |
| Fix or mitigation published   | 30 calendar days for high/critical severity, 90 calendar days otherwise |
| Public disclosure             | After a fix is released, or after 90 days if no fix path is agreed, whichever comes first |

Reporters are credited in the change record unless they request otherwise.

## Threat model boundaries

The following boundaries are explicit, documented design decisions and must
hold for any contribution that touches them. Violations fail the test gate.

- **Read-only device collection.** The platform connects to managed devices
  over SNMPv3 and SSH **read-only**. SSH never requests a PTY or runs
  interactive commands beyond the documented collector command; SNMP only
  issues GET/BULK WALKs against an OID allowlist.
- **Plaintext credentials never persisted, echoed, or exported.** Device
  credentials (SNMPv3 auth/priv keys, SSH private keys) are encrypted at rest
  with AES-256-GCM (see `backend/app/services/credential_manager.py`) and are
  never returned by API responses, logs, diffs, or exports — only status bits
  and digests are exposed.
- **Config snapshots are redacted before storage.** Full device config text
  is kept in memory only; only the redacted form (`config_text_redacted`) and
  a SHA-256 content hash are persisted. The redactor covers line-level secret
  patterns plus multi-line PEM private-key blocks.
- **SSH host keys are verified.** Host-key policy distinguishes
  `host_key_unknown` / `host_key_mismatch` from authentication failures;
  a pinned `host_key_fingerprint` on a device rejects mismatches instead of
  silently trusting a changed key.
- **Authorized scanning only.** Discovery is capped at `MAX_TARGETS = 256`
  and must only be run against address ranges the operator is authorized to
  scan. Live credentials, device addresses, and scan logs must never be
  committed to the repository.
- **Exposure is opt-in.** Alert notifications (SMTP/Webhook), AI diagnosis,
  and any external reporting are disabled by default and require explicit
  configuration with outbound destinations and credentials.

## CI and supply-chain controls

The following controls are enforced by `.github/workflows/ci.yml`:

- **Pull-request-only triggers.** CI runs on `push` to `main` and on
  `pull_request` events. Workflows never receive write access to the
  repository on pull-request events, and `secrets.*` are not used by the
  backend test job.
- **Test gate.** `pytest` runs the full backend suite on Python 3.11 with a
  pinned `backend/requirements.txt`; regressions fail the gate (baseline:
  257 tests).
- **Dependency pinning.** Runtime dependencies are pinned in
  `backend/requirements.txt`; new transitive dependencies must be reviewed
  before they are introduced.

## Credential handling

- Device credentials are encrypted at rest with **AES-256-GCM** using a key
  derived from `NETCHECK_SECRET_KEY` (SHA-256 of the configured secret).
  If `NETCHECK_SECRET_KEY` is unset, credentials are stored only as a
  placeholder marker and reported as unavailable — never as usable plaintext.
- API responses, audit logs, config diffs, and Excel/Text exports expose only
  `has_secret` status bits and short digests, never secret values.
- The bootstrap admin password is hashed with PBKDF2-SHA-256 (per-password
  random salt) and is rate-limited: login locks for
  `login_lock_minutes` after `login_max_attempts` consecutive failures.
  The local demo account `admin` / `admin123` is for local demo only and must
  be replaced before any real deployment.
- Notification channels (SMTP password, Webhook URL and headers, AI API key)
  are environment-driven configuration, never stored in the database.

## Security-conscious contribution checklist

Before opening a pull request that touches security-sensitive code, confirm:

- [ ] No new plaintext credential paths: credentials stay encrypted at rest
      and are never returned by APIs, logs, or exports.
- [ ] No new `pull_request_target` triggers or `secrets.*` use in CI.
- [ ] Config redaction covers any new sensitive line patterns (and PEM
      multi-line blocks if applicable); plaintext is never persisted.
- [ ] SSH host-key policy still distinguishes unknown/mismatch and honors a
      pinned fingerprint when set.
- [ ] SNMP access remains read-only and within the documented OID allowlist.
- [ ] Discovery target limits and authorization boundaries are preserved.
- [ ] New environment variables are documented without secret values
      (see `backend/app/core/config.py`).

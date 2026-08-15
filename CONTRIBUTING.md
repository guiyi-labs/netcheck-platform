# Contributing to NetCheck Platform

Thank you for your interest in contributing to NetCheck Platform, a
network-operations observability platform (SNMPv3/SSH device collection,
config backup and diff, alerting, LLDP neighbor discovery). This document
outlines the contribution process and the conventions the project follows.

## Prerequisites

- Python 3.11+ for backend development
- Docker and Docker Compose for running the full stack locally
- A Linux/macOS host for real-device / network verification (container
  demo network is included via Compose)
- Node.js 18+ (only needed for frontend builds)

## Getting Started

1. Fork the repository and clone your fork
2. Create a new branch for your changes:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. Make your changes, following the existing code style and conventions
4. Run the backend test suite:
   ```bash
   cd backend && pip install -r requirements.txt && pytest -q
   ```
5. Ensure the fast gate passes locally (baseline: 257 tests)
6. Commit and push your changes
7. Open a pull request against the `main` branch

## Code Conventions

- **Backend (Python/FastAPI)**: Follow standard Python conventions and the
  existing module layout under `backend/app` (`api/`, `services/`, `models/`,
  `schemas/`, `core/`). Keep collector logic in `services/` and HTTP surface
  in `api/` — do not mix them.
- **Credential safety**: New features touching credentials must go through
  `backend/app/services/credential_manager.py` (AES-256-GCM at rest, digests
  only for display). Never log, return, or export plaintext secrets.
- **Collector classification**: New failure modes for SNMP/SSH collection
  should follow the existing status vocabulary
  (`ok / auth_failed / priv_failed / timeout / host_key_unknown /
  host_key_mismatch / conn_refused / cmd_not_supported / parse_failed /
  error`).
- **Testing**: New features should include unit tests under
  `backend/tests/`. Changes to behavior must update existing tests.
- **Docs**: User-visible behavior belongs in `README.md`, `CHANGELOG.md`, and
  the delivery docs under `docs/final-delivery/`.

## Pull Request Workflow

1. **Before submitting**: Ensure `pytest -q` passes locally (baseline 257
   tests). Do not break existing collector status semantics or the LLDP
   layout fallbacks.
2. **PR description**: Clearly describe the what, why, and how of your
   changes, and how you verified them (unit test, Compose demo, real device).
   If the change touches security-sensitive code, run the checklist in
   [SECURITY.md](SECURITY.md).
3. **CI gates**: Your PR must pass the backend CI job (Python 3.11, pinned
   requirements, full pytest suite) before review.
4. **Review**: After CI passes, the PR will be reviewed. Address feedback
   promptly.

## Reporting Issues

When filing an issue, please include:

- Clear description of the problem
- Steps to reproduce
- Expected behavior vs actual behavior
- Screenshots or error logs if applicable
- Environment details (OS, Python version, deployment mode: Compose vs bare)

## Security Disclosure

For security vulnerabilities, please follow the process outlined in
[SECURITY.md](SECURITY.md). Do not file public issues for security
vulnerabilities.

# Security policy

## Report privately

Use **Security → Advisories → Report a vulnerability** in the [project repository](https://github.com/ImanAkrami/codex-den/security/advisories). This sends a private report to repository maintainers through GitHub; no personal email address is required.

Include affected version, impact, minimal reproduction using synthetic data, and a proposed fix if available. Never post credentials, authentication/session files, exploit details, or sensitive configuration in public issues. If private reporting is unavailable, do not post vulnerability details publicly; request that maintainers enable the reporting button without disclosing the issue.

## Supported versions and boundaries

The latest preview receives reviewed security fixes. No long-term stable support window has been declared.

Environment directories separate application state; they do not restrict operating-system access. Shared environments deliberately share local authentication and history. Configuration transfers exclude known credential/runtime paths and redact known structured secret fields. Arbitrary instructions and skills can still contain sensitive text: inspect them before export.

Dependencies and security changes go through review and the complete test gate. Pull-request workflows receive no publication credentials. See [compatibility](docs/compatibility.md) for operational limits and [maintainer guidance](docs/maintaining.md) for enabling/verifying private reporting before publication.

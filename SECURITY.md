# Security Policy

## Supported Versions

Yigthinker is pre-1.0. The only actively supported version is the latest release on PyPI (or `master` if you install from GitHub source). Security fixes are not back-ported to older 0.x versions.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security bugs.**

Preferred channel: open a private security advisory via the GitHub Security tab (`Security` → `Advisories` → `New draft security advisory`). This creates an encrypted private conversation between you and the maintainers.

Alternatively, email the maintainer directly (see the `authors` field in `pyproject.toml` or the commit log for current contact). Subject line: `[yigthinker security]`.

When reporting, please include:

- A description of the vulnerability and its impact
- Steps to reproduce (ideally a minimal proof-of-concept)
- The version of Yigthinker (or commit SHA) where you observed it
- Your suggested disclosure timeline

We aim to acknowledge reports within 5 business days and to issue a fix or mitigation within 30 days for confirmed high-severity vulnerabilities. Lower-severity issues may take longer.

## Scope

The following are in-scope for security reports:

- The `yigthinker` core package and its public API
- The `yigthinker-mcp-uipath` and `yigthinker-mcp-powerautomate` MCP server packages
- Installer scripts (`install.sh`, `install.ps1`)
- Examples and documentation that could mislead users into insecure configurations

The following are **out of scope** and should be reported upstream to the respective projects:

- Vulnerabilities in third-party dependencies (report to the dependency; we will track via dependabot)
- Vulnerabilities in the Anthropic, OpenAI, Azure, or UiPath / Microsoft Power Automate services themselves
- Misconfigurations in the user's own deployment (e.g. running the gateway with permissive `bypassAll` mode on a public network)

## Known Security-Relevant Design Choices

These are deliberate trade-offs documented for transparency, not vulnerabilities:

- **`df_transform` executes LLM-generated Python** in a restricted `exec()` sandbox with getattr dunder blocking + wall-clock timeout. The sandbox is best-effort — do not rely on it for untrusted input. Production deployments should pair it with the permission system set to `ask` or `deny` for `df_transform`.
- **`sql_query` runs LLM-generated SQL** via parameterised queries, but DML is routed through permission checks. Run the configured database user as read-only where possible.
- **Vault integration** (`vault://path`) and OS keyring are the supported credential paths. Never put plain credentials in `settings.json`. The workflow template engine refuses to substitute raw secrets.
- **Workflow templates** use Jinja2 `SandboxedEnvironment` + AST validation (two-layer SSTI prevention) for generated Python scripts.
- **Hook commands** run in subprocesses with a timeout. Commands come from `.yigthinker/settings.json`, which is user-owned — any attacker who can write to that file already has a stronger foothold than a hook would give them.

## Responsible Disclosure

We commit to:

- Acknowledging your report privately within 5 business days
- Keeping you informed about the progress of the fix
- Crediting you in the release notes (or keeping you anonymous, if you prefer)
- Not pursuing legal action against researchers who follow responsible disclosure practices

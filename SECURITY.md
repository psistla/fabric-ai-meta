# Security Policy

## Supported versions

Security fixes are provided for the current 1.8.x release line.

| Version | Supported |
|---------|-----------|
| 1.8.x   | Yes       |
| < 1.8   | No        |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting on this repository: **Security > Report a vulnerability**. Do not open
a public issue for a suspected vulnerability.

You will get an acknowledgement, and a fix or mitigation plan once the report is
triaged. Please give a reasonable window to address the issue before any public
disclosure.

## Sensitive surfaces

These are the parts of the tool that touch credentials or live systems. Keep
them in mind when configuring and when reporting issues.

- **Entra credentials.** `auth login` and live extraction authenticate against
  Microsoft Entra. Credentials are handled by `azure-identity`; the tool stores
  no tokens of its own.
- **LLM API keys.** Enrichment reads a provider key from the environment variable
  named in your config. The config stores the *name* of the variable, never the
  value; no key is written to disk or logged.
- **Live semantic model writeback.** `apply-descriptions` and `apply-copilot`
  modify live models. Both default to dry-run and change nothing until you pass
  `--no-dry-run`.
- **MCP server filesystem exposure.** `serve` reads whatever `.pbip` path a
  connected agent names. Run it only against models and agents you trust.
- **Response cache.** `.fabric-ai-meta-cache/` (created in the working directory,
  gitignored) holds plaintext LLM responses with no expiry. These can contain
  model vocabulary such as table and measure names. Delete the directory to clear
  it.

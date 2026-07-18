# Operations and Recovery

## Regional capability decisions

FRA identifies US issuers with SEC CIKs and exchange-qualified symbols. SEC EDGAR is the regulated
filing source; yfinance remains an unofficial, personal-use-only market fallback rather than an
authoritative exchange feed.

South Korean disclosures use the eight-digit OpenDART corporation code and preserve the six-digit
stock code only as a separate listing identifier. OpenDART disclosure search is available when an
`OPENDART_API_KEY` environment-variable reference is configured. KRX market data is not enabled:
membership, service approval, key issuance, and a dated terms review must be completed before an
adapter may be added. FRA does not infer approval from the presence of a credential.

Vietnam uses exchange-qualified symbols and configured official document URLs or feeds.

The authoritative-price provider decision was completed on 2026-07-19: **no provider is approved
for the current FRA release, so the Vietnam pack remains partial**. HNX publishes official market
data on its website and offers information-service packages, while HOSE publishes priced Market
Data Feed and Webservice products. FRA has not executed a service agreement, approved usage and
retention terms, or implemented and contract-tested an adapter for either exchange. Public web-page
availability is not treated as an API or redistribution license. yfinance remains an explicitly
unofficial, personal-research-only fallback and must never be described as authoritative Vietnam
coverage.

Reopen the decision only when an operator records all of: the exchange or licensed vendor contract,
permitted usage and retention profiles, redistribution terms, credentials/service approval, stable
schema and identifier mappings, point-in-time behavior, attribution, and a passing shared source
contract suite. Relevant official product surfaces are the
[HNX market-data page](https://www.hnx.vn/vi-vn/m-niem-yet/du-lieu-thi-truong.html),
[HNX information packages](https://www.hnx.vn/vi-vn/dich-vu-cctt/du-lieu-cung-cap-list.html), and
[HOSE information-service pricing](https://staticfile.hsx.vn/Uploads/UploadDocuments/2406142/Bieu%20gia%20dich%20vu%20cung%20cap%20tin.pdf).

## Backup and Markdown-only export

`fra workspace export DESTINATION` creates a new destination and copies durable Markdown only. It
excludes caches, logs, locks, and generated indexes. The command refuses an existing destination or
a destination inside the source workspace. Keep exported directories under the same access control
as the source because reports and profiles may contain user-supplied research facts.

## Schema migration

`fra workspace migrate DESTINATION` first makes a new Markdown-only copy, parses YAML front matter,
and applies supported schema conversions structurally. It never edits the source workspace. The
current migrator upgrades schema version 0 front matter to version 1 and writes
`migration-report.md`; unknown or newer versions stop visibly.

## Index recovery

Markdown is always authoritative. `fra workspace rebuild-index` recreates `index.md` and
`.indexes/artifacts.json` from Markdown. Both outputs may be deleted at any time. A recovery
exercise is:

1. stop FRA commands that can write;
2. make a Markdown-only export;
3. validate `workspace.md` with `fra doctor`;
4. remove `.indexes/` and `index.md` if either is suspect;
5. run `fra workspace rebuild-index`;
6. run `fra dashboard --plain-text` and inspect artifact links;
7. restore from the newest verified export into a new directory if authoritative Markdown is
   corrupt.

Interrupted writes leave the prior atomic file intact. Temporary siblings are not authoritative and
may be removed only after confirming no FRA process is writing.

## Installation and cross-platform behavior

The supported baseline is Python 3.12 or newer installed from the locked project environment:

```console
uv sync --locked --all-groups
uv build
uv run fra --help
uv run fra doctor
```

Atomic replacement uses the host filesystem, and aggregate locks use `flock` on POSIX systems or
the standard Windows locking API. Owner-only POSIX modes are applied where supported; on filesystems
without those modes, directory ACLs remain the operator's responsibility. Agent cancellation uses
process groups and therefore requires a supported local Codex or Claude Code CLI environment.

The hermetic release gates run on `ubuntu-latest`, `macos-latest`, and `windows-latest`. Installed
agent and live-source smokes remain operator-run gates because hosted CI deliberately has no agent
authentication or provider credentials.

## Security and privacy review

- Secrets are environment-variable references, never inline TOML values or persisted source URLs.
- Diagnostics and agent events pass through central redaction before user-visible output.
- Workspaces minimize free-form personal information and expose no account, brokerage, custody, or
  order capability.
- Source licenses and retention policies fail closed; generated indexes omit document content.
- Export and migration never overwrite an existing destination.
- Default tests use sanitized fixtures and require no network, credentials, or installed agent CLI.

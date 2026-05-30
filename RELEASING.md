# Releasing paramant-sdk

Both packages publish under the name `paramant-sdk` (PyPI and npm) from this
repo via `.github/workflows/release.yml`, triggered when a GitHub Release is
published. The release tag must be `v<version>` and must match the version in
both `sdk-py/pyproject.toml` and `sdk-js/package.json`, or the run fails before
anything is published.

## One-time setup

Publishing is irreversible: a published version number can never be reused. Do
the setup once, then every release is a tag.

### PyPI (trusted publishing, no token)

1. On PyPI, open the `paramant-sdk` project, Settings, Publishing.
2. Add a GitHub Actions trusted publisher:
   - Owner: `Apolloccrypt`
   - Repository: `paramant-sdk`
   - Workflow: `release.yml`
   - Environment: leave empty (none configured)
3. That is all. The workflow authenticates over OIDC; no API token is stored.

### npm (automation token)

1. On npmjs.com, create an automation access token with publish rights to
   `paramant-sdk`.
2. In this repo: Settings, Secrets and variables, Actions, add a secret named
   `NPM_TOKEN` with that value.

Publishing uses `--provenance`, so npm records a signed link back to this
workflow run.

## Cutting a release

1. Make sure `sdk-py/pyproject.toml` and `sdk-js/package.json` are both at the
   target version (they move together). Bump them in a normal PR if needed.
2. Confirm CI is green on `main` (the `tests` workflow: sdk-js, sdk-py,
   conformance).
3. Create a GitHub Release tagged `v<version>` (for example `v3.2.0`).
4. The `release` workflow builds and publishes both packages, after re-checking
   that the version matches the tag.

## Notes

- The Python import path is `from paramant import GhostPipe`. The old
  `from paramant_sdk import ...` still works through a deprecation shim and is
  scheduled for removal in 4.0.
- The canonical wire-format v1 spec lives with the relay and core
  (`paramant-relay/docs/wire-format-v1.md`); the conformance suite cites it.

# Releasing paramant-sdk

Both packages publish under the name `paramant-sdk` (PyPI and npm) from this
repo via `.github/workflows/release.yml`, triggered when a GitHub Release is
published. The release tag must be `v<version>` and must match the version in
both `sdk-py/pyproject.toml` and `sdk-js/package.json`, or the run fails before
anything is published.

## Current state (checked 2026-09-02)

| | Configured? | Last published |
|---|---|---|
| PyPI trusted publisher | Documented below as the setup, **not verifiable from this repo** (PyPI does not expose it over the API). No secret is needed either way. | `paramant-sdk` 3.0.0 |
| npm `NPM_TOKEN` secret | **Missing.** `gh secret list --repo Apolloccrypt/paramant-sdk` returns nothing; the repo has no Actions secrets and no environments. | `paramant-sdk` 3.0.0 |

So 3.1.0 and 3.2.0 shipped in this repo but never reached either registry: the
repo has no version tags at all and one draft release (`v3.2.0`, never
published), so a release of 3.3.0 would be the first publish since 3.0.0 on both
sides.

Because `NPM_TOKEN` is absent, the `publish-npm` job **skips its publish step
with a warning instead of failing** (see `release.yml`). The PyPI job is a
separate job and is not affected: a missing npm token can no longer turn a
release run red or hold up the Python publish. Add the secret and re-run the
workflow (`workflow_dispatch`) to publish the npm package afterwards.

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
   `NPM_TOKEN` with that value. Until that exists, the npm job runs its version
   check and its tests and then skips publishing with a `::warning`, so the
   release itself still succeeds.

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

## What `gh release create v3.3.0` does today

1. Both jobs check out the tag and assert that their package version equals
   `3.3.0` (`sdk-py/pyproject.toml` and `sdk-js/package.json` — both are at
   3.3.0).
2. `publish-pypi` builds an sdist and a wheel and publishes **paramant-sdk
   3.3.0 to PyPI** over OIDC, provided the trusted publisher above is actually
   configured on the PyPI project. If it is not, that job fails at the publish
   step with an OIDC error and nothing is published.
3. `publish-npm` installs and runs `npm test` as a gate, then finds no
   `NPM_TOKEN`, prints a warning and a job-summary note, and finishes green
   **without publishing to npm**.

Net effect right now: PyPI gets 3.3.0, npm stays at 3.0.0, and the run is green.

## Notes

- The Python import path is `from paramant import GhostPipe`. The old
  `from paramant_sdk import ...` still works through a deprecation shim and is
  scheduled for removal in 4.0.
- The canonical wire-format v1 spec lives with the relay and core
  (`paramant-relay/docs/wire-format-v1.md`); the conformance suite cites it.

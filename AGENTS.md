# AGENTS.md

## Cursor Cloud specific instructions

This repo is **two libraries plus a cross-implementation conformance suite** — there is no server or GUI to run. Testing is terminal-based.

Components:
- `sdk-js/` — JavaScript SDK (`paramant-sdk`). Scripts in `sdk-js/package.json`: `npm test` (node `--test`), `npm run typecheck`.
- `sdk-py/` — Python SDK (`paramant-sdk`). Deps in `pyproject.toml`; run tests with `pytest`.
- `tests/conformance/` — cross-impl suite (`node --test tests/conformance/conformance.test.mjs`); see its `README.md`.

The update script already installs deps: `npm install` in `sdk-js/`, and a venv at `sdk-py/.venv` with `pip install -e "./sdk-py[dev]"`. Use that venv's interpreter directly: `sdk-py/.venv/bin/python` / `sdk-py/.venv/bin/pytest`.

Non-obvious caveats:
- **`npm run typecheck` is broken in-repo**: there is no `tsconfig.json`, so `tsc --noEmit` prints its help text and exits 1. CI (`.github/workflows/test.yml`) only runs `npm test`, not typecheck. Do not treat the typecheck failure as a regression and do not add a `tsconfig.json` unless asked.
- **Conformance suite requires `@paramant/core`** (the relay's Rust NAPI crypto binding) — it is NOT optional in the test code: without it the preflight + 9 cross-impl tests *fail* (not skip). It is built from the sibling repo `https://github.com/Apolloccrypt/paramant-core` (Rust 1.95 via rustup + `cmake`/`ninja`/`clang`/`libclang-dev` to compile liboqs). Build once: `cargo build -p paramant-core-node --release` then `cp target/release/libparamant_core_node.so crates/paramant-core-node/index.node`. Run the suite with both env vars set:
  `PARAMANT_PY=sdk-py/.venv/bin/python PARAMANT_CORE_NODE=<core>/crates/paramant-core-node/index.node node --test tests/conformance/conformance.test.mjs`
  Expected healthy result: **17 pass, 2 skip, 0 fail** (the 2 skips are the relay wire-encoder tests — the relay repo is absent here, which is expected).
- **Examples won't run offline**: `sdk-js/examples/*` and `sdk-py/examples/*` talk to a live Paramant relay and need a real `pgp_...` API key. To exercise the core crypto without a relay, call the SDKs' public crypto + wire-format APIs directly (`paramant.crypto` / `paramant.wire_format`; JS exports `wireEncode`/`wireDecode`/`isV1`).
- AAD gotcha when building blobs by hand: `build_aad`/`buildAAD` returns 14 bytes (10-byte header + 4-byte chunk_index) and is what the sender signature and AES-GCM bind to; `decode()`'s `aad` field is only the 10-byte header. Rebuild the 14-byte AAD on the recipient side for signature verify + GCM decrypt.

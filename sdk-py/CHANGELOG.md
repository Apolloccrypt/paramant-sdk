# Changelog

All notable changes to `paramant-sdk` (Python).

## [3.3.0] - 2026-09-02

Compatibility release for a relay change. `receive()` now gets its delivery
receipt from relays on both sides of the 2026-09 move, and neither loses it
quietly nor lets a missing one cost you the data.

Minor, not patch: a call that used to succeed can now emit a `RuntimeWarning`
and return `receipt=None` where it previously returned a receipt object, and
`_resolve_receipt` gained an exception on a path that used to return `None`.

### Fixed
- **A missing receipt can no longer destroy the payload.** The download is
  burn-on-read: by the time the receipt is resolved the relay has already
  destroyed the blob, so the decrypted bytes are the only copy left. 3.2.x
  resolved the receipt BEFORE decrypting and raised on a 404 from the receipt
  route (an expired 15 minute window, a per-account cap, a relay restarted
  between the two calls), throwing that copy away over a missing proof of
  delivery. `receive()` now decrypts and returns the data first; a receipt that
  cannot be had becomes `receipt=None` plus a `RuntimeWarning`, with the reason
  on `GhostPipe.last_receipt_error`.
- **A receipt that could not be read is no longer silently `None`.** Every
  failure to decode `X-Paramant-Receipt` was swallowed by a bare
  `except Exception: pass`, so the caller could not tell "this transfer was
  never receipted" from "the proof of delivery went missing". Those cases are
  now warned about and recorded. A download the relay genuinely did not receipt
  still returns a plain `None`, with no warning, because there is nothing to
  fail about.
- **Response headers are looked up case-insensitively.** `_get` returns
  `dict(r.headers)`, which keeps whatever casing the server sent, so the old
  two-way `.get("x-paramant-receipt") or .get("X-Paramant-Receipt")` depended on
  the relay's exact casing and any proxy that normalised it broke the receipt.
- **A transport failure while fetching a receipt is wrapped.** `urllib` raises
  `URLError` for DNS failures, refused connections and timeouts; that now
  arrives as a `ReceiptError` rather than as a bare transport error.
- **CI: the conformance job installed an unsupported pqcrypto.** It ran
  `pip install pqcrypto cryptography`, unpinned, while the package declares
  `pqcrypto>=0.4,<1.0`. The day pqcrypto 1.0.0 was published that job began
  installing it, `paramant/crypto.py` raised its "pqcrypto >= 0.4 is required"
  ImportError, and 14 of 19 conformance tests went red on changes that touched
  no crypto. The job now installs `./sdk-py` itself, so the constraint has one
  home and cannot drift.

### Added
- **Support for the receipt-by-reference relay.** Relays from 2026-09 answer
  `GET /v2/outbound/:hash` with `X-Paramant-Receipt-Id`,
  `X-Paramant-Receipt-Hash` and `X-Paramant-Receipt-Url` instead of the ~18 KB
  inline receipt, which did not fit in a response header (over Node's 16 KB
  limit and over a default nginx proxy buffer). The SDK fetches
  `GET /v2/transfers/:receipt_id/receipt` with the same API key.
- **Receipts are verified against the hash the download advertised**, with
  `hmac.compare_digest`, before being decoded. Required when the relay sends a
  receipt id, so "send no hash" is not a way around verification, and applied to
  the inline header too when a hash comes with it, which is what the relay's
  deprecation opt-in sends.
- `ReceiptError`, a `GhostPipeError` subclass, and
  `GhostPipe.last_receipt_error`.

### Migration
`receive()` still returns `(data, receipt_or_None)` and still raises for a
failed download. What changes is that a receipt problem no longer raises out of
`receive()`: check `last_receipt_error`, or turn the `RuntimeWarning` into an
error with `warnings.simplefilter("error")`, if your flow requires proof of
delivery. Older relays that still send the inline header keep working
unchanged.

## [3.1.0] — 2026-05-23

Security release. Wire format unchanged (still v1, PQHB version `0x01`) — the relay
and existing tooling are unaffected. Only client behaviour changes.

### Fixed
- **Sender signatures are now verified (F1).** `receive()`/`_decrypt()` previously never
  called `sig_verify`, so a tampered signature or a swapped `sender_pub` was accepted
  silently. The signature is now verified before decryption and the blob is rejected
  (`SignatureError`) on failure.
- **Cross-SDK signing convention aligned (F3).** The signed message is now
  `CT_KEM || SENDER_PUB || NONCE || CIPHERTEXT || AAD` (matching sdk-js); 3.0.0 signed a
  different SHA-256 input, so py-signed blobs did not verify in sdk-js. The device
  fingerprint is now `SHA-256(kem_pub || sig_pub)` (binds the signing key) and is
  byte-identical to sdk-js. `/v2/pubkey` registers canonical `kem_pub`/`sig_pub` plus
  `kyber_pub`/`dsa_pub` aliases.
- **Receipts are verified client-side (F2).** `verify_receipt()` checks the relay's
  ML-DSA signature against a pinned `relay_identity_pub` instead of trusting the
  untrusted relay's `/v2/verify-receipt`.
- **Algorithm ids are no longer cosmetic (F4).** A `kem_id`/`sig_id` this build cannot
  perform now raises `UnsupportedAlgorithm` at construction instead of silently using
  ML-KEM-768/ML-DSA-65 while writing the requested id into the header.
- **Safe key zeroization (F5).** Secret material is held in `bytearray` and wiped in
  place; the 3.0.0 `ctypes.memset()` on immutable `bytes` (undefined behaviour) is gone.

### Added
- `receive(..., sender="device-id")` pins the sender's signing key (TOFU) to authenticate
  the origin; without it a warning is emitted.
- `GhostPipe(relay_identity_pub=...)` for client-side receipt verification.

### Migration
- Upgrade receivers and senders together. Existing keypairs are reused (no rotation).
- Existing local TOFU `known_keys` entries use the old fingerprint formula and will raise
  `FingerprintMismatchError` on next contact — re-`trust()` after out-of-band verification.

## [3.0.0] — 2026-04-24

### Breaking

- **Dropped `kyber-py` dependency.** Its own README explicitly warns against
  production use (not constant-time, timing-attack vulnerable). Replaced with
  [`pqcrypto`](https://pypi.org/project/pqcrypto/) (backbone-hq, Apache-2.0,
  thin CFFI over audited PQClean C code; pre-built wheels for Linux / macOS /
  Windows).
- **Removed the silent ECDH-P256 fallback.** v2.x quietly degraded to
  classical ECDH when `kyber-py` was absent while still advertising
  post-quantum protection. v3 raises `ImportError` at module load with a
  clear message instead.
- **Wire format v1** (`PQHB` magic, 10-byte header, KEM/SIG algorithm IDs,
  length-prefixed fields). See `docs/wire-format-v1.md`. v2 blobs
  (`0x02` legacy format) are not decryptable by v3.
- **Keypair file layout**: v2 `*.keypair.json` files without `ml_kem_pub` /
  `ml_dsa_pub` are renamed to `*.v2.bak` on first use and a fresh v3 keypair
  is generated.

### Added

- `paramant.wire_format` — byte-exact encoder / decoder matching
  `docs/wire-format-v1.md`. Test vectors reproduced:
    - signed:    `sha256=002b4f6aad4fa992804a3e94c46d514b4f842e9f5c283f7a31d7c76722d0476a`
    - anonymous: `sha256=46bce75b12e90ed312420fafcbead4108d55aa25273aee3ce4f2b4f61b3d19ef`
- `paramant.crypto` — pqcrypto wrappers for ML-KEM-768 and ML-DSA-65 plus
  AES-256-GCM with the spec's header-based AAD.
- `paramant.capabilities` — `/v2/capabilities` client + `negotiate()` that
  fetches and validates wire version and algorithm support before the first
  send. Unsupported combination raises `CapabilityMismatch`. No silent
  fallback.
- `GhostPipe(..., kem_id=, sig_id=, negotiate_on_init=)` constructor
  parameters for per-client algorithm override.
- `GhostPipe.capabilities()` — returns the relay's `RelayCapabilities`.
- CLI: `paramant-sdk capabilities --key ... --relay ...` prints the relay's
  advertised algorithms.

### Changed

- Default algorithms are now ML-KEM-768 (`0x0002`) + ML-DSA-65 (`0x0002`).
  Anonymous blobs use `sig_id=0x0000`.
- README rewritten to describe real v3 behaviour. v2 marketing claim of
  "ML-KEM-768" — which was only true when users happened to have `kyber-py`
  installed and never verified — removed.

### Required upgrades

1. `pip install 'paramant-sdk>=3'`
2. Environment must support `pqcrypto` wheels (Linux / macOS / Windows).
3. In-flight v2 blobs need to be re-encrypted under v3 (wire format
   incompatibility).

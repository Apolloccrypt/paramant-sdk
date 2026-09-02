# Changelog

## 3.3.0 - 2026-09-02

Version-only release, cut in lockstep with sdk-py 3.3.0. No behaviour, API or
wire-format change in this package; both SDKs publish from one tag, and the
release workflow requires `sdk-js/package.json` to carry the tag version
exactly, so the JS package moves with the Python one.

### Relay compatibility

sdk-py 3.3.0 exists because relays from 2026-09 no longer put the whole signed
delivery receipt in the `X-Paramant-Receipt` response header (~18 KB, over
Node's 16 KB header limit and over a default nginx proxy buffer). They send a
reference instead, plus `X-Paramant-Receipt-Deprecated`, and the full receipt is
fetched from `GET /v2/transfers/:receipt_id/receipt` with the same API key,
valid for 15 minutes.

**That change does not affect this SDK, because this SDK never read the header.**
`httpRequest()` returns `{ status, body }` and drops response headers entirely,
so `receive()` has never surfaced a delivery receipt on any relay version. There
was nothing to break and nothing to migrate.

- Works against relay 3.1.0+ (receipt by reference) and against older relays,
  identically.
- The opt-in `PARAMANT_INLINE_RECEIPT_HEADER` on an older relay, which restores
  the inline header for old clients, changes nothing here either.

### Known gap (not fixed in this release)

`verifyReceipt()` verifies a receipt the caller already has, but nothing in this
SDK obtains one: `receive()` returns only the decrypted bytes. A JS caller needs
the receipt out of band (sdk-py, or a direct call to the relay). Surfacing the
receipt from `receive()` — fetching it by reference, checking its sha3-256, and
never letting a missing receipt cost the payload, as sdk-py 3.3.0 does — is a
separate change to the HTTP layer and is not part of this release.

## 3.2.0 - 2026-05-28

### Deprecated
- **`sendAnonymous()` is deprecated.** The anonymous tier is being retired.
  The `/v2/anon-inbound` relay endpoint will be removed in a future major
  release. Callers will see a one-shot `console.warn` per process and a
  `Deprecation: true` response header from the relay. Migrate to `send()`
  for authenticated, ML-DSA-65 signed transfers with CT-log proof of origin.
  No wire-format change; no other API behaviour changed in this release.

## 3.1.0 — 2026-05-23

Security release. Wire format unchanged (still v1) — relay and existing tooling unaffected.

### Fixed
- **Cross-SDK interop with sdk-py (F3).** sdk-py ≤ 3.0.0 signed a different message and
  never verified, so py↔js signed transfers were broken. The signing convention
  (`CT_KEM || SENDER_PUB || NONCE || CIPHERTEXT || AAD`) and fingerprint
  (`SHA-256(kem_pub || sig_pub)`, first 10 bytes) are now byte-identical across both SDKs.
  `registerPubkeys()` also sends `kyber_pub`/`dsa_pub` aliases.
- **Receipts verified client-side (F2).** `verifyReceipt()` checks the relay's ML-DSA
  signature against a pinned `relayIdentityPub` instead of trusting `/v2/verify-receipt`.
  (Pass `{ allowRelayFallback: true }` to keep the old behaviour for debugging.)

### Added
- `receive(hash, { sender })` pins the sender's signing key (TOFU) to authenticate origin;
  without it a warning is logged.
- `GhostPipe({ relayIdentityPub })` for client-side receipt verification.
- `computeFingerprint` is now exported.
- A test suite for the security fixes; `npm test` script fixed (`node --test`) and
  `test/` is now shipped in the package.

### Note
Signature verification on `_decrypt` (rejecting tampered signatures) was already present
in this branch; 3.1.0 adds sender-key pinning and aligns the convention with sdk-py.

## 3.0.0 — 2026-04-24

**Breaking release.** See README for full migration notes.

### Real post-quantum crypto

- Added `@noble/post-quantum` `^0.6.1` as a runtime dependency.
- Replaced empty-array KEM placeholders (`new Uint8Array(0)`) and the
  ECDH-P256 fallback with real `ml_kem768.encapsulate` / `.decapsulate`.
- Signing is wired up to `ml_dsa65.sign` / `.verify`. The default `sigId`
  is `0x0002` (ML-DSA-65). Pass `sigId: SIG.NONE` (`0x0000`) for anonymous
  blobs with no signature section.
- New device keypair format (`version: 3`) stores real ML-KEM-768 and
  ML-DSA-65 material. Older 2.x keypairs are ignored.

### Wire format v1

- Removed the legacy v0 packet structure.
- Added `src/wire-format.js` with `encode`, `decode`, `buildAAD`, `isV1`,
  bit-exact against the test vectors in `docs/wire-format-v1.md`:
  - signed:    `002b4f6aad4fa992804a3e94c46d514b4f842e9f5c283f7a31d7c76722d0476a`
  - anonymous: `46bce75b12e90ed312420fafcbead4108d55aa25273aee3ce4f2b4f61b3d19ef`
- AES-256-GCM AAD now binds the 10-byte header plus a 4-byte chunk index.

### Capabilities negotiation

- Added `src/capabilities.js` with `fetchCapabilities(relayUrl)`.
- `GhostPipe` queries `/v2/capabilities` before the first `send()` and
  validates `wire_version`, `kemId`, `sigId` against the advertised set.
  Mismatches throw `UnsupportedAlgorithmError` — no silent fallback.
- New `checkCapabilities` constructor option (default: `true`).

### API changes

- `GhostPipeOptions` gained `kemId`, `sigId`, `checkCapabilities`.
- New public error class: `SignatureError`.
- New public method: `sendAnonymous(data, recipientKemPubHex, opts)`
  that posts a v1 blob (`sigId=0x0000`) to `/v2/anon-inbound`.
- Keypair fields renamed: `kyber_pub` → `kem_pub`, `kyber_priv` → `kem_priv`.
- Re-exports: `wireEncode`, `wireDecode`, `buildAAD`, `isV1`,
  `fetchCapabilities`, `KEM`, `SIG`, `WIRE_VERSION`.

### Documentation

- README rewritten. Removed the 2.x claim of ML-KEM-768 support (which was
  not actually wired up in the code path) and replaced it with an accurate
  description of the real crypto layer.

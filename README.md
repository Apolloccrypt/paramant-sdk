# Paramant SDK

Post-quantum file-relay clients for [Paramant](https://paramant.app). Send and receive end-to-end encrypted files where the relay only ever holds ciphertext, in RAM, and burns it on read.

Two implementations, one wire format:

- JavaScript / Node: [`sdk-js/`](sdk-js/) (npm: [`paramant-sdk`](https://www.npmjs.com/package/paramant-sdk))
- Python: [`sdk-py/`](sdk-py/) (PyPI: [`paramant-sdk`](https://pypi.org/project/paramant-sdk/))

Crypto: ML-KEM-768 (FIPS 203) for key encapsulation and ML-DSA-65 (FIPS 204) for signatures are the default, with AES-256-GCM and HKDF-SHA256 for the payload envelope. Wire format v1 (PQHB magic). Additional algorithms (the "extended" set) are opt-in and negotiated against the relay's `/v2/capabilities`; the SDKs never silently substitute an algorithm the relay does not advertise.

## Wire-format spec

The canonical wire-format v1 specification lives with the relay and core, not in this repo: [docs/wire-format-v1.md](https://github.com/Apolloccrypt/paramant-relay/blob/main/docs/wire-format-v1.md). Both SDKs and the relay implement that one contract.

## Conformance

[`tests/conformance/`](tests/conformance/) is a cross-implementation suite. It checks that sdk-js, sdk-py, and the relay/core crypto each reproduce the spec's own test vectors byte for byte, with no mocks. Run it from the repo root:

    node --test tests/conformance/conformance.test.mjs

It needs the three real stacks present: sdk-js (`cd sdk-js && npm install`), a Python venv with `pqcrypto` and `cryptography`, and optionally `@paramant/core`. The relay adapter is skipped with a message when the relay repo is not alongside, so it never passes on a missing implementation.

## License

Apache-2.0. See [LICENSE](LICENSE).

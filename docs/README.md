# docs/

SDK-specific documentation lives here. For the product and the full API
reference, see [paramant.app/docs](https://paramant.app/docs).

The canonical **wire-format v1** specification is owned by the relay and crypto
core, not this repo — the relay's decoder is authoritative. See
[`docs/wire-format-v1.md`](https://github.com/Apolloccrypt/paramant-relay/blob/main/docs/wire-format-v1.md)
in `paramant-relay`. These SDKs implement that one contract; the conformance
suite in [`tests/conformance/`](../tests/conformance/) pins them to it.

Per-language usage:

- JavaScript / Node: [`../sdk-js/README.md`](../sdk-js/README.md)
- Python: [`../sdk-py/README.md`](../sdk-py/README.md)

"""
The delivery receipt moved out of the response header, and this SDK has to work
against relays on both sides of that move.

WHY. Relays up to 2026-09 answered GET /v2/outbound/:hash with the whole signed
receipt in X-Paramant-Receipt. That payload is about 18 KB: over Node's 16 KB
header limit and over a default nginx proxy buffer, so it could not stay there.
Newer relays send a receipt id plus the sha3-256 of the bytes, and the receipt
comes from GET /v2/transfers/:receipt_id/receipt.

The part that makes this a security-relevant change and not a plumbing one:
before 3.2.1 this SDK turned every failure to read that header into
`receipt = None`, silently. A delivery proof that quietly becomes nothing is
indistinguishable from a transfer that was never receipted, so against a new
relay the old SDK would have kept working while proving nothing. That silence
is gone: if the relay says a receipt exists and it cannot be produced and
verified, `_resolve_receipt` raises `ReceiptError`.
"""
import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from paramant_sdk import GhostPipe, ReceiptError

API_KEY = "pgp_testkey_0123456789abcdef"

RECEIPT = {
    "blob_hash": "a3f2" * 16,
    "sector": "health",
    "retrieved_at": "2026-09-02T09:00:00.000Z",
    "relay_id": "relay.paramant.app",
    "burn_confirmed": True,
    "inclusion_proof": {"leaf_hash": "d4e1" * 16, "audit_path": [], "root": "c7a9" * 16},
    "signature": "ML-DSA-65-base64-would-go-here",
}
RECEIPT_B64 = base64.urlsafe_b64encode(json.dumps(RECEIPT).encode()).decode().rstrip("=")
RECEIPT_HASH = "sha3-256:" + hashlib.sha3_256(RECEIPT_B64.encode()).hexdigest()
RECEIPT_ID = "b7" * 16


def _relay(routes: dict):
    """An in-process relay that serves the given path -> (status, body) map.

    Records the API key it was called with, so a test can prove the receipt
    fetch is authenticated the same way the download was.
    """
    seen = {"keys": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["keys"].append(self.headers.get("X-Api-Key"))
            if self.path in routes:
                status, body = routes[self.path]
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, *a, **kw):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}", seen


def _gp(relay, home_tmp):
    return GhostPipe(API_KEY, "device-a", relay=relay, negotiate_on_init=False)


@pytest.fixture
def home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# -- the old relay, which must keep working ----------------------------------

def test_inline_header_is_still_accepted(home_tmp):
    gp = _gp("https://offline.invalid", home_tmp)
    got = gp._resolve_receipt({"X-Paramant-Receipt": RECEIPT_B64})
    assert got == RECEIPT


def test_header_lookup_is_case_insensitive(home_tmp):
    # _get returns dict(r.headers), which keeps the server's casing. Header
    # names are case-insensitive on the wire and a proxy may rewrite them.
    gp = _gp("https://offline.invalid", home_tmp)
    assert gp._resolve_receipt({"x-paramant-receipt": RECEIPT_B64}) == RECEIPT
    assert gp._resolve_receipt({"X-PARAMANT-RECEIPT": RECEIPT_B64}) == RECEIPT


# -- the new relay ------------------------------------------------------------

def test_reference_is_fetched_with_the_same_api_key(home_tmp):
    body = json.dumps({"ok": True, "receipt": RECEIPT_B64, "receipt_hash": RECEIPT_HASH}).encode()
    srv, url, seen = _relay({f"/v2/transfers/{RECEIPT_ID}/receipt": (200, body)})
    try:
        gp = _gp(url, home_tmp)
        got = gp._resolve_receipt({
            "X-Paramant-Receipt-Id": RECEIPT_ID,
            "X-Paramant-Receipt-Hash": RECEIPT_HASH,
            "X-Paramant-Receipt-Url": f"/v2/transfers/{RECEIPT_ID}/receipt",
        })
        assert got == RECEIPT
        assert seen["keys"] == [API_KEY], "the receipt is fetched with the key that made the download"
    finally:
        srv.shutdown()


def test_reference_without_a_url_header_falls_back_to_the_documented_path(home_tmp):
    body = json.dumps({"ok": True, "receipt": RECEIPT_B64, "receipt_hash": RECEIPT_HASH}).encode()
    srv, url, _ = _relay({f"/v2/transfers/{RECEIPT_ID}/receipt": (200, body)})
    try:
        gp = _gp(url, home_tmp)
        assert gp._resolve_receipt({"X-Paramant-Receipt-Id": RECEIPT_ID}) == RECEIPT
    finally:
        srv.shutdown()


# -- the silence that had to go ----------------------------------------------

def test_an_unfetchable_receipt_raises_instead_of_returning_none(home_tmp):
    # The receipt window is short. Missing it must be an error the caller sees,
    # not a delivery proof that quietly evaporates.
    srv, url, _ = _relay({})
    try:
        gp = _gp(url, home_tmp)
        with pytest.raises(ReceiptError, match="404"):
            gp._resolve_receipt({"X-Paramant-Receipt-Id": RECEIPT_ID})
    finally:
        srv.shutdown()


def test_a_tampered_receipt_raises(home_tmp):
    # The download promised a hash over the exact bytes. If the fetched bytes do
    # not match, something sat in between.
    other = base64.urlsafe_b64encode(json.dumps({**RECEIPT, "burn_confirmed": False}).encode()).decode().rstrip("=")
    body = json.dumps({"ok": True, "receipt": other, "receipt_hash": RECEIPT_HASH}).encode()
    srv, url, _ = _relay({f"/v2/transfers/{RECEIPT_ID}/receipt": (200, body)})
    try:
        gp = _gp(url, home_tmp)
        with pytest.raises(ReceiptError, match="hash mismatch"):
            gp._resolve_receipt({
                "X-Paramant-Receipt-Id": RECEIPT_ID,
                "X-Paramant-Receipt-Hash": RECEIPT_HASH,
            })
    finally:
        srv.shutdown()


def test_an_undecodable_inline_header_raises(home_tmp):
    gp = _gp("https://offline.invalid", home_tmp)
    with pytest.raises(ReceiptError):
        gp._resolve_receipt({"X-Paramant-Receipt": "not-base64-of-any-json!!"})


def test_no_receipt_advertised_is_still_none(home_tmp):
    # An anonymous drop, or a blob with no CT entry, is genuinely unreceipted.
    # There is nothing to fail about, so this stays None rather than raising.
    gp = _gp("https://offline.invalid", home_tmp)
    assert gp._resolve_receipt({"X-Paramant-Burned": "true"}) is None

"""
The delivery receipt moved out of the response header, and this SDK has to work
against relays on both sides of that move WITHOUT ever costing the caller the
payload.

WHY THE RELAY CHANGED. Relays up to 2026-09 answered GET /v2/outbound/:hash with
the whole signed receipt in X-Paramant-Receipt. That payload is about 18 KB:
over Node's 16 KB header limit and over a default nginx proxy buffer, so it
could not stay there. Newer relays send a receipt id plus the sha3-256 of the
bytes, and the receipt comes from GET /v2/transfers/:receipt_id/receipt.

WHY THIS IS DELICATE. That download is BURN ON READ. By the time the SDK looks
at the receipt, the relay has already destroyed the blob, so the bytes in hand
are the only copy left in the world. A receipt fetch that raises, and takes the
decrypted payload with it, trades an unrecoverable plaintext for a missing proof
of delivery. Every test here therefore goes through receive() rather than
through _resolve_receipt, because the ordering inside receive() IS the property:
decrypt first, return the data, and let a missing receipt be a warning.

The other half is the one that was there before: an unreadable receipt must not
be silently indistinguishable from a transfer that had none. That is what
last_receipt_error and the RuntimeWarning are for.
"""
import base64
import hashlib
import json

import pytest

from paramant_sdk import GhostPipe, ReceiptError

API_KEY = "pgp_testkey_0123456789abcdef"
RECEIPT_ID = "b7" * 16
RECEIPT_PATH = f"/v2/transfers/{RECEIPT_ID}/receipt"

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

PLAINTEXT = b"the payload that must survive a missing receipt" * 11


@pytest.fixture
def home_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _gp(home_tmp, device="receiver-001"):
    return GhostPipe(api_key=API_KEY, device=device, relay="https://offline.invalid",
                     negotiate_on_init=False)


def _blob_for(gp) -> bytes:
    """A real v1 blob this GhostPipe can decrypt, so receive() runs for real."""
    kem_pub = bytes.fromhex(gp._load_keypair()["ml_kem_pub"])
    padded, _ = gp._encrypt(PLAINTEXT, kem_pub, pad_block=64 * 1024)
    return padded


def _wire(gp, download_headers: dict, receipt_response=None):
    """Point gp at a fake relay: one burn-on-read download, one receipt route.

    receipt_response is (status, body_bytes) or None for "route does not exist".
    Records the paths requested so a test can prove what was and was not called.
    """
    blob = _blob_for(gp)
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        if path.startswith("/v2/outbound/"):
            return 200, blob, dict(download_headers)
        if path == RECEIPT_PATH:
            if receipt_response is None:
                return 404, b'{"error":"Not found. Expired, or never issued."}', {}
            return receipt_response[0], receipt_response[1], {}
        raise AssertionError(f"unexpected request to {path}")

    gp._get = fake_get
    return calls


def _ok_body(b64=RECEIPT_B64, h=RECEIPT_HASH):
    return 200, json.dumps({"ok": True, "receipt": b64, "receipt_hash": h}).encode()


REFERENCE_HEADERS = {
    "X-Paramant-Burned": "true",
    "X-Paramant-Receipt-Id": RECEIPT_ID,
    "X-Paramant-Receipt-Hash": RECEIPT_HASH,
    "X-Paramant-Receipt-Url": RECEIPT_PATH,
}


# -- the blocker: a missing receipt must never destroy the payload ------------

def test_a_404_on_the_receipt_route_does_not_cost_the_payload(home_tmp):
    # The window is 15 minutes, capped per account, and a relay without redis
    # loses every outstanding receipt on restart. All three answer 404, and the
    # blob is already burned by then. The data comes back regardless.
    gp = _gp(home_tmp)
    _wire(gp, REFERENCE_HEADERS, receipt_response=None)
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        data, receipt = gp.receive("a3f2" * 16)
    assert data == PLAINTEXT, "the only copy of the plaintext in the world came back"
    assert receipt is None
    assert isinstance(gp.last_receipt_error, ReceiptError), "and the reason is inspectable"
    assert "404" in str(gp.last_receipt_error)


def test_an_unreachable_receipt_route_does_not_cost_the_payload(home_tmp):
    # urllib raises URLError for DNS failures, refused connections and timeouts.
    gp = _gp(home_tmp)
    blob = _blob_for(gp)

    import urllib.error

    def fake_get(path, params=None):
        if path.startswith("/v2/outbound/"):
            return 200, blob, dict(REFERENCE_HEADERS)
        raise urllib.error.URLError("connection refused")

    gp._get = fake_get
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        data, receipt = gp.receive("a3f2" * 16)
    assert data == PLAINTEXT
    assert receipt is None
    assert isinstance(gp.last_receipt_error, ReceiptError), "a transport error is wrapped, not raw"
    assert "connection refused" in str(gp.last_receipt_error)


def test_a_tampered_receipt_does_not_cost_the_payload_either(home_tmp):
    other = base64.urlsafe_b64encode(
        json.dumps({**RECEIPT, "burn_confirmed": False}).encode()).decode().rstrip("=")
    gp = _gp(home_tmp)
    _wire(gp, REFERENCE_HEADERS, receipt_response=_ok_body(b64=other))
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        data, receipt = gp.receive("a3f2" * 16)
    assert data == PLAINTEXT
    assert receipt is None, "a receipt that fails its hash is refused, not returned"
    assert "hash mismatch" in str(gp.last_receipt_error)


def test_the_receipt_is_fetched_after_the_decrypt_not_before(home_tmp):
    # Ordering is the whole fix, so it is asserted directly and not only through
    # its consequences.
    gp = _gp(home_tmp)
    calls = _wire(gp, REFERENCE_HEADERS, receipt_response=_ok_body())
    data, receipt = gp.receive("a3f2" * 16)
    assert data == PLAINTEXT
    assert receipt == RECEIPT
    assert calls[0].startswith("/v2/outbound/") and calls[1] == RECEIPT_PATH
    assert gp.last_receipt_error is None


# -- both relay shapes --------------------------------------------------------

def test_the_new_relay_shape_yields_the_receipt(home_tmp):
    gp = _gp(home_tmp)
    _wire(gp, REFERENCE_HEADERS, receipt_response=_ok_body())
    data, receipt = gp.receive("a3f2" * 16)
    assert (data, receipt) == (PLAINTEXT, RECEIPT)


def test_the_old_inline_header_still_works(home_tmp):
    gp = _gp(home_tmp)
    calls = _wire(gp, {"X-Paramant-Burned": "true", "X-Paramant-Receipt": RECEIPT_B64})
    data, receipt = gp.receive("a3f2" * 16)
    assert (data, receipt) == (PLAINTEXT, RECEIPT)
    assert calls == [f"/v2/outbound/{'a3f2' * 16}"], "an inline receipt costs no second request"


def test_header_lookup_is_case_insensitive(home_tmp):
    # _get returns dict(r.headers), which keeps the server's casing. Header
    # names are case-insensitive on the wire and a proxy may rewrite them.
    gp = _gp(home_tmp)
    _wire(gp, {"x-paramant-receipt": RECEIPT_B64})
    _, receipt = gp.receive("a3f2" * 16)
    assert receipt == RECEIPT


def test_no_receipt_advertised_is_none_and_no_warning(home_tmp):
    # An anonymous drop, or a blob with no CT entry, is genuinely unreceipted.
    # There is nothing to fail about, so no warning and no recorded error.
    gp = _gp(home_tmp)
    calls = _wire(gp, {"X-Paramant-Burned": "true"})
    import warnings as _w
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        data, receipt = gp.receive("a3f2" * 16)
    assert (data, receipt) == (PLAINTEXT, None)
    assert gp.last_receipt_error is None
    assert not [c for c in caught if "receipt" in str(c.message)]
    assert len(calls) == 1


# -- verification rules -------------------------------------------------------

def test_a_receipt_id_without_a_hash_is_an_error(home_tmp):
    # Otherwise "send no hash" is the easy way around verification.
    gp = _gp(home_tmp)
    headers = {k: v for k, v in REFERENCE_HEADERS.items() if k != "X-Paramant-Receipt-Hash"}
    _wire(gp, headers, receipt_response=(200, json.dumps({"ok": True, "receipt": RECEIPT_B64}).encode()))
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        data, receipt = gp.receive("a3f2" * 16)
    assert data == PLAINTEXT
    assert receipt is None
    assert "no X-Paramant-Receipt-Hash" in str(gp.last_receipt_error)


def test_the_inline_header_is_verified_when_a_hash_comes_with_it(home_tmp):
    # The deprecation opt-in sends BOTH the inline header and the reference. That
    # path is the one an operator turns on for OLD clients, so it must not be the
    # only unverified way to get a receipt.
    tampered = base64.urlsafe_b64encode(
        json.dumps({**RECEIPT, "burn_confirmed": False}).encode()).decode().rstrip("=")
    gp = _gp(home_tmp)
    _wire(gp, {**REFERENCE_HEADERS, "X-Paramant-Receipt": tampered})
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        _, receipt = gp.receive("a3f2" * 16)
    assert receipt is None
    assert "hash mismatch" in str(gp.last_receipt_error)


def test_an_unknown_hash_algorithm_is_refused(home_tmp):
    gp = _gp(home_tmp)
    _wire(gp, {**REFERENCE_HEADERS, "X-Paramant-Receipt-Hash": "md5:d41d8cd9"},
          receipt_response=_ok_body(h="md5:d41d8cd9"))
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        _, receipt = gp.receive("a3f2" * 16)
    assert receipt is None
    assert "Unsupported receipt hash" in str(gp.last_receipt_error)


def test_last_receipt_error_is_reset_per_call(home_tmp):
    # It must never describe an older call.
    gp = _gp(home_tmp)
    _wire(gp, REFERENCE_HEADERS, receipt_response=None)
    with pytest.warns(RuntimeWarning, match="receipt could not be obtained"):
        gp.receive("a3f2" * 16)
    assert gp.last_receipt_error is not None
    _wire(gp, REFERENCE_HEADERS, receipt_response=_ok_body())
    _, receipt = gp.receive("a3f2" * 16)
    assert receipt == RECEIPT
    assert gp.last_receipt_error is None

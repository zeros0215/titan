import json
import tempfile
import unittest
from pathlib import Path
from broker.kiwoom.paper_market import _market_session_event, load_market_session_state

class KiwoomPaperMarketTest(unittest.TestCase):
    def test_plain_ping_is_echoed_before_json_parsing(self):
        class Socket:
            def __init__(self): self.messages = iter(("", "PING", '{"trnm":"LOGIN","return_code":0}')); self.sent = []
            def recv(self): return next(self.messages)
            def send(self, value): self.sent.append(value)
        from broker.kiwoom.paper_market import KiwoomPaperMarketSessionClient
        socket = Socket()
        message = KiwoomPaperMarketSessionClient._receive(socket, 1)
        self.assertEqual("LOGIN", message["trnm"])
        self.assertEqual(["PING"], socket.sent)

    def test_market_open_event_uses_official_215_code(self):
        event = _market_session_event({"data":[{"type":"0s","values":{"215":"3"}}]})
        self.assertTrue(event.regular_session_open)
        self.assertEqual("3", event.status_code)

    def test_other_status_is_fail_closed(self):
        event = _market_session_event({"data":[{"type":"0s","values":{"215":"4"}}]})
        self.assertFalse(event.regular_session_open)

    def test_fresh_stock_trade_is_regular_session_evidence(self):
        event = _market_session_event({"data":[{"type":"0B","values":{"20":"114955","10":"+271000","15":"3"}}]})
        self.assertTrue(event.regular_session_open)
        self.assertEqual("TRADE_0B", event.status_code)

    def test_incomplete_trade_is_not_session_evidence(self):
        self.assertIsNone(_market_session_event({"data":[{"type":"0B","values":{"20":"114955","10":"271000","15":"0"}}]}))

    def test_missing_or_invalid_state_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.assertFalse(load_market_session_state(path)["regular_session_open"])
            path.write_text(json.dumps({"regular_session_open":"yes"}), encoding="utf-8")
            self.assertFalse(load_market_session_state(path)["regular_session_open"])

if __name__ == "__main__": unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from price_history.krx_adjustment import KrxAdjustedPriceCompiler


def row(day, close, shares):
    return (
        "Stock", "KOSPI", day, close, close, close, close, 1000, shares
    )


class KrxAdjustmentTest(unittest.TestCase):
    @staticmethod
    def _snapshot(root, day, close, shares):
        issue = {
            "ISU_SRT_CD": "000001", "ISU_ABBRV": "Stock",
            "SECUGRP_NM": "STOCK", "KIND_STKCERT_TP_NM": "COMMON STOCK",
            "SECT_TP_NM": "NORMAL", "LIST_DD": "20240101",
        }
        price = {
            "ISU_CD": "000001", "ISU_NM": "Stock", "BAS_DD": day,
            "TDD_OPNPRC": str(close), "TDD_HGPRC": str(close),
            "TDD_LWPRC": str(close), "TDD_CLSPRC": str(close),
            "ACC_TRDVOL": "1000", "LIST_SHRS": str(shares),
        }
        for directory, payload in (
            (root / "universe", issue), (root / "price", price)
        ):
            directory.mkdir(exist_ok=True)
            for market in ("KOSPI", "KOSDAQ"):
                rows = [payload] if market == "KOSPI" else []
                (directory / f"{day}_{market}.json").write_text(
                    json.dumps({"OutBlock_1": rows}), encoding="utf-8"
                )

    @staticmethod
    def _manifests(root, end):
        for name in ("universe", "price"):
            (root / name / "collection_manifest.json").write_text(
                json.dumps({
                    "coverage_start": "2024-01-01", "coverage_end": end,
                    "raw_sha256": f"{name}-{end}",
                }),
                encoding="utf-8",
            )

    def test_normalizes_no_trade_ohlc_to_close(self):
        values = (
            "005930", "Stock", "KOSPI", "2024-01-01T00:00:00",
            0.0, 0.0, 0.0, 100.0, 0, 1000,
        )

        normalized = KrxAdjustedPriceCompiler._normalize_no_trade(values)

        self.assertEqual((100.0, 100.0, 100.0, 100.0), normalized[4:8])

    def test_detects_split_and_adjusts_only_prior_prices(self):
        rows = [
            row("2024-01-01T00:00:00", 100.0, 100),
            row("2024-01-02T00:00:00", 20.0, 500),
            row("2024-01-03T00:00:00", 22.0, 500),
        ]
        compiler = KrxAdjustedPriceCompiler()

        actions, unresolved = compiler._events(rows)
        factors = compiler._backward_factors(rows, actions)

        self.assertEqual(1, len(actions))
        self.assertEqual([], unresolved)
        self.assertAlmostEqual(0.2, factors[0][0])
        self.assertAlmostEqual(1.0, factors[1][0])
        self.assertAlmostEqual(1.0, factors[2][0])

    def test_does_not_adjust_unexplained_price_jump(self):
        rows = [
            row("2024-01-01T00:00:00", 100.0, 100),
            row("2024-01-02T00:00:00", 200.0, 100),
        ]

        actions, unresolved = KrxAdjustedPriceCompiler()._events(rows)

        self.assertEqual([], actions)
        self.assertEqual(1, len(unresolved))
        self.assertEqual(
            "UNEXPLAINED_PRICE_DISCONTINUITY",
            unresolved[0]["classification"],
        )

    def test_quarantines_61_sessions_after_unresolved_jump(self):
        rows = [
            row(f"2024-01-{index + 1:02d}T00:00:00", 100.0, 100)
            for index in range(70)
        ]
        unresolved = [{
            "index": 2,
            "classification": "UNEXPLAINED_PRICE_DISCONTINUITY",
        }]

        intervals = KrxAdjustedPriceCompiler._quarantines(
            rows, unresolved
        )

        self.assertEqual(rows[2][2], intervals[0]["start"])
        self.assertEqual(rows[62][2], intervals[0]["end"])

    def test_incremental_compile_appends_without_mutating_active_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._snapshot(root, "20240101", 100, 100)
            self._snapshot(root, "20240102", 101, 100)
            self._manifests(root, "2024-01-02")
            compiler = KrxAdjustedPriceCompiler()
            compiler.compile(root / "universe", root / "price", root / "active")
            active_before = (root / "active" / "000001.json").read_bytes()

            self._snapshot(root, "20240103", 102, 100)
            self._manifests(root, "2024-01-03")
            manifest = compiler.compile(
                root / "universe", root / "price", root / "staging",
                base_price_dir=root / "active",
            )

            active = json.loads((root / "active" / "000001.json").read_text())
            staging = json.loads((root / "staging" / "000001.json").read_text())
            self.assertEqual(active_before, (root / "active" / "000001.json").read_bytes())
            self.assertEqual(2, len(active["candles"]))
            self.assertEqual(3, len(staging["candles"]))
            self.assertEqual(1, manifest["incremental_rows"])
            self.assertEqual("2024-01-02", manifest["incremental_from"])


if __name__ == "__main__":
    unittest.main()

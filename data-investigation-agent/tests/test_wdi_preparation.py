"""Synthetic preflight doubles only; no WDI source data or golden answers here."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.provenance import PUBLIC_SNAPSHOTS

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wdi_preparation_test", ROOT / "examples/prepare_wdi_smoke.py")
wdi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wdi)


class WDIPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "synthetic-source/provenance/raw"
        self.raw.mkdir(parents=True)
        observations, access, populations, countries = [], [], [], []
        for index, country in enumerate(wdi.COUNTRIES):
            countries.append([country, country + " test country", "Test region"])
            for year in wdi.YEARS:
                value, population = 50 + index / 10 + (year - 2019) / 100, 100000 + index
                access.append([country, year, value])
                populations.append([country, year, population])
                for indicator, number in ((wdi.ACCESS, value), (wdi.POPULATION, population)):
                    observations.append({"indicator": {"id": indicator}, "countryiso3code": country,
                                         "date": str(year), "value": number})
        self.documents = {
            "observations.json": [{"pages": 1, "test_only": "SYNTHETIC"}, observations],
            "countries.json": [{"pages": 1}, [{"id": code, "name": name, "region": {"id": "TEST", "value": region}}
                                             for code, name, region in countries]],
            "electricity_indicator.json": [{"pages": 1}, [{"id": wdi.ACCESS}]],
            "population_indicator.json": [{"pages": 1}, [{"id": wdi.POPULATION}]],
        }
        self.csv_hashes = {}
        for name, header, rows in (
            ("electricity_access.csv", ["country_code", "year", "access_pct"], access),
            ("population.csv", ["country_code", "year", "population"], populations),
            ("countries.csv", ["country_code", "country_name", "region_name"], countries),
        ):
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(header); writer.writerows(sorted(rows))
            self.csv_hashes[name] = hashlib.sha256(stream.getvalue().encode()).hexdigest()
        self.write_sources()

    def tearDown(self):
        self.temp.cleanup()

    def write_sources(self):
        self.source_hashes, records = {}, {}
        for name, value in self.documents.items():
            data = (json.dumps(value) + "\n").encode()
            (self.raw / name).write_bytes(data)
            self.source_hashes[name] = hashlib.sha256(data).hexdigest()
            records[name] = {"url": wdi.SOURCE_URLS[name], "sha256": self.source_hashes[name],
                             "bytes": len(data), "api_header": value[0],
                             "retrieved_at_utc": wdi.SOURCE_RETRIEVED_AT[name]}
        manifest = (json.dumps({"files": records}) + "\n").encode()
        license_text = b"SYNTHETIC UNIT TEST ONLY; not actual World Bank data.\n"
        (self.raw.parent / "source_manifest.json").write_bytes(manifest)
        (self.raw.parent.parent / "LICENSE_DATA.md").write_bytes(license_text)
        self.record_hashes = {"source_manifest.json": hashlib.sha256(manifest).hexdigest(),
                              "LICENSE_DATA.md": hashlib.sha256(license_text).hexdigest()}

    def pins(self):
        import contextlib
        stack = contextlib.ExitStack()
        for actual, replacement in ((wdi.SOURCE_SHA256, self.source_hashes),
                                    (wdi.CSV_SHA256, self.csv_hashes), (wdi.RECORD_SHA256, self.record_hashes)):
            stack.enter_context(patch.dict(actual, replacement, clear=True))
        return stack

    def test_real_pins_reject_synthetic_substitution_before_output_or_admission(self):
        self.assertTrue(all(len(v) == 64 for v in [*wdi.SOURCE_SHA256.values(), *wdi.CSV_SHA256.values()]))
        with self.assertRaisesRegex(ValueError, "Source hash differs"):
            wdi.prepare(self.raw, self.root / "rejected")
        self.assertFalse((self.root / "rejected").exists())
        self.assertEqual(PUBLIC_SNAPSHOTS, {})

    def test_preparation_separates_sources_and_requires_checked_explicit_admission(self):
        before = {p.name: p.read_bytes() for p in self.raw.iterdir()}
        with self.pins(), patch.dict(PUBLIC_SNAPSHOTS, {}, clear=True), \
                patch("socket.socket", side_effect=AssertionError("No network")):
            prepared = wdi.prepare(self.raw, self.root / "prepared")
            bundle = Path(prepared["bundle"])
            self.assertFalse(prepared["automatically_admitted"])
            self.assertEqual(PUBLIC_SNAPSHOTS, {})
            self.assertEqual(len(list(bundle.iterdir())), 7)
            self.assertFalse((bundle / "objective_contract.json").exists())
            self.assertFalse((bundle / "admission_proposal.json").exists())
            validated = wdi.admit(self.raw, bundle)
            self.assertFalse(validated["synthetic"])
            self.assertEqual([item["rows"] for item in validated["tables"]], [90, 90, 18])
            self.assertEqual(validated["provider_calls"], 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.raw.iterdir()})
            PUBLIC_SNAPSHOTS.clear()
            (bundle / "request.txt").write_text("Changed request needs separate review")
            with self.assertRaisesRegex(ValueError, "context or data differs"):
                wdi.admit(self.raw, bundle)
            self.assertEqual(PUBLIC_SNAPSHOTS, {})

    def test_duplicate_missing_and_invalid_values_are_rejected_without_repair(self):
        original = copy.deepcopy(self.documents)
        variants = []
        duplicated = copy.deepcopy(original)
        duplicated["observations.json"][1].append(duplicated["observations.json"][1][0])
        variants.append(duplicated)
        missing = copy.deepcopy(original); missing["observations.json"][1].pop()
        variants.append(missing)
        for value in (None, -1, 101, True):
            bad = copy.deepcopy(original); bad["observations.json"][1][0]["value"] = value
            variants.append(bad)
        fractional = copy.deepcopy(original); fractional["observations.json"][1][1]["value"] = 100000.5
        variants.append(fractional)
        for index, variant in enumerate(variants):
            self.documents = variant
            self.write_sources()
            with self.subTest(index=index), self.pins(), self.assertRaises(ValueError):
                wdi.prepare(self.raw, self.root / f"rejected-{index}")
            self.assertFalse((self.root / f"rejected-{index}").exists())

    def test_changed_license_record_and_extra_bundle_files_cannot_be_admitted(self):
        with self.pins(), patch.dict(PUBLIC_SNAPSHOTS, {}, clear=True):
            prepared = wdi.prepare(self.raw, self.root / "prepared")
            bundle = Path(prepared["bundle"])
            (bundle / "unexpected-evaluator-file.json").write_text("not model input")
            with self.assertRaisesRegex(ValueError, "exactly the seven"):
                wdi.admit(self.raw, bundle)
            (self.raw.parent.parent / "LICENSE_DATA.md").write_text("Changed license")
            with self.assertRaisesRegex(ValueError, "record hash differs"):
                wdi.prepare(self.raw, self.root / "rejected")
            self.assertFalse((self.root / "rejected").exists())
            self.assertEqual(PUBLIC_SNAPSHOTS, {})


if __name__ == "__main__":
    unittest.main()

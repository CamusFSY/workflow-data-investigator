"""Offline preparation of one pinned public WDI development smoke, not a downloader.

The four raw JSON files must already exist. No model, key lookup, network, billing,
gold reader or arbitrary dataset opt-in is provided. A trusted caller may explicitly
admit only the exact source/context bytes reconstructed and checked by this module.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from investigator.bundle import safe_read, validate_bundle
from investigator.provenance import PUBLIC_SNAPSHOTS

COUNTRIES = tuple("ARG AUS BRA CAN CHN DEU ETH FRA GBR IDN IND JPN KEN MEX NGA PAK USA ZAF".split())
YEARS = tuple(range(2019, 2024))
ACCESS = "EG.ELC.ACCS.ZS"
POPULATION = "SP.POP.TOTL"
COUNTRY_PATH = ";".join(COUNTRIES)
BASE = "https://api.worldbank.org/v2/"
SOURCE_URLS = {
    "observations.json": BASE + f"country/{COUNTRY_PATH}/indicator/{ACCESS};{POPULATION}?source=2&date=2019:2023&format=json&per_page=1000",
    "countries.json": BASE + f"country/{COUNTRY_PATH}?format=json&per_page=1000",
    "electricity_indicator.json": BASE + f"indicator/{ACCESS}?source=2&format=json&per_page=1000",
    "population_indicator.json": BASE + f"indicator/{POPULATION}?source=2&format=json&per_page=1000",
}
SOURCE_SHA256 = {
    "observations.json": "83ca463bfb19709bc28edeb87f394f4f80b7dad719fd66ed611533efa8e9e44a",
    "countries.json": "d8102cc16f92bcedfe828980495f123926db8a2c7017ec3ac20dd6c1d269142a",
    "electricity_indicator.json": "e3f5c7a3c56c363e3c59546e9fe5c3e9838b5b9b9c3d05ed0970ab14619db3c6",
    "population_indicator.json": "689a8664399394b9d35c831ee21f7406a8e059acc3be5fc3da02313f5562dd63",
}
SOURCE_RETRIEVED_AT = {
    "observations.json": "2026-10-11T15:39:18.356480Z",
    "countries.json": "2026-10-11T15:39:20.974977Z",
    "electricity_indicator.json": "2026-10-11T15:40:13.414273Z",
    "population_indicator.json": "2026-10-11T15:40:16.198771Z",
}
RECORD_SHA256 = {
    "source_manifest.json": "c0d91bb5b1924e6ff2d06450fcf70135ad12c61de0594ab093c89b82af1cd90e",
    "LICENSE_DATA.md": "5e25dd4938cf043fa9f1d1c064c61e62b68c553937bdf90705c2ea1e7d93fb2e",
}
CSV_SHA256 = {
    "electricity_access.csv": "bc94e330efc6094fff497d9fc00af185f0d38640cb19fe2da7592d4958e0c783",
    "population.csv": "0c6058db3718661f0cba5dc777924bbc3cc33b311235555c4b5c45c97e522ec1",
    "countries.csv": "e4b2fb33e1c0b629f2e54aecc603c7caf0ddc0513255e6e3fcf44fccfc5338f4",
}
GOAL = (
    "核验固定18国样本2022年人口加权通电率是否低于2021年，给出两年的百分比与百分点变化。"
    "先检查粒度和连接键。请用一个成功的SQL查询返回一行，列名为baseline_year、comparison_year、"
    "baseline_pct、comparison_pct、delta_pp，并在最终发现中引用该查询证据。"
    "不能把本样本描述成世界银行官方全球指标。"
)
METRIC = """# Fixed-sample descriptive electricity access metric
This public World Development Indicators snapshot covers exactly the 18 country
codes in catalog.json and years 2019 through 2023. It contains national rows only.
Each fact table's grain is one (country_code, year); countries has one country_code.
Join facts on BOTH country_code AND year, then country metadata on country_code.

For a year, estimated people with access = population * access_pct / 100.
The sample's population-weighted percentage is
100 * SUM(estimated people with access) / SUM(population).
For the requested comparison, delta_pp = percentage in 2022 - percentage in 2021.
This is our descriptive definition for this fixed sample, not an official World
Bank world/regional aggregate. Current region labels are not historical labels.
Population and electricity access are estimates, not binomial success/total
observations. Keep their published precision; do not round them into analyze/plot
count inputs. NULL is unknown, not zero; do not silently drop unmatched/missing rows.
No causal or statistical-significance claim follows from this comparison alone.

Sources: World Bank, World Development Indicators, EG.ELC.ACCS.ZS and SP.POP.TOTL.
Indicator metadata: https://databank.worldbank.org/metadataglossary/world-development-indicators/series/EG.ELC.ACCS.ZS
https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SP.POP.TOTL
Data: CC BY 4.0 with World Bank additional terms:
https://datacatalog.worldbank.org/public-licenses
Selection, renamed columns and derived calculations are modifications by this project.
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def csv_bytes(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(sorted(rows))
    return stream.getvalue().encode("utf-8")


def checked_sources(raw_directory):
    """Reject drift before creating a bundle; never overwrite or normalize raw JSON."""
    root = Path(raw_directory).absolute()
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError("Symlink raw source paths are not accepted")
    raw, documents = {}, {}
    for name, expected in SOURCE_SHA256.items():
        data = safe_read(root, name, 2 * 1024 * 1024)
        if digest(data) != expected:
            raise ValueError(f"Source hash differs: {name}; retain it separately for a newly reviewed snapshot")
        response = json.loads(data)  # Default number decoding is intentional.
        if (not isinstance(response, list) or len(response) != 2
                or not isinstance(response[0], dict) or response[0].get("pages") != 1
                or not isinstance(response[1], list)):
            raise ValueError(f"Expected a single-page API response: {name}")
        raw[name], documents[name] = data, response
    for name, indicator in (("electricity_indicator.json", ACCESS), ("population_indicator.json", POPULATION)):
        records = documents[name][1]
        if len(records) != 1 or records[0].get("id") != indicator:
            raise ValueError(f"Wrong indicator metadata: {name}")
    manifest_bytes = safe_read(root.parent, "source_manifest.json", 65536)
    license_bytes = safe_read(root.parent.parent, "LICENSE_DATA.md", 65536)
    for name, data in (("source_manifest.json", manifest_bytes), ("LICENSE_DATA.md", license_bytes)):
        if digest(data) != RECORD_SHA256[name]:
            raise ValueError(f"Original source/license record hash differs: {name}")
    manifest = json.loads(manifest_bytes)
    for name, data in raw.items():
        record = manifest["files"][name]
        if (record["url"] != SOURCE_URLS[name] or record["sha256"] != digest(data)
                or record["bytes"] != len(data) or record["api_header"] != documents[name][0]
                or record["retrieved_at_utc"].replace("+00:00", "Z") != SOURCE_RETRIEVED_AT[name]):
            raise ValueError(f"Source manifest does not describe the raw bytes: {name}")
    return raw, documents, manifest_bytes, license_bytes


def reconstruct(raw_directory):
    """Return canonical bytes and a fixed-snapshot admission proposal, with no side effects."""
    raw, documents, source_manifest, license_bytes = checked_sources(raw_directory)
    access, population, countries = [], [], []
    seen = {ACCESS: set(), POPULATION: set()}
    for row in documents["observations.json"][1]:
        indicator, country, year = row["indicator"]["id"], row["countryiso3code"], int(row["date"])
        if indicator not in seen or country not in COUNTRIES or year not in YEARS:
            raise ValueError("Observation outside the fixed indicator/country/year scope")
        key = country, year
        if key in seen[indicator]:
            raise ValueError("Duplicate fact key; do not deduplicate")
        seen[indicator].add(key)
        value = row["value"]
        if indicator == ACCESS:
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Expected non-missing finite access in [0, 100]")
            access.append([country, year, value])
        else:
            if type(value) is not int or not 0 < value < 2**63:
                raise ValueError("Expected a positive integer population without conversion")
            population.append([country, year, value])
    expected_keys = {(country, year) for country in COUNTRIES for year in YEARS}
    if any(keys != expected_keys for keys in seen.values()):
        raise ValueError("Expected 90 unique matching keys per fact table")
    seen_countries = set()
    for row in documents["countries.json"][1]:
        code, name, region = row["id"], row["name"], row["region"]["value"]
        if code not in COUNTRIES or code in seen_countries or row["region"].get("id") == "NA":
            raise ValueError("Unexpected, duplicate or aggregate country row")
        if any(not isinstance(v, str) or not 1 <= len(v) <= 120 or any(ord(c) < 32 for c in v)
               for v in (name, region)):
            raise ValueError("Invalid public country/region label")
        seen_countries.add(code)
        countries.append([code, name, region])
    if seen_countries != set(COUNTRIES):
        raise ValueError("Expected all 18 country metadata records")
    files = {
        "electricity_access.csv": csv_bytes(["country_code", "year", "access_pct"], access),
        "population.csv": csv_bytes(["country_code", "year", "population"], population),
        "countries.csv": csv_bytes(["country_code", "country_name", "region_name"], countries),
    }
    if {name: digest(data) for name, data in files.items()} != CSV_SHA256:
        raise ValueError("Canonical CSV hashes differ; do not evaluate this as the original snapshot")
    recipe_hash = digest(Path(__file__).read_bytes())
    source_hash = digest(source_manifest)
    declaration = {
        "type": "public-real", "dataset_id": "world-bank-wdi-electricity-18-country",
        "snapshot_id": f"wdi18-2019-2023-{source_hash[:12]}-{recipe_hash[:12]}",
        "source_url": SOURCE_URLS["observations.json"], "license_id": "CC-BY-4.0",
        "license_url": "https://datacatalog.worldbank.org/public-licenses",
        "retrieved_at": SOURCE_RETRIEVED_AT["observations.json"], "upstream_sha256": source_hash,
        "transformation": f"upstream_sha256 pins source_manifest.json with four raw API hashes. Fixed 18 national rows, 2019-2023, two indicators; sorted UTF-8 CSV with renamed columns; no rounding, imputation or deduplication. Preparation script SHA256 {recipe_hash}.",
        "attribution": "World Bank, World Development Indicators, EG.ELC.ACCS.ZS and SP.POP.TOTL; retrieved 2026-10-11 by source author. Selected countries/years, renamed columns and derived calculations. CC BY 4.0 with World Bank additional terms; not an official world aggregate.",
        "personal_data": False, "sensitive_data": False, "private_data": False,
    }
    tables = []
    for name, columns, key in (
        ("electricity_access", {"country_code": "TEXT", "year": "INTEGER", "access_pct": "REAL"}, ["country_code", "year"]),
        ("population", {"country_code": "TEXT", "year": "INTEGER", "population": "INTEGER"}, ["country_code", "year"]),
        ("countries", {"country_code": "TEXT", "country_name": "TEXT", "region_name": "TEXT"}, ["country_code"]),
    ):
        tables.append({"name": name, "file": name + ".csv", "columns": columns,
                       "grain": "One row per " + ", ".join(key), "verified_unique_key": key})
    files.update({
        "catalog.json": json_bytes({"version": "1.0", "synthetic": False, "provenance": declaration,
                                    "country_codes": list(COUNTRIES), "years": list(YEARS), "tables": tables}),
        "metric_definition.md": METRIC.encode("utf-8"),
        "dashboard_query.sql": b"-- No pre-existing dashboard SQL was provided for this descriptive comparison.\n",
        "request.txt": (GOAL + "\n").encode("utf-8"),
    })
    approval = {"provenance": declaration, "files": {name: digest(data) for name, data in files.items()},
                "review_reference": "Fixed WDI source handoff 2026-10-11; official indicator license/definition pages checked; helper verifies all pinned raw/CSV hashes, 18 national rows, 90 unique matching keys/fact, permitted columns and no missing/out-of-range values. Development smoke only; no live result claim."}
    proofs = {"provenance/source_manifest.json": source_manifest, "LICENSE_DATA.md": license_bytes}
    return raw, files, proofs, approval


def prepare(raw_directory, output):
    raw, files, proofs, approval = reconstruct(raw_directory)
    output = Path(output).absolute()
    if any(p.is_symlink() for p in [output.parent, *output.parent.parents]):
        raise ValueError("Symlink output paths are not accepted")
    output.mkdir(parents=True, exist_ok=False)
    (output / "bundle_inputs").mkdir()
    (output / "provenance" / "raw").mkdir(parents=True)
    for name, data in files.items():
        (output / "bundle_inputs" / name).write_bytes(data)
    for name, data in raw.items():
        (output / "provenance" / "raw" / name).write_bytes(data)
    for name, data in proofs.items():
        (output / name).write_bytes(data)
    (output / "admission_proposal.json").write_bytes(json_bytes(approval))
    (output / "objective_contract.json").write_bytes(json_bytes({
        "purpose": "Development smoke, excluded from held-out evaluation; no expected answers in bundle_inputs",
        "result_columns": ["baseline_year", "comparison_year", "baseline_pct", "comparison_pct", "delta_pp"],
        "selection": "Exactly one successful query evidence ID cited by final findings must return one row with exactly these columns and years 2021,2022. Missing/ambiguous matches fail; never search uncited queries for a passing answer.",
        "absolute_tolerance_percentage_points": "0.000000001",
        "gold": "Compute/review independently outside bundle_inputs before live calls. No scorer or numerical gold is supplied by this preparation helper.",
    }))
    return {"bundle": str(output / "bundle_inputs"), "snapshot_id": approval["provenance"]["snapshot_id"],
            "raw_hashes_verified": 4, "csv_hashes_verified": 3, "model_calls": 0, "automatically_admitted": False}


def admit(raw_directory, bundle_directory):
    """Trusted host opt-in for this pinned snapshot only; no model/CLI admission tool."""
    _, files, _, proposal = reconstruct(raw_directory)
    bundle = Path(bundle_directory).absolute()
    if any(p.is_symlink() for p in [bundle, *bundle.parents]):
        raise ValueError("Symlink bundle paths are not accepted")
    if {p.name for p in bundle.iterdir()} != set(files):
        raise ValueError("WDI bundle must contain exactly the seven prepared input files")
    if any(safe_read(bundle, name) != expected for name, expected in files.items()):
        raise ValueError("WDI bundle context or data differs from the pinned preparation")
    snapshot = proposal["provenance"]["snapshot_id"]
    existing = PUBLIC_SNAPSHOTS.get(snapshot)
    if existing is not None and existing != proposal:
        raise ValueError("Snapshot identifier already has a different approval")
    PUBLIC_SNAPSHOTS[snapshot] = proposal
    try:
        return validate_bundle(bundle)
    except Exception:
        if existing is None:
            PUBLIC_SNAPSHOTS.pop(snapshot, None)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.raw_directory, args.output), ensure_ascii=False, indent=2))

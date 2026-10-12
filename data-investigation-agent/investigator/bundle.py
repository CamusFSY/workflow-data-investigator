"""Read only public, bounded CSV bundles; write only a new private run directory."""
import csv
import hashlib
import io
import json
import re
import sqlite3
import stat
from pathlib import Path

from .provenance import require_synthetic, source_provenance

MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_ROWS = 50000
CONTEXT_FILES = {
    "catalog": "catalog.json",
    "metric": "metric_definition.md",
    "dashboard": "dashboard_query.sql",
    "request": "request.txt",
}
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,62}\Z")
CSV_NULL_ENCODINGS = {
    "empty": ("", "Empty CSV cells become NULL; unspecified column types are TEXT."),
    "backslash-N": (r"\N", "CSV literal backslash-N becomes NULL; empty TEXT stays empty; "
                    "empty numeric fields are invalid; unspecified column types are TEXT."),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_read(root, name, limit=MAX_FILE):
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("Bundle files must be flat relative filenames")
    path = root / name
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
        raise ValueError(f"Unsafe or oversized bundle file: {name}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Unsafe or oversized bundle file: {name}")
    return data


def table_specs(catalog):
    tables = catalog.get("tables")
    if isinstance(tables, dict):
        if any(not isinstance(spec, dict) for spec in tables.values()):
            raise ValueError("Each catalog.tables entry must be an object")
        tables = [dict(spec, name=name) for name, spec in tables.items()]
    if not isinstance(tables, list) or not 1 <= len(tables) <= 20:
        raise ValueError("catalog.tables must contain 1..20 table descriptions")
    seen = set()
    for entry in tables:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError("Each catalog.tables entry must be an object with a name")
        name = entry["name"]
        if not isinstance(name, str) or not IDENT.fullmatch(name) or name in seen:
            raise ValueError("Invalid or duplicate table name")
        filename = entry.get("file", entry.get("path", name + ".csv"))
        if not isinstance(filename, str) or not filename.endswith(".csv"):
            raise ValueError("Each table must name a CSV file")
        seen.add(name)
        yield name, filename, entry.get("columns", [])


def prepare_bundle(source, output):
    """No globbing, SQL execution from files, code imports, or unknown file reads."""
    source = Path(source).absolute()
    for parent in [source, *source.parents]:
        if parent.is_symlink():
            raise ValueError("Symlink bundle paths are not accepted")
    files = {"catalog.json": safe_read(source, "catalog.json", 65536)}
    catalog = json.loads(files["catalog.json"])
    source_provenance(catalog)
    null_encoding = catalog.get("csv_null_encoding", "empty")
    if not isinstance(null_encoding, str) or null_encoding not in CSV_NULL_ENCODINGS:
        raise ValueError("catalog.csv_null_encoding must be empty or backslash-N")
    null_token, import_note = CSV_NULL_ENCODINGS[null_encoding]
    for name in CONTEXT_FILES.values():
        if name != "catalog.json":
            files[name] = safe_read(source, name, 65536)
    specs = list(table_specs(catalog))
    for _, filename, _ in specs:
        files[filename] = safe_read(source, filename)
    if sum(map(len, files.values())) > MAX_TOTAL:
        raise ValueError("Bundle exceeds 8 MiB")
    provenance = source_provenance(catalog, files)
    output = Path(output).absolute()
    for parent in [output.parent, *output.parent.parents]:
        if parent.is_symlink():
            raise ValueError("Symlink output paths are not accepted")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "input"
    snapshot.mkdir()
    for name, data in files.items():
        (snapshot / name).write_bytes(data)
    db = snapshot / "data.sqlite"
    try:
        with sqlite3.connect(db) as conn:
            for table, filename, columns in specs:
                reader = csv.reader(io.StringIO(files[filename].decode("utf-8-sig")))
                header = next(reader, None)
                if header is None:
                    raise ValueError(f"Empty CSV; provide a header: {filename}")
                if (not 1 <= len(header) <= 32 or len(set(header)) != len(header)
                        or any(not IDENT.fullmatch(col) for col in header)):
                    raise ValueError(f"Invalid CSV header in {filename}")
                declared = {}
                if isinstance(columns, dict):
                    declared = {
                        k: v.get("type", "TEXT") if isinstance(v, dict) else v
                        for k, v in columns.items()
                    }
                elif isinstance(columns, list):
                    if any(not isinstance(c, dict) or not isinstance(c.get("name"), str)
                           for c in columns):
                        raise ValueError(f"Catalog columns must be named objects: {filename}")
                    declared = {c["name"]: c.get("type", "TEXT") for c in columns}
                    if len(declared) != len(columns):
                        raise ValueError(f"Duplicate catalog column names: {filename}")
                else:
                    raise ValueError(f"Catalog columns must be an object or array: {filename}")
                if declared and set(declared) != set(header):
                    raise ValueError(f"Catalog/CSV column mismatch: {filename}")
                types = [str(declared.get(col, "TEXT")).upper() for col in header]
                aliases = {"STRING": "TEXT", "DATE": "TEXT", "DATETIME": "TEXT",
                           "TIMESTAMP": "TEXT", "INT": "INTEGER", "FLOAT": "REAL",
                           "NUMBER": "REAL", "BOOLEAN": "INTEGER"}
                types = [aliases.get(kind, kind) for kind in types]
                if any(t not in {"TEXT", "INTEGER", "REAL"} for t in types):
                    raise ValueError(f"Column types must be TEXT, INTEGER, or REAL: {filename}")
                ddl = ", ".join(f'"{col}" {kind}' for col, kind in zip(header, types))
                conn.execute(f'CREATE TABLE "{table}" ({ddl})')
                for count, row in enumerate(reader, 1):
                    if count > MAX_ROWS:
                        raise ValueError(f"CSV exceeds {MAX_ROWS} data rows: {filename}")
                    if len(row) != len(header):
                        raise ValueError(f"CSV row {count + 1} has {len(row)} fields; expected {len(header)}: {filename}")
                    converted = []
                    for column, value, kind in zip(header, row, types):
                        if len(value.encode("utf-8")) > 4096:
                            raise ValueError("CSV field exceeds 4096 bytes")
                        if value == null_token:
                            converted.append(None)
                        elif kind in {"INTEGER", "REAL"}:
                            import math
                            try:
                                val = int(value) if kind == "INTEGER" else float(value)
                                if kind == "REAL" and not math.isfinite(val):
                                    raise ValueError("Non-finite number")
                                if kind == "INTEGER" and not -(2 ** 63) <= val < 2 ** 63:
                                    raise ValueError("Integer exceeds SQLite range")
                            except ValueError:
                                null_hint = "an empty cell" if null_encoding == "empty" else r"literal \N"
                                raise ValueError(
                                    f"Invalid {kind} in {filename}, row {count + 1}, column {column}; "
                                    f"use a finite number in range or {null_hint} for NULL"
                                ) from None
                            converted.append(val)
                        else:
                            converted.append(value)
                    conn.execute(
                        f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in header)})',
                        converted,
                    )
        if db.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Imported database exceeds 16 MiB")
        hashes = {name: digest(data) for name, data in files.items()}
        hashes["data.sqlite"] = digest(db.read_bytes())
        for path in snapshot.iterdir():
            path.chmod(0o444)
        return {"synthetic": provenance["type"] == "synthetic", "provenance": provenance, "files": hashes, "sqlite_version": sqlite3.sqlite_version,
                "import": import_note}
    except Exception as exc:
        (output / "setup_error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        raise


def validate_bundle(source):
    """Import into temporary local storage; return schema/counts/hashes, never a diagnosis."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="investigator-validate-") as directory:
        output = Path(directory) / "check"
        manifest = prepare_bundle(source, output)
        tables = []
        catalog = json.loads((output / "input" / "catalog.json").read_text())
        with sqlite3.connect(f"file:{output / 'input' / 'data.sqlite'}?mode=ro", uri=True) as conn:
            for table, filename, _ in table_specs(catalog):
                columns = [{"name": row[1], "type": row[2]}
                           for row in conn.execute(f'PRAGMA table_info("{table}")')]
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                tables.append({"name": table, "file": filename, "rows": count, "columns": columns})
        return {"status": "valid", "synthetic": manifest["synthetic"], "provenance": manifest["provenance"], "provider_calls": 0, "tables": tables,
                "source_files": {k: v for k, v in manifest["files"].items() if k != "data.sqlite"},
                "scope": "File, schema, type and resource validation only; metric meaning and authority are not verified.",
                "import": manifest["import"]}

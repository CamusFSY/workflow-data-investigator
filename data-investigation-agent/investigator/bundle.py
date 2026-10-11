"""Read only public, bounded CSV bundles; write only a new private run directory."""
import csv
import hashlib
import io
import json
import re
import sqlite3
import stat
from pathlib import Path

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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_read(root, name, limit=MAX_FILE):
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("Bundle files must be flat relative filenames")
    path = root / name
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
        raise ValueError(f"Unsafe or oversized bundle file: {name}")
    return path.read_bytes()


def table_specs(catalog):
    tables = catalog.get("tables")
    if isinstance(tables, dict):
        tables = [dict(spec, name=name) for name, spec in tables.items()]
    if not isinstance(tables, list) or not 1 <= len(tables) <= 20:
        raise ValueError("catalog.tables must contain 1..20 table descriptions")
    seen = set()
    for entry in tables:
        name = entry["name"]
        filename = entry.get("file", entry.get("path", name + ".csv"))
        if not isinstance(name, str) or not IDENT.fullmatch(name) or name in seen:
            raise ValueError("Invalid or duplicate table name")
        if not isinstance(filename, str) or not filename.endswith(".csv"):
            raise ValueError("Each table must name a CSV file")
        seen.add(name)
        yield name, filename, entry.get("columns", [])


def require_synthetic(catalog):
    """Accept explicit legacy or provenance declarations without rewriting the catalog."""
    if not isinstance(catalog, dict):
        raise ValueError("Catalog must be an object")
    if "synthetic" in catalog and catalog["synthetic"] is not True:
        raise ValueError("catalog.synthetic, when present, must be boolean true")
    provenance = catalog.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ValueError("catalog.provenance must be an object")
    if "type" in provenance and provenance["type"] != "synthetic":
        raise ValueError("Provenance conflicts with a synthetic-only bundle")
    for key in ("real_enterprise_data", "personal_data"):
        if key in provenance and provenance[key] is not False:
            raise ValueError(f"provenance.{key}, when present, must be boolean false")
    explicit_provenance = (
        provenance.get("type") == "synthetic"
        and provenance.get("real_enterprise_data") is False
        and provenance.get("personal_data") is False
    )
    if catalog.get("synthetic") is not True and not explicit_provenance:
        raise ValueError(
            "MVP requires synthetic: true or explicit synthetic provenance "
            "with real_enterprise_data: false and personal_data: false"
        )


def prepare_bundle(source, output):
    """No globbing, SQL execution from files, code imports, or unknown file reads."""
    source = Path(source).absolute()
    for parent in [source, *source.parents]:
        if parent.is_symlink():
            raise ValueError("Symlink bundle paths are not accepted")
    files = {name: safe_read(source, name, 65536) for name in CONTEXT_FILES.values()}
    catalog = json.loads(files["catalog.json"])
    require_synthetic(catalog)
    specs = list(table_specs(catalog))
    for _, filename, _ in specs:
        files[filename] = safe_read(source, filename)
    if sum(map(len, files.values())) > MAX_TOTAL:
        raise ValueError("Bundle exceeds 8 MiB")
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
                header = next(reader)
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
                    declared = {c["name"]: c.get("type", "TEXT")
                                for c in columns if isinstance(c, dict)}
                if declared and set(declared) != set(header):
                    raise ValueError(f"Catalog/CSV column mismatch: {filename}")
                types = [str(declared.get(col, "TEXT")).upper() for col in header]
                aliases = {"STRING": "TEXT", "DATE": "TEXT", "DATETIME": "TEXT",
                           "TIMESTAMP": "TEXT", "INT": "INTEGER", "FLOAT": "REAL",
                           "NUMBER": "REAL", "BOOLEAN": "INTEGER"}
                types = [aliases.get(kind, kind) for kind in types]
                if any(t not in {"TEXT", "INTEGER", "REAL"} for t in types):
                    raise ValueError("Column types must be TEXT, INTEGER, or REAL")
                ddl = ", ".join(f'"{col}" {kind}' for col, kind in zip(header, types))
                conn.execute(f'CREATE TABLE "{table}" ({ddl})')
                for count, row in enumerate(reader, 1):
                    if count > MAX_ROWS or len(row) != len(header):
                        raise ValueError(f"Row limit or row width error: {filename}")
                    converted = []
                    for value, kind in zip(row, types):
                        if len(value.encode("utf-8")) > 4096:
                            raise ValueError("CSV field exceeds 4096 bytes")
                        if value == "":
                            converted.append(None)
                        elif kind == "INTEGER":
                            converted.append(int(value))
                        elif kind == "REAL":
                            import math
                            val = float(value)
                            if not math.isfinite(val):
                                raise ValueError("Non-finite CSV number")
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
        return {"synthetic": True, "files": hashes, "sqlite_version": sqlite3.sqlite_version,
                "import": "Empty CSV cells become NULL; unspecified column types are TEXT."}
    except Exception as exc:
        (output / "setup_error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        raise

"""Trusted short-lived SQL worker. It never executes model-written Python."""
import json
import math
import resource
import sqlite3
import sys
import time
from pathlib import Path

# Caller contracts import the same limit enforced by this isolated SQL worker.
MAX_QUERY_COLUMNS = 64

FUNCTIONS = set("""
abs avg count sum total min max round coalesce ifnull nullif
date time datetime julianday unixepoch strftime timediff
lower upper length substr substring trim ltrim rtrim replace instr
typeof cast printf format like glob group_concat
row_number rank dense_rank lag lead first_value last_value
""".split())


def main():
    # The worker has a clean environment and no exposed filesystem/network functions.
    # rlimits bound native SQLite; this is not a general code-execution sandbox.
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    request = json.loads(sys.stdin.read(10000))
    uri = Path(sys.argv[1]).as_uri() + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=0.1)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
    conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 8192)
    conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, MAX_QUERY_COLUMNS)
    conn.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50)
    conn.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 10)
    conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 256)
    start = time.monotonic()
    ticks = 0

    def progress():
        nonlocal ticks
        ticks += 1
        return ticks >= 500 or time.monotonic() - start > 1.5

    conn.set_progress_handler(progress, 1000)
    if request["operation"] == "schema":
        tables = conn.execute(
            "SELECT name, type, sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if len(tables) > 20 or any(t[1] != "table" for t in tables):
            raise ValueError("Only up to 20 ordinary imported tables are supported")
        data = {"tables": []}
        for name, _, ddl in tables:
            if "VIRTUAL" in ddl.upper():
                raise ValueError("Virtual tables are not supported")
            cols = conn.execute('PRAGMA table_info("' + name.replace('"', '""') + '")')
            data["tables"].append({
                "name": name,
                "columns": [{"name": r[1], "type": r[2], "primary_key": bool(r[5])}
                            for r in cols],
            })
        return {"ok": True, "data": data}

    def authorize(action, arg1, arg2, database, trigger):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        # SQLite's optimized COUNT(*) reports db=None and an empty column name.
        # ATTACH/temp/schema mutation are denied, so this can only count an input table.
        if action == sqlite3.SQLITE_READ and (database == "main" or (database is None and arg2 == "")):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(authorize)
    cursor = conn.execute(request["sql"])
    if cursor.description is None:
        raise ValueError("Only SELECT / WITH queries are supported")
    columns = [item[0] for item in cursor.description]
    if len(columns) != len(set(columns)):
        raise ValueError("Give duplicate output columns distinct aliases")
    rows = cursor.fetchmany(201)
    truncated = len(rows) > 200
    rows = rows[:200]
    for row in rows:
        for value in row:
            if isinstance(value, bytes):
                raise ValueError("BLOB output is not supported")
            if isinstance(value, str) and len(value.encode()) > 4096:
                raise ValueError("Result field exceeds 4096 bytes")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite SQL result")
    return {"ok": True, "data": {
        "columns": columns, "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows), "truncated": truncated,
    }}


if __name__ == "__main__":
    try:
        result = main()
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("Result exceeds 64 KiB; aggregate or filter the query")
    except Exception as exc:
        encoded = json.dumps({"ok": False, "error": {
            "type": type(exc).__name__, "message": str(exc)[:500],
        }}, ensure_ascii=False)
    sys.stdout.write(encoded)

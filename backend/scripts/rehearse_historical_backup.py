"""Restore a controlled backup in isolation and prove preservation across upgrade.

Never connects to a source installation. The target must be newly provisioned,
empty, named megalodon_rehearsal_*, and have no application writers. Reports are
private and never contain row values or connection credentials. This is evidence
for a database rehearsal, not certification of a deployed recovery or its RPO.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

from scripts.postgres_backup import BackupInputError, connection, digest, restore

HISTORICAL = "20260914_workspace_bridge_tenant"
HEAD = "20260930_identity_authority"
# Only migrations in this explicitly reviewed interval are supported.
RENAMES = {"catalog_terms": {"created_by_id": "creado_por_id",
                            "updated_by_id": "actualizado_por_id"}}
UTC_COLUMNS = {
    "tezcatlipoca_users": ("created_at", "last_login"),
    "user_sessions": ("created_at", "expires_at", "last_active"),
    "snapshots": ("created_at",),
    "tunnels": ("created_at", "expires_at", "closed_at"),
    "dead_drops": ("created_at", "expires_at"),
    "api_logs": ("timestamp",),
    "token_blacklist": ("expires_at", "revoked_at"),
    "system_settings": ("created_at", "updated_at"),
}
ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise BackupInputError(message)


def validate_target(value):
    url = make_url(value)
    require(url.drivername in {"postgresql", "postgresql+asyncpg", "postgresql+psycopg2", "postgresql+psycopg"},
            "PostgreSQL rehearsal target required")
    require(bool(re.fullmatch(r"megalodon_rehearsal_[a-z0-9_]+", url.database or "")),
            "Target must be a dedicated megalodon_rehearsal_* database")
    # Normalize the dialect for Alembic's async environment; credentials remain
    # in the environment, never command arguments or reports.
    return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


@contextmanager
def read_snapshot(uri, env):
    # Pass the explicit passfile to the driver, without changing global os.environ.
    with psycopg2.connect(uri, passfile=env.get("PGPASSFILE", "")) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL timezone TO 'UTC'")
            cursor.execute("SET LOCAL extra_float_digits TO 3")
            cursor.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
            cursor.execute("SET LOCAL bytea_output TO 'hex'")
        yield conn


def inventory(conn):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='public' AND c.relkind IN ('r','p')
              AND c.relname <> 'alembic_version' AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname COLLATE "C", a.attnum
        """)
        result = {}
        for table, column, kind in cursor:
            result.setdefault(table, []).append((column, kind))
        cursor.execute("SELECT version_num FROM public.alembic_version")
        versions = cursor.fetchall()
        require(len(versions) == 1, "Exactly one recorded Alembic revision required")
        return result, versions[0][0]


def projection_query(table, columns, migrated=False):
    expressions = []
    for original, kind in columns:
        name = RENAMES.get(table, {}).get(original, original) if migrated else original
        expression = sql.Identifier(name)
        if (not migrated and original in UTC_COLUMNS.get(table, ())
                and kind == "timestamp without time zone"):
            expression = sql.SQL("({} AT TIME ZONE 'UTC')").format(expression)
        # PostgreSQL text preserves decimal scale and EWKB geometry. JSON is
        # only the unambiguous row envelope; the report receives hashes alone.
        expressions.append(sql.SQL("{}::text AS {}").format(expression, sql.Identifier(original)))
    return sql.SQL("""
        SELECT row_to_json(p)::text FROM (SELECT {} FROM {}) p
        ORDER BY row_to_json(p)::text COLLATE "C"
    """).format(sql.SQL(", ").join(expressions), sql.Identifier("public", table))


def fingerprints(conn, tables, migrated=False):
    result = {}
    for number, (table, columns) in enumerate(tables.items()):
        h, count = hashlib.sha256(), 0
        # A server cursor streams the sorted rows; memory is bounded even for a
        # real historical database. Duplicate rows participate in the digest.
        with conn.cursor(name=f"rehearsal_rows_{number}") as cursor:
            cursor.itersize = 1000
            cursor.execute(projection_query(table, columns, migrated))
            for (row,) in cursor:
                h.update(row.encode("utf-8") + b"\n")
                count += 1
        result[table] = {"rows": count, "historical_columns_sha256": h.hexdigest()}
    return result


def compare(before, after):
    require(before == after, "Historical row preservation failed; keep target isolated for investigation")


def checked_command(command, env, label):
    # Tool logs/tracebacks can contain private values. Only a sanitized failure
    # leaves this process. The retained target enables local investigation.
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    require(result.returncode == 0, f"{label} failed; target retained for private investigation")


def run_rehearsal(backup, uri, env):
    started = time.monotonic()
    restore_started = time.monotonic()
    restore(uri, env, backup)
    restore_seconds = time.monotonic() - restore_started
    with read_snapshot(uri, env) as conn:
        tables, revision = inventory(conn)
        require(revision in {HISTORICAL, HEAD}, "Backup revision outside the reviewed migration interval")
        before = fingerprints(conn, tables)
    upgrade_started = time.monotonic()
    checked_command([sys.executable, "-m", "alembic", "upgrade", HEAD], os.environ.copy(), "Historical upgrade")
    upgrade_seconds = time.monotonic() - upgrade_started
    with read_snapshot(uri, env) as conn:
        current, target = inventory(conn)
        require(target == HEAD and set(current) == set(tables), "Unexpected revision or historical table changes")
        after = fingerprints(conn, tables, migrated=revision != HEAD)
        compare(before, after)
    checked_command([sys.executable, "-m", "scripts.verify_migrated_schema"], os.environ.copy(), "Migrated schema check")
    return {"status": "database_rehearsal_passed", "source_revision": revision,
            "target_revision": target, "backup_sha256": digest(backup),
            "tables": before, "tables_verified": len(before),
            "rows_verified": sum(t["rows"] for t in before.values()),
            "historical_values_preserved": True,
            "timings_seconds": {"restore": round(restore_seconds, 3),
                                "upgrade": round(upgrade_seconds, 3),
                                "database_rehearsal_total": round(time.monotonic() - started, 3)},
            "production_deployment_certified": False, "rpo_seconds": None, "production_rto_seconds": None,
            "remaining": ["representativeness of supplied historical data", "cluster roles and runtime grants",
                          "external artifacts and storage references", "JWT key rotation after recovery",
                          "deployed application flows", "measured production RPO/RTO"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        os.environ["DATABASE_URL"] = validate_target(os.environ["DATABASE_URL"])
        require(args.backup.is_file(), "Controlled backup file required")
        # Reserve the report before any database write; never overwrite an old
        # report, supplied backup, symlink or unrelated file.
        with args.report.open("x", encoding="utf-8") as report:
            os.chmod(args.report, 0o600)
            try:
                with connection() as (uri, env):
                    result = run_rehearsal(args.backup, uri, env)
                result["completed_at_utc"] = datetime.now(UTC).isoformat()
                report.write(json.dumps(result, indent=2) + "\n")
                report.flush()
                os.fsync(report.fileno())
            except Exception:
                report.write(json.dumps({"status": "failed", "production_deployment_certified": False,
                                         "target_retained": True}) + "\n")
                raise
    except BackupInputError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("Historical rehearsal failed; inspect the isolated target privately") from None
    print("Database rehearsal passed; private report written. Production GO remains unproven.")


if __name__ == "__main__":
    main()

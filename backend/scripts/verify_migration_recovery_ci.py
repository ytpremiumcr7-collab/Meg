"""Exercise populated historical upgrades and real PostgreSQL backup/restore.

Synthetic fixtures are confined to a dedicated disposable CI service. This is
not a production migration command, and a passing report does not certify a
customer database, its credentials, role grants, or external artifact storage.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
import geoalchemy2  # noqa: F401 -- register PostGIS reflection types


HISTORICAL = "20260914_workspace_bridge_tenant"
HEAD = "20260930_identity_authority"
OWNED = ("presupuestos", "partidas", "conceptos", "insumos",
         "programas_obra", "actividades_programa")
TABLES = ("tenants", "users", "expedientes_obra", *OWNED,
          "catalog_terms", "webhook_eventos_procesados", "tezcatlipoca_users", "snapshots",
          "levantamientos", "puntos_topograficos")
INSTANT = datetime(2026, 9, 14, 12, 34, 56, 123456, tzinfo=timezone.utc)
NAIVE = INSTANT.replace(tzinfo=None)
D = Decimal


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalize(value):
    if isinstance(value, datetime):
        # Historical Tez timestamps explicitly represented UTC without tzinfo.
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def snapshot(engine):
    with engine.connect() as conn:
        result = {}
        for name in TABLES:
            table = sa.Table(name, sa.MetaData(), autoload_with=conn)
            columns = [sa.func.ST_AsEWKT(c).label(c.name) if c.name == "geom" else c for c in table.columns]
            result[name] = [normalize(dict(row)) for row in conn.execute(
                sa.select(*columns).order_by(*table.primary_key.columns)).mappings()]
        result["revision"] = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        return result


def schema_signature(engine):
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        return {
            name: {
                "columns": [(c["name"], str(c["type"]), c["nullable"], str(c["default"]))
                            for c in inspector.get_columns(name)],
                "foreign_keys": inspector.get_foreign_keys(name),
                "unique": inspector.get_unique_constraints(name),
                "checks": inspector.get_check_constraints(name),
            }
            for name in sorted(inspector.get_table_names())
        }


def migrate(target, expected_failure=None, downgrade=False):
    command = [sys.executable, "-m", "alembic", "downgrade" if downgrade else "upgrade", target]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if expected_failure:
        require(result.returncode != 0 and expected_failure in result.stderr,
                "Migration did not reject the expected unsafe operation")
    elif result.returncode:
        # CI fixtures only; never run against customer credentials/data.
        sys.stderr.write(result.stderr)
        raise RuntimeError("Migration failed")


def seed(engine):
    graph = []
    with engine.begin() as conn:
        def insert(table_name, **values):
            table = sa.Table(table_name, sa.MetaData(), autoload_with=conn)
            return conn.execute(table.insert().values(**values).returning(table.c.id)).scalar_one()

        for number in (1, 2):
            tenant, user, expediente, presupuesto, partida, concepto, insumo, programa, actividad = [uuid4() for _ in range(9)]
            insert("tenants", id=tenant, name=f"CI historical tenant {number}", slug=f"ci-history-{number}",
                   is_active=True, plan="free")
            insert("users", id=user, tenant_id=tenant, email=f"history-{number}@fixture.invalid",
                   hashed_password="disabled-ci-fixture-no-login", full_name="CI historical author",
                   role="admin", is_active=True, is_verified=True)
            insert("expedientes_obra", id=expediente, tenant_id=tenant, identificador="SHARED-ID",
                   titulo="Historical fixture", organo="CI", unidad_administrativa="CI",
                   serie_documental="CI", subserie_documental="CI", tipo_contrato="PRECIOS_UNITARIOS",
                   estado="INICIADO", clasificacion="PUBLICO", creado_por_id=user)
            insert("presupuestos", id=presupuesto, expediente_id=expediente, identificador="SHARED-BUDGET",
                   nombre="Historical explicit cost", monto_directo=D("1234.56"), monto_indirecto=D("123.46"),
                   monto_utilidad=D("135.80"), monto_impuesto=D("239.01"), monto_total=D("1732.83"),
                   moneda="MXN", factor_indirecto=D("0.1000"), factor_utilidad=D("0.1000"),
                   factor_impuesto=D("0.1600"), zona_economica="CENTRO", estado="BORRADOR",
                   metadatos={"provenance": "synthetic historical fixture", "unicode": "México"},
                   creado_por_id=user, actualizado_por_id=user, created_at=INSTANT, updated_at=INSTANT)
            insert("partidas", id=partida, presupuesto_id=presupuesto, numero=1, descripcion="CI line",
                   unidad="m3", cantidad=D("2.0000"), precio_unitario=D("617.28"), importe=D("1234.56"))
            insert("conceptos", id=concepto, partida_id=partida, clave="CI-CONCEPT", descripcion="CI concept",
                   unidad="m3", cantidad=D("2.0000"), costo_directo_unitario=D("617.28"))
            insert("insumos", id=insumo, concepto_id=concepto, clave="CI-RESOURCE", descripcion="CI resource",
                   tipo="MATERIAL", unidad="m3", cantidad=D("2.0000"), precio_unitario=D("617.28"),
                   importe=D("1234.56"), rendimiento=D("1.0000"))
            insert("programas_obra", id=programa, expediente_id=expediente, identificador="SHARED-SCHEDULE",
                   nombre="CI schedule", fecha_inicio_plan=INSTANT, duracion_plan_dias=2, estado="BORRADOR")
            insert("actividades_programa", id=actividad, programa_id=programa, identificador="CI-A",
                   nombre="CI activity", wbs_codigo="1", wbs_nivel=1, duracion=D("2.00"), tipo="TAREA",
                   costo_presupuestado=D("1234.56"), costo_real=D("0.00"), porcentaje_avance=D("0.00"),
                   holgura_total=D("0.00"), holgura_libre=D("0.00"), en_ruta_critica=True)
            term = insert("catalog_terms", id=uuid4(), tenant_id=tenant, domain="ci", code="SHARED-TERM",
                          label="Historical term", created_by_id=user, updated_by_id=user)
            tez = insert("tezcatlipoca_users", username=f"ci-history-{number}",
                         password_hash="disabled-ci-fixture-no-login", tenant_id=str(tenant),
                         megalodon_user_id=str(user), created_at=NAIVE, last_login=NAIVE)
            insert("snapshots", name="CI historical snapshot", user_id=tez, tenant_id=str(tenant),
                   layers={"fixture": True}, viewport={"longitude": -99.1}, created_at=NAIVE)
            survey = insert("levantamientos", id=uuid4(), expediente_id=expediente,
                            identificador="CI-SURVEY", nombre="CI topography", tipo="TOPOGRAFICO",
                            estado="BORRADOR", crs="EPSG:6362", srid=6362, creado_por_id=user)
            insert("puntos_topograficos", id=uuid4(), levantamiento_id=survey, identificador="CI-POINT",
                   x=D("500000.123456"), y=D("2100000.654321"), z=D("2234.567890"), precision_xy=D("0.0010"),
                   geom=sa.func.ST_GeomFromEWKT("SRID=6362;POINT Z(500000.123456 2100000.654321 2234.56789)"))
            graph.append({"tenant": tenant, "user": user, "term": term,
                          **dict(zip(OWNED, (presupuesto, partida, concepto, insumo, programa, actividad)))})
        insert("webhook_eventos_procesados", id=uuid4(), proveedor="stripe",
               evento_id="ci-historical-event", procesado_en=INSTANT)
    return graph


def verify_upgrade(before, after, graph):
    expected = json.loads(json.dumps(before))
    expected["revision"] = HEAD
    for name in OWNED:
        by_id = {str(g[name]): str(g["tenant"]) for g in graph}
        for row in expected[name]:
            row["tenant_id"] = by_id[row["id"]]
            if name == "presupuestos":
                row.update(factor_riesgo=None, monto_riesgo=None)
    for row in expected["users"]:
        row["auth_version"] = 0
    for row in expected["catalog_terms"]:
        row["creado_por_id"] = row.pop("created_by_id")
        row["actualizado_por_id"] = row.pop("updated_by_id")
    for row in expected["webhook_eventos_procesados"]:
        row["created_at"] = row["updated_at"] = row["procesado_en"]
    require(expected == after, "Upgrade changed historical values beyond the documented transformations")


def verify_constraints(engine, graph):
    # Execute cross-tenant writes and require PostgreSQL itself to reject them.
    with engine.connect() as conn:
        for name in OWNED:
            transaction = conn.begin_nested()
            try:
                conn.execute(sa.text(f"UPDATE {name} SET tenant_id=:tenant WHERE id=:id"),
                             {"tenant": graph[1]["tenant"], "id": graph[0][name]})
            except IntegrityError as exc:
                require(exc.orig.pgcode == "23503", f"Unexpected constraint failure in {name}")
            else:
                raise RuntimeError(f"Cross-tenant ownership was accepted in {name}")
            finally:
                transaction.rollback()


def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("ENVIRONMENT") != "staging":
        raise SystemExit("This command seeds fixtures only in dedicated disposable CI staging")
    container = os.environ["MIGRATION_CI_CONTAINER"]
    url = sa.engine.make_url(os.environ["DATABASE_URL"])
    require(url.host in ("localhost", "127.0.0.1") and url.database == "migration_history_ci",
            "Dedicated local CI database required")
    engine = sa.create_engine(url.set(drivername="postgresql+psycopg2"))
    checks = []
    try:
        with engine.begin() as conn:
            require(not sa.inspect(conn).has_table("alembic_version"), "CI database must be fresh")
            conn.execute(sa.text("ALTER DATABASE migration_history_ci SET timezone TO 'America/Mexico_City'"))
        engine.dispose()
        migrate(HISTORICAL)
        graph = seed(engine)
        # An unresolved historical author must abort the entire upgrade, not
        # invent a user, drop attribution, or leave half-applied migrations.
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE catalog_terms SET created_by_id=:bad WHERE id=:id"),
                         {"bad": uuid4(), "id": graph[0]["term"]})
        invalid = snapshot(engine)
        invalid_schema = schema_signature(engine)
        migrate("head", expected_failure="fk_catalog_terms_creado_por_id")
        require(snapshot(engine) == invalid and schema_signature(engine) == invalid_schema,
                "Failed historical upgrade did not roll back schema and data atomically")
        checks.append("Unresolved historical authors reject upgrade with complete transaction rollback")
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE catalog_terms SET created_by_id=:author WHERE id=:id"),
                         {"author": graph[0]["user"], "id": graph[0]["term"]})
        historical = snapshot(engine)
        migrate("head")
        verify_upgrade(historical, snapshot(engine), graph)
        with engine.connect() as conn:
            for table, fields in (("tezcatlipoca_users", ("created_at", "last_login")),
                                  ("snapshots", ("created_at",))):
                columns = {c["name"]: c for c in sa.inspect(conn).get_columns(table)}
                require(all(columns[field]["type"].timezone for field in fields),
                        "Historical Tez UTC timestamps were not migrated to timezone-aware types")
        checks.append("Populated historical upgrade preserves decimal costs, UTC instants, authors and ownership")
        verify_constraints(engine, graph)
        checks.append("PostgreSQL rejects cross-tenant writes across all six budget/schedule tables")
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE users SET auth_version=7"))
        current, schema = snapshot(engine), schema_signature(engine)
        migrate("20260930_tez_timestamps", expected_failure="forward-only", downgrade=True)
        require(snapshot(engine) == current and schema_signature(engine) == schema,
                "Rejected identity downgrade changed authority or migration state")
        checks.append("Unsafe security downgrade is rejected without resetting session versions")
        from scripts.verify_migrated_schema import verify
        with engine.connect() as conn:
            verify(conn)
        with tempfile.TemporaryDirectory(prefix="meg-recovery-") as directory:
            backup = Path(directory) / "fixture.dump"
            with backup.open("wb") as output:
                subprocess.run(["docker", "exec", container, "pg_dump", "-U", url.username,
                                "-d", url.database, "-Fc"], stdout=output, check=True, timeout=120)
            subprocess.run(["docker", "exec", container, "createdb", "-U", url.username,
                            "-T", "template0", "migration_restore_ci"], check=True, timeout=30)
            with backup.open("rb") as source:
                subprocess.run(["docker", "exec", "-i", container, "pg_restore", "-U", url.username,
                                "-d", "migration_restore_ci", "--single-transaction", "--exit-on-error",
                                "--no-owner", "--no-privileges"], stdin=source, check=True, timeout=120)
            restored = sa.create_engine(engine.url.set(database="migration_restore_ci"))
            try:
                require(snapshot(restored) == current and schema_signature(restored) == schema,
                        "Backup restore changed data, schema, constraints or revocation epochs")
                verify_constraints(restored, graph)
                with restored.connect() as conn:
                    verify(conn)
                    require(conn.execute(sa.text("SELECT PostGIS_Version()")).scalar_one(), "PostGIS unavailable")
                    # Restored serial sequences must advance beyond existing IDs.
                    for table in ("tezcatlipoca_users", "snapshots"):
                        maximum = conn.execute(sa.text(f"SELECT max(id) FROM {table}")).scalar_one()
                        next_id = conn.execute(sa.text(
                            "SELECT nextval(pg_get_serial_sequence(:table, 'id'))"), {"table": table}).scalar_one()
                        require(next_id > maximum, f"Restored sequence collides in {table}")
            finally:
                restored.dispose()
        checks.append("Actual pg_dump/pg_restore preserves data, schema, PostGIS, sequences and revocation epochs")
        report = {"passed": checks, "source_revision": HISTORICAL, "target_revision": HEAD,
                  "fixtures": "synthetic populated historical data in two tenants",
                  "owned_rows": sum(len(current[t]) for t in OWNED),
                  "data_sha256": hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest(),
                  "production_deployment_certified": False,
                  "excluded": ["customer database snapshot", "role/ACL provisioning", "external storage recovery", "RPO/RTO"]}
        Path("migration-recovery-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

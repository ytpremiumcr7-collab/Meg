# Cierre bloqueantes (re-auditoría 2026-09-10)

## Bloqueantes originales → estado

| # | Bloqueante | Estado |
|---|------------|--------|
| B1 | inheritance_codes raise sin perfil | **CORREGIDO** — required=False, chain=(code,) |
| B2 | garantías fuera de CSV | **CORREGIDO** — garantias_legal_rules.csv + load_garantias |
| B3 | CANDIDATO materializa | **CORREGIDO** — requires !es_candidato AND datos_verificados |
| B4 | runtime sin DB | Parcial — tests SQLite en repo; E2E Postgres pendiente en entorno del usuario |
| B5 | tests adorno | **MEJORADO** — test_db_driven_runtime_sqlite.py (11+ asserts) |

## Adicional corregido en este ciclo

- `motor_garantias.py` reescrito: **sin** TOPE_PENAS / MINIMA_OBRA hardcode
- `contrato_service` async + fail-closed 422 si no hay regla
- `legal_consultor` async DB + sin 10%/5% inventados en respuesta/templates
- selector excepción: procedimiento desde `requirement.procedimiento` si existe
- bootstrap_procedure_db_driven.sh

## Aún no 10/10 producto completo

- Umbrales federales CANDIDATO (Anexo 9)
- Labels catalog.py aún en Python
- Frontend defaults de formulario (UX, no runtime legal)
- E2E API Postgres+JWT no ejecutado aquí

## Cómo validar

```bash
cd megalodon_audit/backend
python -m pytest tests/procurement/test_db_driven_runtime_sqlite.py -q --noconftest
# Con Postgres:
./scripts/bootstrap_procedure_db_driven.sh
```

## Ciclo perfiles + catálogo DB (mismo día)

- Modelo `CatalogTerm` + migración `20260910_catalog_terms`
- Seed `catalog_terms.csv` (37 términos, 8 dominios)
- `catalog.py` sin dicts hardcodeados; `build_catalog_payload` desde DB
- `ProcurementService.catalog` y validaciones usan `load_domain_map`
- Frontend: defaults vacíos; valores salen del perfil / tender
- `load_seeds_from_csv --only catalog`

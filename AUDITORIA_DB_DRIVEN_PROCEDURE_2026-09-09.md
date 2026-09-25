# Auditoría DB-driven procedure + garantías (2026-09-09/10)

## Misión
Semi-automatización de propuestas de licitación de obra para cualquier dependencia.
Fuente de verdad = DB. Backend evalúa; frontend opera extremo a extremo.
Nada de umbrales/porcentajes legales hardcodeados en runtime.

## Completado

### Procedimiento (DB)
- `procedure_thresholds` + ThresholdResolver fail-closed
- Selector + MotorJuridico sin umbrales_referencia en runtime
- Excepciones LegalRule domain=PROCEDURE_EXCEPTION (corpus LOPSRM/LAASSP)
- Endpoints recommend-procedure + UI semi-auto (select editable)

### Seeds CSV (listos para cargar)
`backend/app/data/seeds/`
- `procedure_thresholds.csv` (29 filas federales CANDIDATO)
- `procedure_exceptions.csv` (11 reglas)
- `jurisdiction_profiles.csv` (6 perfiles)

Export: `python scripts/export_procedure_seed_csv.py`
Load:  `python -m scripts.load_seeds_from_csv`

### Garantías DB-driven
`MotorGarantiasPenalizaciones` reescrito:
- Porcentajes desde LegalRule domain=GARANTIAS / PENALIZACIONES
- Fail-closed si no hay regla
- `ContratoService.crear_garantia` / `crear_penalizacion` async contra DB
- `legal_consultor` ya no inventa 10% ni 5% de seriedad sin regla

### Operación en entorno con Postgres
```bash
alembic upgrade head
python scripts/export_procedure_seed_csv.py
python -m scripts.load_seeds_from_csv
python -m scripts.seed_procedure_thresholds   # alternativo desde módulo
python -m scripts.seed_jurisdiction_profiles_state
python -m scripts.seed_procedure_exceptions
# corpus garantías (RLOPSRM 91, etc.):
python -m scripts.load_legal_corpus_articles
python scripts/verify_procedure_db_driven_offline.py
```

## Verificación offline
`verify_procedure_db_driven_offline.py` → ALL PASS
CSV integrity + ausencia de constantes TOPE_PENAS_PORCENTAJE / GARANTIA_CUMPLIMIENTO_MINIMA_OBRA → OK

## Pendiente producción (siguiente ciclo)
- Ejecutar seeders contra Postgres real y pruebas de integración API
- Cargar/confirmar Anexo 9 primario (pasar CANDIDATO → VERIFICADO)
- Vocabularios de catalog.py (PROCEDURES labels) → tabla de catálogo si se exige 0 hardcode de UI labels
- Garantía de seriedad: seed LegalRule cuando exista fundamento verificado

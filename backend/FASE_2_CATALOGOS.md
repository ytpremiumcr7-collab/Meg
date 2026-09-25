# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

# FASE 2: Catálogos Reales + SQLite Temporal

## Estado: ✅ COMPLETADO (Schema + Seed Data)

### Qué se armó

1. **Schema SQLite temporal** (`scripts/sqlite_dev_schema.sql`):
   - 30+ tablas con todas las relaciones del scaffold v2.0
   - Índices para búsqueda full-text y filtros
   - Compatible con el modelo SQLAlchemy existente

2. **Seed Data** (`scripts/sqlite_seed_data.sql`) con partes de catálogos reales:

   | Fuente | Archivo PDF | Conceptos de muestra |
   |--------|-------------|---------------------|
   | **CFE 2026** | `1039183160-CATALOGO-DE-PRECIOS-UNITARIOS-CFE-2026.pdf` | 9 conceptos (CT7-XXXXX, SR-XXXX). Rehabilitación de pozos y sondaje. Zonas I, II, III. Precios SIN IVA. |
   | **CMIC 2026** | `1030112820-Rehabilitacion-Pozos-2026.pdf` | 4 conceptos. Rehabilitación por diámetro (6"-10", 12"-16"). Urbano y Rural. |
   | **CONAGA SGIH 2026** | `CAT_LOGO_POR_GERENCIA_SGIH_2026.pdf` | 15 conceptos. Por gerencia (Distrito Riego, Unidad Riego, Temporal Tecnificado). Estados: Aguascalientes, Jalisco, Sinaloa. |
   | **Salarios Profesionales** | Referencia mercado 2026 | 10 salarios (ingeniero residente, supervisor, topógrafo, jefe de obra, etc.) |
   | **Maquinaria y Equipo** | Referencia mercado 2026 | 20 equipos (excavadoras, grúas, camiones, bombas, compresores, sondas, etc.) |
   | **Materiales** | Referencia mercado 2026 | 18 materiales (cemento, acero, PVC, agregados, aditivos, sellos) |
   | **Costos por m²/m³** | Referencia mercado 2026 | 8 conceptos (muros, cimentación, losas, concreto por resistencia) |

3. **README** (`scripts/README_SQLITE.md`) explicando que es temporal.

### Total de datos de muestra
- **25 conceptos** de catálogos oficiales (CFE + CMIC + CONAGA)
- **60 insumos** (materiales + mano de obra + maquinaria + salarios + costos por m²/m³)
- **1 tenant** + **1 usuario admin** de prueba

### ⚠️ Nota importante
Este SQLite es **TEMPORAL PARA DESARROLLO**. En producción:
- Se migra el schema a **PostgreSQL + PostGIS en Supabase**
- Se carga el **catálogo completo** vía ETL desde los PDFs oficiales
- Este SQLite se descarta

### Cómo usar
```bash
cd backend/scripts
sqlite3 megalodon_dev.db < sqlite_dev_schema.sql
sqlite3 megalodon_dev.db < sqlite_seed_data.sql
```

### Qué sigue (FASE 3)
Meterle carne a los módulos placeholder:
- `modules/workflow/` → Motor de estados
- `modules/trazabilidad/` → Bitácora inmutable con hash chain
- `modules/notifications/` → WebSocket push
- `modules/search/` → Full-text search

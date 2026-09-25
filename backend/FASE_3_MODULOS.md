# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

# FASE 3: Módulos Placeholder → Código Real

## Estado: 🔄 PENDIENTE

### Objetivo
Convertir los `.gitkeep` en módulos funcionales.

### Tareas
1. **modules/workflow/** — Motor de estados y transiciones:
   - `engine.py` — Validar transiciones según reglas
   - `models.py` — Estados, transiciones, tareas
   - Integración con expedientes existentes

2. **modules/trazabilidad/** — Bitácora inmutable:
   - `ledger.py` — Hash chain (Merkle light)
   - `service.py` — Registrar cada acción
   - Exportación para auditoría

3. **modules/notifications/** — Sistema de alertas:
   - `service.py` — Eventos internos → WebSocket push
   - `models.py` — Notificaciones, preferencias
   - Panel en el OS frontend

4. **modules/search/** — Búsqueda inteligente:
   - `engine.py` — Full-text en expedientes, documentos, conceptos
   - `filters.py` — Filtros avanzados

5. **modules/presupuestos/** — Capa de negocio:
   - `reglas.py` — Validación de sobrecostos
   - `comparativos.py` — Benchmarks de mercado

6. **modules/documentos/** — CDE real:
   - `cde.py` — Versionado, firma, sellado
   - `ocr_pipeline.py` — Extracción automática

### Archivos a crear
```
backend/app/modules/
  ├── workflow/engine.py
  ├── workflow/models.py
  ├── trazabilidad/ledger.py
  ├── trazabilidad/service.py
  ├── notifications/service.py
  ├── notifications/models.py
  ├── search/engine.py
  ├── presupuestos/reglas.py
  └── documentos/cde.py
```

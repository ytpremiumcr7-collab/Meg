# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

# FASE 4: Frontend — Apps Reales Conectadas

## Estado: 🔄 PENDIENTE

### Objetivo
Las 50 apps del OS conectan con el backend real.

### Tareas
1. **Conectar apps existentes**:
   - `megalodon-costos` → `/api/v1/presupuestos/`
   - `proyectos` → `/api/v1/expedientes/`
   - `star-map` → mantener como está (visual)

2. **Nuevas apps/vistas**:
   - **Documentos/CDE** — Subir, versionar, firmar, visualizar
   - **Licitaciones** — Flujo completo (convocatoria → fallo)
   - **Contratos** — Administración contractual + modificatorios
   - **Catálogos** — Buscador de conceptos con filtros por zona
   - **Compliance** — Checklists y dictámenes
   - **Riesgo** — Matriz + Monte Carlo visual
   - **Reportes/BI** — Tableros con datos reales
   - **Transparencia** — Vista pública del expediente

3. **WebSocket en el OS**:
   - Notificaciones en tiempo real (toast en taskbar)
   - Barra de progreso para OCR, BIM, Monte Carlo
   - Indicadores de actividad

4. **Pages + Apps (ambos modos)**:
   - Pages de React Router para navegación directa
   - Apps del OS (ventanas flotantes) para multitarea

### Archivos a modificar
- `frontend/app/src/App.tsx` — rutas nuevas
- `frontend/app/src/apps/` — nuevas apps
- `frontend/app/src/stores/` — stores para WebSocket

# Corrección de la auditoría BIM/costeo de octubre

Base: 51bcc08324183022a9f5867acc8f569deb99fb2c, rama codex/costeo-sesiones-2026-09-30.

- IFC: geometría SI sin segunda conversión; QTO usa unidad propia de longitud/área/volumen, incluida Unit explícita.
- Reprocesado: bloqueo del modelo, actualización por GlobalId, conservación de identidad/enlaces/zonas y reemplazo atómico. Lecturas sin malla devuelven copias.
- Enlaces: validación completa del lote antes de escribir, mismo tenant y expediente; nueva migración PostgreSQL con identidad única, FK de modelo y triggers de integridad.
- Costeo: cantidades faltantes permanecen en cero y BORRADOR. Un grupo parcialmente medible también queda pendiente. No se valida/aprueba con cantidades/precios/importes incompletos.
- Acceso: API aplica el catálogo de módulos del launcher y roles de escritura; aprobación requiere revisor/admin/superadmin.
- Uso: crear, recalcular y cambiar parámetros reservan corridas en la misma transacción del presupuesto; las exportaciones de un presupuesto existente no consumen una nueva corrida.
- Storage: claves por UUID, independientes de nombre/contador; carga BIM sin sobrescribir y limpieza ante fallo de commit. Rechazo del broker queda como ERROR y HTTP 503.
- WebSocket: identidad resuelta por AuthService, revalidación en cada mensaje y cada 30 segundos de inactividad.
- CI: chequeo del intérprete .venv explícito y auditoría de las dependencias exportadas desde uv.lock.

## Validación y límites

Las pruebas SQLite usan modelos actuales y Redis real. Los triggers y bloqueos PostgreSQL se verifican en CI con esquema migrado. SQLite no acredita esas garantías ni sustituye PostGIS. La migración se detiene ante duplicados/enlaces históricos incompatibles; no elimina evidencia automáticamente. Antes de producción, respaldar la BD y reparar conflictos que reporte la migración.

El importador BIM recibe IFC. El DWG cs06 suministrado se inspecciona por separado; convertir un plano a DXF no aporta automáticamente cantidades BIM ni precios. Un fallo del proceso API entre commit y publicación al broker todavía requiere reconciliación operativa: no hay outbox transaccional en este bloque.

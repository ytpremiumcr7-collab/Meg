# Fase 1 — Clean-room build y hardening mínimo de arranque

## Hecho en esta iteración
- `frontend/app/vite.config.ts` quedó con `inspectAttr()` solo en desarrollo.
- `frontend/app/tailwind.config.js` quedó en ESM limpio con `tailwindcss-animate` importado correctamente.
- Se conserva el árbol funcional; no se eliminaron piezas de código fuente por limpieza cosmética.

## Siguiente verificación obligatoria
- Ejecutar `npm ci` real en frontend y `npm run build`.
- Ejecutar build de Docker en entorno limpio.
- Validar que no queden configs CommonJS residuales dentro de un paquete ESM.

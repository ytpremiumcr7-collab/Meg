# Migraciones y recuperación

La migración `20260930_identity_authority` no permite `downgrade`. Suprimir
`users.auth_version` y recrearlo en cero puede volver a aceptar tokens revocados.
La restricción también bloquea descender por debajo de esta revisión desde revisiones
posteriores. Una corrección futura debe conservar o aumentar las versiones de sesión.

El job `migration-recovery` usa un servicio PostGIS 16/3.4 independiente de los tests
normales. `python -m scripts.verify_migration_recovery_ci` exige GitHub Actions,
staging, una base local dedicada y una instalación fresca. No es un comando de
migración para servidores desplegados.

El ensayo crea dos organizaciones en `20260914_workspace_bridge_tenant`, con
identificadores coincidentes, presupuestos decimales explícitos, partidas, conceptos,
insumos, programas, actividades, autores, un webhook y fechas UTC históricas de
Tezcatlipoca. Prueba que una autoría inválida aborta todo el upgrade sin cambios
parciales; corrige la referencia del fixture y migra hasta head. Compara los valores
anteriores con las transformaciones documentadas, sin inventar riesgo presupuestario.
La base usa una zona horaria distinta de UTC para detectar conversiones implícitas.

Se intentan escrituras cruzadas entre organizaciones en las seis tablas y se exige
rechazo por claves foráneas de PostgreSQL. También se exige que un downgrade
inseguro conserve datos, esquema, revisión Alembic y versiones de revocación.

Finalmente se ejecutan los scripts operativos `backup_postgres.sh` y
`restore_postgres.sh`: `pg_dump -Fc` y `pg_restore --single-transaction
--exit-on-error --no-owner --no-privileges` sobre una segunda base vacía. Se comparan
los datos del ensayo, columnas, claves foráneas, unicidad y checks del esquema, y se
verifican geometrías PostGIS 3D y las secuencias. Se rechazan checksums ausentes o
incorrectos y una segunda restauración sobre la base ya poblada. Solo el informe sanitizado se publica como artefacto
de CI; el respaldo temporal se elimina. La prueba no valida roles/grants de despliegue.

Los scripts requieren el Python del backend con dependencias instaladas, y clientes
`pg_dump`, `pg_restore` y `psql` de una versión compatible con el servidor y el archivo.
En CI se fijan clientes de PostgreSQL 16. Las URL `postgresql+asyncpg` de la aplicación
se traducen al contrato libpq; la contraseña se entrega en un archivo efímero 0600,
sin incluirla en argumentos del proceso. El dump es privado, se publica solo al terminar
y lleva un SHA-256 obligatorio con nombre relativo para permitir mover el respaldo.
La restauración exige una base vacía creada con `template0`, no elimina objetos
existentes y aborta en una única transacción. Mantener los escritores detenidos durante
la verificación y restauración. El checksum detecta corrupción, no acredita la confianza
del origen: restaurar únicamente respaldos propios y controlados.

Para recuperar un despliegue real:

1. Cerrar tráfico y detener API, workers y demás escritores. Conservar una copia
   del estado fallido y los artefactos externos antes de cualquier operación destructiva.
2. Restaurar un respaldo verificado en una base aislada con versión PostgreSQL/PostGIS
   compatible. `pg_dump` no contiene roles del clúster ni objetos del almacenamiento
   externo: recuperar y verificar también permisos, secretos, archivos y referencias.
3. Seleccionar código compatible con la revisión restaurada. Si se avanza, ejecutar
   Alembic explícitamente y verificar el esquema; el arranque no repara la base.
4. Rotar `SECRET_KEY` en todos los procesos que emiten o verifican JWT, eliminando
   las claves anteriores. Un respaldo puede retroceder contadores de autoridad;
   conservarlos en el dump por sí solo no garantiza la revocación posterior al respaldo.
   No abrir tráfico con un código que ignore `auth_version` ni con claves antiguas.
5. Reaprovisionar un rol de ejecución sin DDL, comprobar aislamiento, auditoría,
   referencias a archivos, health/ready, login y flujos reales. Solo entonces reabrir
   tráfico y registrar los tiempos y las pérdidas de datos observadas.

Para declarar GO faltan un ensayo con una copia representativa de datos reales,
RPO/RTO medidos, recuperación de roles y artefactos externos, y validación del
despliegue final. Este ensayo sintético no certifica todas las instalaciones históricas.

Referencias contrastadas:

- PostgreSQL 16, pg_dump: https://www.postgresql.org/docs/16/app-pgdump.html
- PostgreSQL 16, pg_restore: https://www.postgresql.org/docs/16/app-pgrestore.html
- Alembic, limitaciones de migración de datos y downgrade, discusión de mantenedores:
  https://github.com/sqlalchemy/alembic/discussions/972
- Implementación de restauración de PostgreSQL:
  https://github.com/postgres/postgres/blob/REL_16_STABLE/src/bin/pg_dump/pg_restore.c
- PostgreSQL, contrato de conexión y archivos de contraseña:
  https://www.postgresql.org/docs/16/libpq-connect.html
  https://www.postgresql.org/docs/16/libpq-pgpass.html
- pgBackRest, recuperación aislada y verificación de respaldos (referencia operativa;
  no es una dependencia añadida): https://pgbackrest.org/user-guide.html

# Auditoría BIM/4D/5D y endurecimiento

Base tomada: `megalodon_v8_2_BIM4D5D_tenant_restaurado.zip` y versión mergeada más completa como referencia de mejoras.

## Mapa BIM/4D/5D

Frontend BIM/Programación → API v1 BIM/Programación → `BIMService` / `ProgramacionService` → motores `MotorBIM` / `MotorCPM` → modelos ORM (`ModeloBIM`, `ElementoBIM`, `ProgramaObra`, `ActividadPrograma`) → persistencia.

## Mejoras reintegradas

- Heurística pura para 4D en `app/engines/bim/heuristics.py`.
- Cálculo 4D ya no depende solo de una duración fija: usa tamaño del grupo + magnitud geométrica.
- `motor_bim.py` quedó con logger definido.
- Defaults mutables en schemas/API de programación y presupuesto sustituidos por `Field(default_factory=...)`.
- Comentarios de negocio ajustados para eliminar lenguaje de placeholder/stub.
- Pruebas unitarias fuente-based y puras para 4D y defaults de contratos.

## Pruebas ejecutadas

- `python -m compileall -q backend/app backend/structlog` ✅
- `pytest -q --confcutdir=tests/unit tests/unit/test_bim_heuristics.py tests/unit/test_programacion_schema_defaults.py tests/unit/test_no_silence_industrial.py` ✅

## Límite del sandbox

Se intentó instalar dependencias con `pip`, pero el índice accesible no resolvió `structlog`, `redis`, `celery`, `python-dotenv` ni `aioredis`. Para no maquillar el resultado, se dejó compatibilidad local mínima para `structlog` y el árbol se mantuvo sin mutilar la lógica de negocio.

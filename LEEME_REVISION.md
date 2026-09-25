<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Motor jurídico multi-jurisdicción — resumen

## Qué se construyó

- `app/engines/juridico/umbrales_referencia.py` (nuevo): registro de
  umbrales versionado por jurisdicción/ley/tipo/año, con **tramos
  escalonados** (el Anexo 9 federal varía por presupuesto autorizado de
  la dependencia, no es un monto único) y **estado tri-nivel** por
  registro: `VERIFICADO` (confirmado contra fuente primaria) /
  `CANDIDATO` (citado por investigación, sin confirmar) / `PENDIENTE`
  (sin ningún dato).
- `app/engines/juridico/motor_juridico.py` reescrito: nunca inventa un
  número. Sin dato → `SIN_DETERMINAR` explícito. Con dato candidato →
  sí calcula, pero marca `es_candidato=true` y mete una advertencia en
  observaciones. Solo con `VERIFICADO` da `datos_verificados=true`.
- `app/services/juridico_service.py` y `app/api/v1/juridico.py`
  reescritos para pasar `jurisdiccion`, `ejercicio_fiscal` y
  `presupuesto_dependencia_miles` de punta a punta, y nuevo endpoint
  `GET /juridico/jurisdicciones`.
- Cliente TS actualizado en ambos lados (backend y frontend, sincronizados
  idénticos): `ResultadoJuridico` con `datos_verificados`/`es_candidato`/
  `fuente_umbral`, más `jurisdiccionesDisponibles()`.
- `megalodon-costos` (frontend): badge visible naranja cuando el dato es
  candidato, badge rojo cuando no se pudo determinar -- antes esto solo
  aparecía enterrado en una lista de observaciones.

## Por qué NO se cargaron cifras como "verificadas"

Se recibieron 2 documentos de "investigación" con cifras del Anexo 9
2026. Antes de cargarlos se cruzaron entre sí:
- La tabla de **Obra Pública** coincidió exacta (15 filas, cifra por
  cifra) entre ambos documentos -- pero eso no es tranquilizador, es
  sospechoso: sugiere que ambos pudieron copiar de la misma fuente
  secundaria no primaria, no que ambos verificaron independiente.
- La tabla de **Adquisiciones** difirió 7x entre los dos documentos (uno
  daba ~$2.2M plano, el otro una tabla escalonada de $309k a $1,145k)
  -- desacuerdo real, sin resolver.
- Un documento previo citó el artículo equivocado del PEF (Art. 12 en
  vez de Art. 3 fracc. X) y mezcló el Anexo 9 del PEF con el Anexo 9 de
  la RMF (SAT) -- son documentos distintos, se descartó ese por error
  verificable.

Se cargaron las cifras como **CANDIDATO** (no VERIFICADO): el motor las
usa y da una respuesta, pero la marca sin confirmar en cada nivel
(`observaciones`, `es_candidato`, `datos_verificados=false`) para que
nadie las use como fundamento único de una decisión de cumplimiento
real sin confirmar contra el documento primario.

## Bug real encontrado en pruebas (no solo `py_compile`)

`jurisdicciones_disponibles()` tenía una comparación `>` estricta contra
un valor por default que hacía que las jurisdicciones cuyo ÚNICO
registro fuera `PENDIENTE` (CDMX, Edomex, Jalisco) desaparecieran por
completo de la lista en vez de aparecer como pendientes -- se encontró
corriendo la función de verdad, no leyendo el código, y se corrigió.

## Otro bug real encontrado de paso

`checklist_requisitos()` (ya existía antes de esta sesión) armaba el
checklist llamando a `determinar_procedimiento()` con un monto dummy
fijo de $1,000,000 -- frágil incluso antes del rediseño (si alguien
pedía el checklist de LICITACION_PUBLICA pero $1,000,000 caía en
adjudicación directa con los umbrales reales, regresaba los requisitos
equivocados en silencio). Se separó en `MotorJuridico.obtener_requisitos()`,
que no depende de ningún umbral -- los requisitos dependen de qué
procedimiento es, no de si el monto está verificado.

## Para completar (mismo patrón que la ronda de clash detection)

Editar `umbrales_referencia.py`: cambiar `estado_dato` a `VERIFICADO`
en el registro correspondiente cuando se confirme contra el Anexo 9 real
(aunque sea leyendo una captura de pantalla con visión, no hace falta
extracción de texto). No requiere tocar `motor_juridico.py`.
Pendientes: CDMX, Estado de México y Jalisco siguen en `PENDIENTE` (sin
ningún dato, ni siquiera candidato) -- ver notas en cada registro.

## Verificación real hecha

- `py_compile` completo del backend -- OK.
- `tsc --noEmit` completo del cliente TS -- OK.
- 8 casos de prueba con ejecución real de Python (no solo sintaxis):
  sin presupuesto de dependencia, con presupuesto (tramo chico y
  grande), LAASSP vs LOPSRM, jurisdicción sin datos, validar_monto con
  advertencia de fraccionamiento, jurisdicciones_disponibles.
- El bug de `jurisdicciones_disponibles()` se encontró precisamente por
  correr estas pruebas, no se habría visto solo leyendo el código.

## Actualización: Tlaxcala agregada

Del zip `catalogoscompletos` subiste `Ley de Obras Públicas Tlaxcala y
sus Municipios-240523.pdf` -- a diferencia de los "research" de Anexo 9,
este es un PDF con texto real (generado en Word, no escaneado), así que
se leyó **directo**, sin intermediarios.

Confirmado contra el texto primario:
- Ley: "Ley de Obras Públicas para el Estado de Tlaxcala y sus
  Municipios", última reforma 24-may-2023.
- Art. 46-47: excepciones a licitación pública.
- Art. 48: remite los montos al **Presupuesto de Egresos del Estado**
  -- mismo mecanismo que federal (la ley no trae los montos, un decreto
  anual aparte sí).
- Art. 50: tope agregado del 20% del presupuesto de obra pública para
  adjudicación directa -- idéntico al 20% de LOPSRM federal (Art. 43).

Se agregó `Jurisdiccion.TLAXCALA` con la ley/artículos ya en estado
verificado (leídos de fuente primaria), pero los montos en pesos siguen
`PENDIENTE` -- falta el Presupuesto de Egresos del Estado de Tlaxcala
del ejercicio vigente, que no venía en el PDF.

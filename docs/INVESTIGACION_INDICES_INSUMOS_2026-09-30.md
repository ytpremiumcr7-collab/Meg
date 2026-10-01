# Investigación de índices por insumo para Megalodon

Fecha de corte: 30 de septiembre de 2026, hora de México. Investigación descriptiva; no se cambiaron precios ni se implementó un motor con estos hallazgos.

## Charter

Objetivo: localizar y contrastar fuentes originales de variación de costos por insumo o familia para actualizar las estimaciones de los catálogos de enero de 2026 al mes destino, sin aplicar un porcentaje global a todos los componentes.

Scope: actualización de estimaciones de construcción en México. Object: Megalodon y sus catálogos con fecha base de enero. Subject: publicaciones CMIC, Varela e INEGI de 2026.

Preguntas: Q1, ¿el mes del título es de publicación o de observación? Q2, ¿hay desglose y son niveles de índice, tasas mensuales, anuales o acumuladas? Q3, ¿qué acceso, metodología y metadatos están disponibles? Q4, ¿qué datos pueden utilizarse y cuáles faltan?

Orden de evidencia: 1, fuente originadora; 2, metodología original; 3, tabla original; 4, comunidad o distribuidores para localizar y contrastar originales. Los resultados de buscador no sustituyen la lectura de la fuente.

## Canonical sources

| ID | Fuente original abierta | Alcance comprobado |
|---|---|---|
| V1 | [Software m2](https://varela.com.mx/software-m2/) | Descripción del sistema, periodicidad de actualizaciones y acceso por suscripción. |
| V2 | [Índice Varela, septiembre 2018](https://varela.com.mx/indice-varela-2018-septiembre/) | Comparación anual entre septiembre de 2017 y septiembre de 2018. |
| V3 | [Tema índiceVarela](https://varela.com.mx/tema/indicevarela/) | Artículos históricos de 2017 y 2018; no se verificó allí una tabla de 2026. |
| V4 | [Archivo 2026](https://varela.com.mx/2026/) | Artículos publicados durante 2026. La entrada de septiembre trata errores de IA en ingeniería de costos. |
| V5 | [Archivo de actualizaciones 2007–2014](https://varela.com.mx/software-m2/actualizaciones-2007-2014/) | Archivo histórico al que redirigieron los enlaces abiertos de actualizaciones. |
| V6 | [Contrato del editor](https://varela.com.mx/contrato/) | Clases de publicaciones, frecuencia declarada y condiciones de acceso/uso. |
| C1 | [CMIC/CEICO septiembre 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/09_Septiembre/CEICO_Informe_Septiembre_2026_Variacion_precio_materiales.pdf) | Publicado el 11 de septiembre; referencia agosto 2025–agosto 2026; siguiente actualización anunciada el 16 de octubre. PDF original abierto completo como texto. |
| C2 | [CMIC/CEICO agosto 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/08_Agosto/CEICO_Informe_Agosto_2026_Variacion_precio_materiales.pdf) | Desglose por insumo y discrepancia interna del periodo. PDF original abierto completo como texto. |
| I1 | [INEGI INPP, septiembre 2026](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/inpp/inpp2026_09.pdf) | Publicación 9 de septiembre, observaciones agosto; siguiente publicación anunciada 8 de octubre. Cuadros mensuales y anuales diferenciados. |

CMIC C1/C2 utiliza datos de INEGI: dos editores no equivalen a dos mediciones estadísticas independientes. Varela aporta otra metodología/editor; no se obtuvo una serie numérica pública actual comparable. Rango 1 para los documentos de sus respectivos autores; comunidad/distribuidores tienen rango 4 y sólo sirven para ubicar originales.

## Findings ledger

| ID | Afirmación verificable | Evidencia / rango | Responde |
|---|---|---|---|
| C01 | Existe el informe CMIC de septiembre de 2026; su observación corresponde a agosto, no a septiembre. Anuncia 16 de octubre como próxima actualización, sin acreditar que ya exista esa edición. | C1, portada y páginas 2–3 / 1 | Q1, Q3 |
| C02 | Las variaciones publicadas por insumo son distintas: tubos de cobre 22.27%; cables con aislamiento 17.15%; lubricantes 16.88%; tubería de plástico 16.35%; aluminio 11.62%. Todas son anuales agosto 2025–agosto 2026. | C1, páginas 2–3 / 1 | Q2 |
| C03 | El mismo gráfico presenta gasolina 9.49%, soldaduras 8.53%, asfalto/mezclas 8.44%, otros productos de concreto 8.30% y cal hidratada 7.77%. Son tasas anuales, no factores enero–agosto. | C1, página 3, etiquetas en extracción de texto / 1 | Q2 |
| C04 | C1 distingue precios al productor LAB sin impuestos y precios mayoristas del ICC con impuestos y entrega en obra. No son bases intercambiables por tener nombres similares. | C1, página 4 / 1 | Q3, Q4 |
| C05 | C2 página 2 escribe julio 2025–junio 2026; su gráfico de página 3 y texto de página 5 indican julio 2025–julio 2026. La discrepancia requiere contraste antes de ingesta. | C2, páginas 2, 3 y 5 / 1; observación de texto | Q1, Q4 |
| I01 | I1 confirma para agosto Construcción 0.16% mensual y 5.91% anual; el 5.91% coincide con C1, pero ambos remiten a la misma medición. | I1, cuadro 1, página 2; C1, página 2 / 1 | Q1, Q3 |
| I02 | I1 cuadro 3 registra en agosto gasolina +4.96% mensual y diésel −11.90% mensual. Un motor debe admitir decrementos y no confundir tasas mensuales con anuales. | I1, página 5 / 1 | Q2, Q4 |

La extracción textual de los gráficos no acredita revisión visual completa: el servicio de capturas devolvió referencias de imagen sin entregar píxeles utilizables en esta ronda. Se transcriben sólo valores con etiquetas legibles y se mantiene pendiente la gráfica comparativa completa de materiales, página 4. No se certifica todo el PDF ni se modificó el CSV del usuario.

Hallazgos de la revisión de Varela (documentos originales abiertos por el investigador encargado):

| Hallazgo | Evidencia | Estado e implicación |
|---|---|---|
| Varela anuncia para m2 actualizaciones en enero, abril, julio y octubre. | V1, apartado de características y Actualizaciones. | Verificado. La periodicidad declarada es trimestral, no mensual. Que octubre sea uno de los meses programados no acredita que la edición octubre 2026 ya esté publicada. |
| Las actualizaciones de m2 requieren suscripción vigente. | V1, apartado Actualizaciones. | Verificado. No se descargó ni se adquirió una actualización. |
| El índice público de septiembre que se encontró corresponde a 2018. | V2 y V3, fecha y comparación explícita. | Verificado. No sirve como observación de septiembre de 2026 ni como tasa mensual de 2026. |
| La entrada de septiembre de 2026 del archivo anual es un artículo sobre errores de IA. | V4, fecha y texto. | Verificado. Un enlace con septiembre 2026 en archivos o navegación no demuestra un informe de variaciones de precios. |
| Los enlaces de actualización abiertos llevan a archivos 2007–2014. | V5, destino de redirección y fechas de versiones. | Verificado para las rutas revisadas. No demuestra que el editor carezca de actualizaciones privadas actuales. |
| El contrato distingue actualizaciones trimestrales de clase A y semestrales de clase C. | V6, definición de obras y frecuencia. | Verificado. No extrapolar la frecuencia de m2 a todos los libros de costos unitarios. |
| No se encontró una tabla primaria pública verificable de Varela, septiembre 2026, con series mensuales por insumo. | Tres rondas acotadas de localización y apertura de V1–V6. | No encontrado en esta revisión; no es una afirmación de inexistencia. No permite inventar coeficientes ni convertir índices agregados históricos en cambios actuales por material. |

## Scope filter

Se excluyen índices de Argentina, personas homónimas y enlaces que sólo mencionan 2026 en navegación. Se conserva V2 únicamente para acreditar la existencia histórica de Ivar y demostrar el riesgo de confundir fechas. No se emplea como dato operativo.

Se conserva C02/C03 como evidencia de variación desigual por insumo, nunca como factores desde enero. No se interpreta la comparación de dos tasas anuales sucesivas como cambio mensual. Se descartan resultados de afiliaciones, facturación, producción física y actividad económica que no son índices de precios. Las copias comunitarias no convierten una medición INEGI en corroboración independiente.

## Object filter

Los catálogos existentes y su precio original permanecen intactos. Las frecuencias de publicación, factores interciudad, índices de inflación y precios de ensamble son objetos diferentes; no deben combinarse como si fueran una misma serie. No se verificó una correspondencia entre ítems del catálogo de Megalodon y familias de un índice Varela actual.

La recomendación se restringe a actualizar estimaciones con series pertinentes. No basta el índice nacional de Construcción para actualizar todos los componentes de Megalodon. El factor enero→destino de cada insumo requiere niveles de índice de esos dos meses o una cadena completa de tasas mensuales de la misma serie. La existencia de un informe de septiembre no demuestra que ya haya precios observados de septiembre en él. C05 debe quedar como conflicto de metadatos, con la fuente intacta, hasta resolverlo con la serie originaria. Se permiten bajas de precios (I02).

## Conclusions

1. **El informe de septiembre solicitado sí existe** y ofrece desglose por insumo. Su referencia es agosto de 2026 y contiene tasas anuales; confirma la necesidad de tratar los insumos por separado (C01–C03).
2. **Octubre tiene fechas anunciadas diferentes**: CMIC 16 de octubre; INEGI 8 de octubre. Son calendarios declarados, no observaciones futuras verificadas (C01, I1).
3. **La selección de serie importa tanto como la fecha**: productor sin impuestos y mayorista con impuestos/entrega no deben mezclarse indiscriminadamente. El motor debe admitir movimientos negativos (C04, I02).
4. **Todavía no hay un conjunto operativo completo enero→destino por todos los insumos de Megalodon**: faltan niveles o tasas mensuales, cobertura y correspondencias verificadas. Los diez insumos destacados no cubren un catálogo entero (C02–C04 y preguntas abiertas de Q4).

La evidencia abierta de Varela confirma productos de costos con actualizaciones periódicas y un índice histórico, pero no acredita una serie mensual pública de 2026 por insumo utilizable ahora en Megalodon. La vía pública verificada para actualización mensual debe resolverse con las tablas e índices originarios disponibles; una fuente privada puede agregarse si se dispone de sus datos y condiciones de uso aplicables. No se debe sustituir una categoría sin datos por el porcentaje global de construcción.

## Next steps / Risks

- Consolidación CMIC/INEGI/Varela realizada en este único documento; las cifras siguen siendo evidencia de investigación, no entradas activadas de producción.
- Seleccionar tablas con niveles o cambios mensuales realmente comparables y documentar la correspondencia de cada insumo.
- Conservar fecha base, fuente, serie, unidad, ámbito geográfico y versiones metodológicas; una variación anual no puede encadenarse como si fuera mensual.
- No presentar una actualización Varela octubre 2026 como disponible hasta abrir la edición o el registro original correspondiente.
- Parallel Search alcanzó el límite gratuito; las verificaciones restantes se realizaron con apertura directa y otro servicio de búsqueda. La restricción de una herramienta no prueba ausencia de una fuente.

### Protocolo propuesto para la siguiente implementación

1. Obtener la serie completa por material/familia y ámbito aplicable; guardar identificador, descripción, metodología, mes observado y fecha de publicación. Elegir según las condiciones de precio documentadas, no por similitud de etiquetas (C04).
2. Acreditar el mes de precios de cada catálogo, separándolo del mes de edición. El usuario establece enero para el CSV y la mayoría de CMIC; no extender esa fecha a todas las fuentes sin confirmación.
3. Registrar correspondencias revisadas entre insumo y serie. Cuando no haya una correspondencia sustentada, indicar falta de cobertura; no aplicar un porcentaje global oculto (C02–C04).
4. Calcular precio_original × índice_destino / índice_base, o su equivalente con tasas mensuales completas. Usar decimales, política de redondeo explícita y origen inmutable. No usar C02/C03 como sustituto de esa cadena.
5. Con desglose APU válido, actualizar cada componente y recalcular el concepto conservando cantidades/rendimientos. Combustible, lubricantes, operación y costos fijos de maquinaria requieren su propio modelo; no multiplicar todo por el diésel (C02, I02; decisión de diseño derivada).
6. Conservar las versiones utilizadas en cada presupuesto para reproducirlo aunque una serie sea revisada; registrar conflictos como C05 antes de activar datos.

### Criterios de aceptación pendientes

- [ ] Serie y metadatos originales completos para cada familia activada; meses enero→destino sin huecos.
- [ ] Correspondencias por insumo con alcance y procedencia; cobertura y ausencias visibles.
- [ ] Contraste de resultados con fuente original para meses, tasas mensuales/anuales y condiciones de impuestos/entrega.
- [ ] Resolución de la discrepancia C05 y revisión visual de tablas/gráficos utilizados en ingesta.
- [ ] Pruebas de mismo mes, movimientos negativos, periodos incompletos, cambios metodológicos y doble actualización.
- [ ] APU válido antes de recomponer; conservar precios impresos y CSV original sin inferencias.
- [ ] Separar resultados con observaciones publicadas de pronósticos; ninguna funcionalidad predictiva fue ejecutada en esta investigación.

### Límites abiertos

No se descargaron las series completas por insumo ni se calcularon factores enero→agosto por material. No se acreditó una tabla Varela septiembre 2026. El informe residencial CMIC de septiembre no pudo abrirse por la ruta revisada; no se afirma que no exista. Los resultados de comunidad no aportaron una serie nueva independiente y verificable. La búsqueda pública fue acotada, no exhaustiva.

Revisión de evidencia: afirmaciones C01–C05/I01–I02 contrastadas con texto de los originales; fechas de portada separadas del periodo medido. El juicio sobre la discrepancia C05 es observación textual, no corrección del original. Las conclusiones numéricas se limitan a los datos legibles y su periodo declarado. El documento constituye investigación y especificación condicionada; no prueba integración ni preparación para producción.

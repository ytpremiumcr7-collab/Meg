# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
BIMService - Gestión de modelos IFC: cuantificación real, persistencia y
enlace con presupuestos.

BUG ORIGINAL: procesar_ifc() nunca persistía nada en BD (ni el ModeloBIM
ni los ElementoBIM) -- solo regresaba un dict de la request y se perdía
todo. Ahora sí queda guardado, incluida la malla para renderizar en el
frontend y el puente elemento->partida.
"""
import os
try:
    import structlog  # type: ignore
    logger = structlog.get_logger()
except ModuleNotFoundError:  # pragma: no cover - compatibilidad de entorno
    import logging
    logger = logging.getLogger(__name__)

import tempfile
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presupuesto import Presupuesto, Partida
from app.models.bim import ModeloBIM, ElementoBIM
from app.models.base import EstadoProceso
from app.models.expediente import ExpedienteObra
from app.engines.bim.motor_bim import MotorBIM
from app.engines.bim.heuristics import estimar_duracion_4d, resumir_grupo_bim4d
from app.integrations.supabase_storage import storage_bim
from app.core.errors import MegalodonException, ErrorCode
from app.engines.costos.parametros import ParametrosCosteoSnapshot

if TYPE_CHECKING:
    from app.models.programacion import ProgramaObra

# Tipos cuyo insumo relevante es área (m2) en vez de volumen (m3).
TIPOS_POR_AREA = {"IfcWall", "IfcSlab", "IfcRoof", "IfcCovering"}
TIPOS_POR_PIEZA = {"IfcDoor", "IfcWindow"}


class BIMService:
    """Servicio de procesamiento BIM/IFC."""

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID | str] = None):
        self.db = db
        self.tenant_id = UUID(str(tenant_id)) if tenant_id is not None else None
        self.motor = MotorBIM()

    async def listar_modelos(self, expediente_id: UUID) -> List[ModeloBIM]:
        """Lista los modelos BIM de un expediente (más reciente primero).

        BUG ORIGINAL: no existía ningún endpoint para enumerar los modelos
        de un expediente -- solo se podía pedir un modelo si ya sabías su
        modelo_id de antemano (ej. guardado en otra pantalla).
        """
        result = await self.db.execute(
            select(ModeloBIM)
            .where(ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self.tenant_id)
            .order_by(ModeloBIM.created_at.desc())
        )
        return list(result.scalars().all())

    async def crear_modelo(
        self,
        *,
        expediente_id: UUID,
        nombre: str,
        file_content: bytes,
        filename: str,
        descripcion: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> ModeloBIM:
        """Registra un modelo BIM y sube el IFC original a Supabase
        Storage. El path guardado en BD es el path DENTRO del bucket
        (nunca una URL firmada -- esas expiran; se genera al vuelo cuando
        se necesite descargar, vía SupabaseStorage.url_firmada)."""
        result = await self.db.execute(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id))
        expediente_obj = result.scalar_one_or_none()
        if not expediente_obj:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")

        count_result = await self.db.execute(select(ModeloBIM).where(ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self.tenant_id))
        count = len(count_result.scalars().all()) + 1
        identificador = f"BIM-{str(expediente_id)[:8]}-{count:03d}"

        ruta_storage = f"tenant/{self.tenant_id}/{expediente_id}/{identificador}-{filename}"
        await storage_bim().subir(ruta_storage, file_content, content_type="application/x-step")

        modelo = ModeloBIM(
            id=uuid4(),
            expediente_id=expediente_id,
            tenant_id=expediente_obj.tenant_id,
            identificador=identificador,
            nombre=nombre,
            descripcion=descripcion,
            ruta_archivo=ruta_storage,
            tamano_bytes=len(file_content),
            estado_procesamiento=EstadoProceso.PENDIENTE.value,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(modelo)
        await self.db.commit()
        await self.db.refresh(modelo)
        return modelo

    async def _validar_modelo_en_expediente(self, modelo_id: UUID, expediente_id: UUID) -> ModeloBIM:
        """Obtiene el modelo y verifica que pertenezca al expediente de la URL.
        Levanta 404 si no existe o si el expediente no coincide (no 403, para
        no revelar que el modelo existe bajo otro expediente)."""
        modelo = (await self.db.execute(select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self.tenant_id))).scalar_one_or_none()
        if not modelo or str(modelo.expediente_id) != str(expediente_id) or (self.tenant_id is not None and str(modelo.tenant_id) != str(self.tenant_id)):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Modelo BIM {modelo_id} no encontrado en el expediente {expediente_id}",
            )
        return modelo

    async def url_descarga_modelo(self, modelo_id: UUID, expediente_id: UUID, expira_segundos: int = 3600) -> str:
        """URL temporal para descargar el IFC original directo de storage."""
        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        url = await storage_bim().url_firmada(modelo.ruta_archivo, expira_segundos)
        if not url:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "No se pudo generar la URL de descarga")
        return url

    async def procesar_ifc(
        self,
        *,
        modelo_id: UUID,
        file_content: bytes,
        tipos_elementos: Optional[List[str]] = None,
        extraer_malla: bool = True,
    ) -> ModeloBIM:
        """Procesa el IFC de un ModeloBIM ya registrado: cuantifica y
        persiste elementos reales. Deja el modelo en COMPLETADO o ERROR."""
        modelo = (await self.db.execute(select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.tenant_id == self.tenant_id))).scalar_one_or_none()
        if not modelo:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Modelo BIM {modelo_id} no encontrado")

        modelo.estado_procesamiento = EstadoProceso.EN_PROCESO.value
        modelo.tamano_bytes = len(file_content)
        await self.db.commit()

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            ifc_file = self.motor.cargar_ifc(tmp_path)
            try:
                modelo.version_ifc = ifc_file.schema
            except Exception as e:
                # No crítico -- el procesamiento sigue sin la versión de
                # schema, pero se deja traza porque un IFC del que no se
                # puede leer ni el schema suele indicar un archivo
                # corrupto o un parser desactualizado.
                logger.debug("bim_service.procesar_ifc: no se pudo leer version_ifc", modelo_id=str(modelo_id), error=str(e))

            resultado = self.motor.cuantificar(tipos_elementos, extraer_malla=extraer_malla)

            for elem in resultado.elementos:
                self.db.add(ElementoBIM(
                    id=uuid4(),
                    modelo_id=modelo.id,
                    global_id=elem.global_id,
                    express_id=elem.express_id,
                    tipo=elem.tipo,
                    nombre=elem.nombre,
                    volumen=elem.volumen,
                    area=elem.area,
                    longitud=elem.longitud,
                    fuente_volumen=elem.fuente_volumen,
                    fuente_area=elem.fuente_area,
                    nivel=elem.nivel,
                    bbox=elem.bbox,
                    propiedades=elem.propiedades,
                    malla_vertices=elem.malla.vertices if elem.malla else None,
                    malla_caras=elem.malla.caras if elem.malla else None,
                ))

            modelo.num_elementos = len(resultado.elementos)
            modelo.niveles = resultado.niveles
            # Si TODOS los elementos fallaron, es un error real; si solo
            # algunos, se deja COMPLETADO pero con el detalle en
            # error_procesamiento para que no se pierda silenciosamente.
            if resultado.elementos:
                modelo.estado_procesamiento = EstadoProceso.COMPLETADO.value
            else:
                modelo.estado_procesamiento = EstadoProceso.ERROR.value

            if resultado.errores:
                modelo.error_procesamiento = "; ".join(resultado.errores[:20])

            await self.db.commit()
            await self.db.refresh(modelo)
            return modelo

        except Exception as e:
            # Antes: el error solo quedaba en error_procesamiento (DB),
            # invisible en logs/observabilidad server-side hasta que
            # alguien abriera ese modelo puntual. Se relanza igual (el
            # caller/worker decide reintentar), pero ahora también queda
            # en logs con contexto de qué modelo falló.
            logger.exception("bim_service.procesar_ifc: fallo procesando IFC", modelo_id=str(modelo_id), error=str(e))
            modelo.estado_procesamiento = EstadoProceso.ERROR.value
            modelo.error_procesamiento = str(e)
            await self.db.commit()
            raise
        finally:
            os.unlink(tmp_path)

    async def listar_elementos(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        tipo: Optional[str] = None,
        nivel: Optional[str] = None,
        incluir_malla: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> List[ElementoBIM]:
        await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        query = select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id)
        if tipo:
            query = query.where(ElementoBIM.tipo == tipo)
        if nivel:
            query = query.where(ElementoBIM.nivel == nivel)
        query = query.order_by(ElementoBIM.tipo).limit(limit).offset(offset)
        result = await self.db.execute(query)
        elementos = list(result.scalars().all())
        if not incluir_malla:
            # La malla puede pesar bastante; solo se manda cuando el
            # frontend explícitamente la va a renderizar.
            for e in elementos:
                e.malla_vertices = None
                e.malla_caras = None
        return elementos

    async def mapear_a_partidas(self, modelo_id: UUID, expediente_id: UUID, mapeos: List[Dict[str, Any]]) -> int:
        """Asocia elementos BIM a partidas de presupuesto ya existentes.

        mapeos: [{"elemento_id": UUID, "partida_id": UUID}, ...]
        """
        await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        count = 0
        for m in mapeos:
            elem = (await self.db.execute(select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.id == m["elemento_id"], ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id))).scalar_one_or_none()
            if elem and elem.modelo_id == modelo_id:
                elem.partida_id = m["partida_id"]
                count += 1
        await self.db.commit()
        return count

    async def crear_presupuesto_desde_bim(
        self,
        *,
        modelo_id: UUID,
        expediente_id: UUID,
        nombre: str = "Presupuesto desde BIM",
        parametros_costeo: ParametrosCosteoSnapshot,
        mapeo_catalogo: Optional[Dict[str, UUID]] = None,
    ) -> Presupuesto:
        """Agrupa los elementos ya cuantificados de un modelo BIM por tipo
        y crea un presupuesto con una partida por tipo.

        `mapeo_catalogo` (5D real): dict opcional {tipo_ifc: catalogo_apu_id}.
        Para los tipos incluidos, la partida se crea con precio real
        (y desglose de insumos si el concepto lo trae) desde
        CatalogoAPU -- vía el mismo camino que
        PresupuestoService.agregar_partida_desde_catalogo, así que no hay
        una segunda lógica de precios por mantener. Para los tipos NO
        incluidos en el mapeo, se conserva el comportamiento original:
        solo cantidades, $0 honesto, pendiente de costeo manual.

        Valida que el modelo pertenezca al expediente antes de operar, y
        que cada catalogo_apu_id del mapeo pertenezca al mismo tenant que
        el expediente (ver nota de seguridad en
        PresupuestoService.agregar_partida_desde_catalogo)."""
        await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        from app.services.presupuesto_service import PresupuestoService
        from app.models.catalogo_apu import CatalogoAPU

        result = await self.db.execute(select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id))
        elementos = list(result.scalars().all())
        if not elementos:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo BIM no tiene elementos cuantificados todavía")

        por_tipo: Dict[str, List[ElementoBIM]] = {}
        for e in elementos:
            por_tipo.setdefault(e.tipo, []).append(e)

        # Resolver el mapeo a catálogo UNA vez, con chequeo de tenant --
        # no dentro del loop por tipo, para no repetir la misma query.
        catalogos_resueltos: Dict[str, CatalogoAPU] = {}
        if mapeo_catalogo:
            expediente = (await self.db.execute(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, *(([ExpedienteObra.tenant_id == self.tenant_id]) if self.tenant_id is not None else [])))).scalar_one_or_none()
            result_apu = await self.db.execute(
                select(CatalogoAPU).where(
                    CatalogoAPU.id.in_(set(mapeo_catalogo.values())),
                    CatalogoAPU.tenant_id == expediente.tenant_id,
                )
            )
            por_id = {c.id: c for c in result_apu.scalars().all()}
            for tipo, catalogo_apu_id in mapeo_catalogo.items():
                concepto = por_id.get(catalogo_apu_id)
                if not concepto:
                    # No existe, o existe bajo otro tenant -- mismo 404,
                    # no se distingue (ver nota en agregar_partida_desde_catalogo).
                    raise MegalodonException(
                        ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                        f"Concepto de catálogo {catalogo_apu_id} (mapeado a '{tipo}') no encontrado",
                    )
                catalogos_resueltos[tipo] = concepto

        partidas_data = []
        orden_tipos = []
        for tipo, elems in por_tipo.items():
            concepto_apu = catalogos_resueltos.get(tipo)

            if concepto_apu is None:
                # Sin mapeo para este tipo: comportamiento original, solo
                # cantidades, $0 honesto (ver nota abajo).
                if tipo in TIPOS_POR_AREA:
                    unidad, cantidad = "m2", sum(float(e.area or 0) for e in elems)
                elif tipo in TIPOS_POR_PIEZA:
                    unidad, cantidad = "pza", float(len(elems))
                else:
                    unidad, cantidad = "m3", sum(float(e.volumen or 0) for e in elems)

                partidas_data.append({
                    "descripcion": f"{tipo} (extraído de BIM, {len(elems)} elementos)",
                    "unidad": unidad,
                    # gt=0 en el resto del sistema; si la cantidad calculada
                    # dio 0 (ej. elementos sin geometría ni Qto) se deja un
                    # mínimo simbólico en vez de tronar, pero NO se inventa un
                    # precio_unitario -- eso se deja pendiente a propósito
                    # (ver nota abajo) para que no se cuele un precio falso a
                    # un presupuesto real.
                    "cantidad": round(cantidad, 4) or 0.0001,
                    # Sin "precio_unitario" ni "conceptos": esto es solo
                    # cuantificación. El motor de costeo lo deja en $0.00
                    # hasta que alguien capture el precio real (tabulador o
                    # APU) -- es más honesto que inventar un valor.
                })
            else:
                # 5D real: la unidad del concepto de catálogo manda -- NO
                # el heurístico TIPOS_POR_AREA/TIPOS_POR_PIEZA (que es
                # solo un default razonable sin mapeo). Si no calza con
                # ninguna cantidad geométrica disponible, se falla claro
                # en vez de adivinar -- p. ej. mandar área cuando el APU
                # real es por m3 daría un importe incorrecto en silencio.
                unidad_apu = (concepto_apu.unidad or "").lower()
                if unidad_apu == "m2":
                    cantidad = sum(float(e.area or 0) for e in elems)
                elif unidad_apu == "m3":
                    cantidad = sum(float(e.volumen or 0) for e in elems)
                elif unidad_apu in ("ml", "m"):
                    cantidad = sum(float(e.longitud or 0) for e in elems)
                elif unidad_apu == "pza":
                    cantidad = float(len(elems))
                else:
                    raise MegalodonException(
                        ErrorCode.BIM_ERROR,
                        f"El concepto de catálogo mapeado a '{tipo}' está en unidad "
                        f"'{concepto_apu.unidad}', que no se puede derivar automáticamente "
                        "de la geometría BIM (solo m2/m3/ml/pza). Usa /mapear-partidas "
                        "para este tipo en vez de mapeo_catalogo.",
                    )

                partida_data: Dict[str, Any] = {
                    "descripcion": f"{tipo} (extraído de BIM, {len(elems)} elementos) — {concepto_apu.descripcion}",
                    "unidad": concepto_apu.unidad,
                    "cantidad": round(cantidad, 4) or 0.0001,
                }
                insumos_desglose = (concepto_apu.desglose or {}).get("insumos") or []
                if insumos_desglose:
                    partida_data["conceptos"] = [{
                        "clave": concepto_apu.clave,
                        "descripcion": concepto_apu.descripcion,
                        "unidad": concepto_apu.unidad,
                        "cantidad": 1.0,
                        "insumos": insumos_desglose,
                    }]
                else:
                    # Tabulador: precio unitario tal cual, sin desglose
                    # (mismo criterio que agregar_partida_desde_catalogo).
                    partida_data["precio_unitario"] = float(concepto_apu.precio_unitario)
                partidas_data.append(partida_data)

            orden_tipos.append(tipo)

        presupuesto_service = PresupuestoService(self.db, self.tenant_id)
        presupuesto = await presupuesto_service.crear_desde_costeo(
            expediente_id=expediente_id,
            nombre=nombre,
            partidas_data=partidas_data,
            parametros_costeo=parametros_costeo,
        )

        partidas_result = await self.db.execute(
            select(Partida).join(Presupuesto, Presupuesto.id == Partida.presupuesto_id).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Partida.presupuesto_id == presupuesto.id, ExpedienteObra.tenant_id == self.tenant_id).order_by(Partida.numero)
        )
        partidas_creadas = list(partidas_result.scalars().all())
        for tipo, partida in zip(orden_tipos, partidas_creadas):
            for e in por_tipo[tipo]:
                e.partida_id = partida.id

        await self.db.commit()
        return presupuesto

    async def asignar_zonas_4d(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        asignaciones: List[Dict[str, Any]],
    ) -> int:
        """Asigna zona_4d a elementos en lote. `asignaciones`:
        [{"elemento_id": UUID, "zona_4d": str}, ...]. Mismo estilo que
        mapear_a_partidas: sin zona_4d asignada, generar_actividades_4d
        cae de vuelta a `nivel`."""
        await self._validar_modelo_en_expediente(modelo_id, expediente_id)

        elemento_ids = [a["elemento_id"] for a in asignaciones]
        result = await self.db.execute(
            select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(
                ElementoBIM.id.in_(elemento_ids),
                ElementoBIM.modelo_id == modelo_id,
                ModeloBIM.tenant_id == self.tenant_id,
            )
        )
        elementos_por_id = {e.id: e for e in result.scalars().all()}

        actualizados = 0
        for a in asignaciones:
            elemento = elementos_por_id.get(a["elemento_id"])
            if elemento is not None:
                elemento.zona_4d = a["zona_4d"]
                actualizados += 1

        await self.db.commit()
        return actualizados

    async def crear_generacion_4d5d(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        dias_por_defecto: float,
        creado_por_id: Optional[UUID] = None,
    ) -> "GeneracionBIM4D5D":
        """Crea el registro de seguimiento PENDIENTE para una corrida de
        generación 4D. El router lo usa para tener un id que devolverle
        al frontend ANTES de encolar la tarea pesada -- la persistencia
        vive aquí, no en el router, igual que el resto del servicio."""
        from app.models.bim import GeneracionBIM4D5D

        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)

        generacion = GeneracionBIM4D5D(
            id=uuid4(),
            modelo_id=modelo_id,
            expediente_id=expediente_id,
            tenant_id=modelo.tenant_id,
            estado=EstadoProceso.PENDIENTE.value,
            dias_por_defecto=dias_por_defecto,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(generacion)
        await self.db.commit()
        await self.db.refresh(generacion)
        return generacion

    async def generar_actividades_4d(
        self,
        *,
        modelo_id: UUID,
        expediente_id: UUID,
        fecha_inicio: datetime,
        dias_por_defecto: float = 5.0,
        nombre_programa: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> "ProgramaObra":
        """Genera un ProgramaObra nuevo con una actividad por (zona,tipo)
        a partir de los elementos ya cuantificados de un modelo BIM, y
        las vincula en `elemento_bim_actividad`.

        Deliberadamente NO genera predecesoras/dependencias: secuenciar
        actividades es un criterio profesional del programador de obra,
        no algo que deba inventarse -- exactamente la misma limitación
        que la tesis de origen documenta sobre el cronograma automático
        de Bexel Manager (duraciones/secuencia genéricas que el
        especialista debe ajustar). `dias_por_defecto` sigue sin ser una
        estimación "inteligente" por tipo de elemento (eso requeriría
        rendimientos de obra reales que no tenemos) -- pero ya no se
        aplica igual a cada actividad sin importar su tamaño: se usa como
        el promedio del programa y se escala por el número de elementos
        de cada grupo relativo a ese promedio, acotado a un rango
        razonable. Sigue siendo una estimación gruesa para que el
        especialista la ajuste, no un sustituto de su criterio.

        Reutiliza ProgramacionService.crear_programa tal cual -- incluida
        su llamada a calcular_cpm al final -- en vez de reimplementar la
        creación de ActividadPrograma o el cálculo de ruta crítica. Este
        método nunca toca app/engines/programacion/cpm.py."""
        from app.models.programacion import ActividadPrograma
        from app.models.bim import ElementoBIMActividad
        from app.services.programacion_service import ProgramacionService

        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)

        result = await self.db.execute(select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id))
        elementos = list(result.scalars().all())
        if not elementos:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo BIM no tiene elementos cuantificados todavía")

        usa_zona_4d = any(e.zona_4d for e in elementos)
        agrupar_por = "zona_4d" if usa_zona_4d else "nivel"

        grupos: Dict[tuple, List[ElementoBIM]] = {}
        for e in elementos:
            zona = (e.zona_4d if usa_zona_4d else e.nivel) or "Sin zona asignada"
            grupos.setdefault((zona, e.tipo), []).append(e)

        # Costo presupuestado por grupo: prorratea el precio unitario ya
        # real de la partida vinculada (si el 5D ya se hizo) sobre la
        # cantidad de ESTE grupo -- no toma partida.importe completo
        # (que es el total del tipo en TODO el modelo, no solo de esta
        # zona), para no sobre-contar entre actividades de zonas distintas.
        partida_ids = {e.partida_id for e in elementos if e.partida_id}
        precios_por_partida: Dict[UUID, tuple] = {}
        if partida_ids:
            result_p = await self.db.execute(select(Partida).join(Presupuesto, Presupuesto.id == Partida.presupuesto_id).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Partida.id.in_(partida_ids), ExpedienteObra.tenant_id == self.tenant_id))
            for p in result_p.scalars().all():
                precios_por_partida[p.id] = (float(p.precio_unitario or 0), (p.unidad or "").lower())

        # `dias_por_defecto` funciona como base configurable. La duración
        # final se ajusta por tamaño del grupo y por la magnitud geométrica
        # real del bloque BIM para que la secuencia 4D no herede siempre el
        # mismo valor.
        num_grupos = len(grupos)
        promedio_elementos_por_grupo = (
            sum(len(elems) for elems in grupos.values()) / num_grupos if num_grupos else 1.0
        )
        pesos_grupo = {
            key: resumir_grupo_bim4d(elems).peso_geometrico_promedio
            for key, elems in grupos.items()
        }
        promedio_peso_por_grupo = (
            sum(pesos_grupo.values()) / num_grupos if num_grupos else 1.0
        )

        actividades_data = []
        orden_grupos = []
        for idx, ((zona, tipo), elems) in enumerate(sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1])), 1):
            costo = 0.0
            for e in elems:
                if e.partida_id and e.partida_id in precios_por_partida:
                    precio_unit, unidad = precios_por_partida[e.partida_id]
                    if unidad == "m2":
                        costo += precio_unit * float(e.area or 0)
                    elif unidad == "m3":
                        costo += precio_unit * float(e.volumen or 0)
                    elif unidad in ("ml", "m"):
                        costo += precio_unit * float(e.longitud or 0)
                    elif unidad == "pza":
                        costo += precio_unit

            peso_grupo = pesos_grupo.get((zona, tipo), 0.0)
            duracion_grupo = estimar_duracion_4d(
                elementos=elems,
                dias_base=dias_por_defecto,
                promedio_cantidad_grupo=promedio_elementos_por_grupo,
                promedio_peso_grupo=promedio_peso_por_grupo,
            )

            identificador = f"BIM4D-{idx:03d}"
            actividades_data.append({
                "id": identificador,
                "nombre": f"{tipo} — {zona}",
                "descripcion": f"Generado automáticamente desde BIM ({len(elems)} elementos)",
                "wbs_codigo": f"{idx:03d}",
                "duracion": duracion_grupo,
                "tipo": "CONSTRUCCION",
                "costo_presupuestado": round(costo, 2),
                "metadatos": {
                    "origen": "bim_4d",
                    "modelo_id": str(modelo_id),
                    "num_elementos": len(elems),
                    "duracion_base_dias": dias_por_defecto,
                    "peso_geometrico_grupo": round(peso_grupo, 4),
                    "promedio_peso_grupo": round(promedio_peso_por_grupo, 4),
                    "factor_duracion_aplicado": round(duracion_grupo / dias_por_defecto if dias_por_defecto else 1.0, 2),
                },
            })
            orden_grupos.append((identificador, elems))

        prog_service = ProgramacionService(self.db, self.tenant_id)
        programa = await prog_service.crear_programa(
            expediente_id=expediente_id,
            nombre=nombre_programa or f"Cronograma 4D — {modelo.nombre}",
            descripcion=f"Generado desde el modelo BIM '{modelo.nombre}' ({agrupar_por} como agrupación).",
            fecha_inicio=fecha_inicio,
            actividades_data=actividades_data,
            creado_por_id=creado_por_id,
            tenant_id=tenant_id,
        )

        result_act = await self.db.execute(
            select(ActividadPrograma).join(ProgramaObra, ProgramaObra.id == ActividadPrograma.programa_id).join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id).where(ActividadPrograma.programa_id == programa.id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        actividades_por_identificador = {a.identificador: a for a in result_act.scalars().all()}

        for identificador, elems in orden_grupos:
            actividad = actividades_por_identificador.get(identificador)
            if actividad is None:
                continue
            for e in elems:
                self.db.add(ElementoBIMActividad(id=uuid4(), elemento_bim_id=e.id, actividad_id=actividad.id))

        await self.db.commit()
        return programa

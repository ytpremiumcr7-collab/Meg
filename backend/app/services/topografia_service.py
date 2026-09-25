# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
TopografiaService - Orquestación real de levantamientos, superficies TIN,
volúmenes de movimiento de tierras, perfiles, curvas de nivel y geodesia.

Antes: 5 carpetas de motor completamente vacías (solo __init__.py con el
header de copyright) y ningún service/router -- "topografía" no existía
como funcionalidad, solo como scaffolding.
"""
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.models.topografia import Levantamiento, PuntoTopografico, SuperficieTIN, CalculoVolumen
from app.models.expediente import ExpedienteObra
from app.engines.topografia.triangulacion import MotorTriangulacion
from app.engines.topografia.volumenes import MotorVolumenes
from app.engines.topografia.geodesia import MotorGeodesia
from app.engines.topografia.levantamientos import MotorPerfiles
from app.engines.topografia.coordenadas import ImportadorPuntos
from app.engines.topografia.importadores.las_importer import ImportadorLAS
from app.core.errors import MegalodonException, ErrorCode
from app.engines.costos.parametros import ParametrosCosteoSnapshot


class TopografiaService:
    """Servicio de topografía: levantamientos, superficies, volúmenes."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        self.db = db
        self.tenant_id = tenant_id
        # These engines are part of the service contract; initialize them
        # here rather than after the return in _require_tenant(), where they
        # were unreachable and therefore never existed at runtime.
        self.motor_triangulacion = MotorTriangulacion()
        self.motor_volumenes = MotorVolumenes()
        self.motor_geodesia = MotorGeodesia()
        self.motor_perfiles = MotorPerfiles()
        self.importador = ImportadorPuntos()

    def _require_tenant(self) -> UUID:
        if self.tenant_id is None:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Contexto tenant requerido para TopografiaService", status_code=403)
        return self.tenant_id

    # ─── Levantamientos y puntos ────────────────────────────────────────

    async def crear_levantamiento(
        self, *, expediente_id: UUID, nombre: str, descripcion: Optional[str] = None,
        crs: str = "EPSG:6362", srid: int = 6362, tipo: str = "POLIGONAL",
        creado_por_id: Optional[UUID] = None,
    ) -> Levantamiento:
        result = await self.db.execute(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self._require_tenant()))
        if not result.scalar_one_or_none():
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")

        count_result = await self.db.execute(select(Levantamiento).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(Levantamiento.expediente_id == expediente_id, ExpedienteObra.tenant_id == self._require_tenant()))
        count = len(count_result.scalars().all()) + 1
        identificador = f"TOPO-{str(expediente_id)[:8]}-{count:03d}"

        levantamiento = Levantamiento(
            id=uuid4(), expediente_id=expediente_id, identificador=identificador,
            nombre=nombre, descripcion=descripcion, crs=crs, srid=srid, tipo=tipo,
            creado_por_id=creado_por_id, actualizado_por_id=creado_por_id,
        )
        self.db.add(levantamiento)
        await self.db.commit()
        await self.db.refresh(levantamiento)
        return levantamiento

    async def listar_levantamientos(self, expediente_id: UUID, limit: int = 50) -> List[Levantamiento]:
        result = await self.db.execute(
            select(Levantamiento).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(Levantamiento.expediente_id == expediente_id, ExpedienteObra.tenant_id == self._require_tenant()).limit(limit)
        )
        return list(result.scalars().all())

    async def listar_superficies(self, levantamiento_id: UUID) -> List[SuperficieTIN]:
        """Lista de referencia (sin la malla, para no pesar el listado --
        usar obtener_superficie() para traer la malla completa)."""
        result = await self.db.execute(
            select(SuperficieTIN).join(Levantamiento, Levantamiento.id == SuperficieTIN.levantamiento_id).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(SuperficieTIN.levantamiento_id == levantamiento_id, ExpedienteObra.tenant_id == self._require_tenant())
        )
        return list(result.scalars().all())

    async def listar_puntos(self, levantamiento_id: UUID, limit: int = 5000) -> List[PuntoTopografico]:
        """Puntos crudos de un levantamiento ya persistidos. Antes no
        existía -- el frontend solo veía los puntos como valor de retorno
        de agregar_puntos()/importar_puntos_csv() en la misma sesión; al
        recargar o reabrir un levantamiento existente, se perdían."""
        tenant_id = self._require_tenant()
        result = await self.db.execute(
            select(PuntoTopografico)
            .join(Levantamiento, Levantamiento.id == PuntoTopografico.levantamiento_id)
            .join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id)
            .where(
                PuntoTopografico.levantamiento_id == levantamiento_id,
                ExpedienteObra.tenant_id == tenant_id,
            )
            .order_by(PuntoTopografico.identificador)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def agregar_puntos(
        self, levantamiento_id: UUID, puntos: List[Dict[str, Any]],
    ) -> List[PuntoTopografico]:
        """puntos: [{"identificador", "x", "y", "z", "etiqueta", "descripcion"}, ...]"""
        levantamiento = await self.db.scalar(select(Levantamiento).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(Levantamiento.id == levantamiento_id, ExpedienteObra.tenant_id == self._require_tenant()))
        if not levantamiento:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Levantamiento {levantamiento_id} no encontrado")

        creados = []
        for p in puntos:
            z = p.get("z")
            punto = PuntoTopografico(
                id=uuid4(),
                levantamiento_id=levantamiento_id,
                identificador=str(p["identificador"]),
                etiqueta=p.get("etiqueta"),
                descripcion=p.get("descripcion"),
                x=p["x"], y=p["y"], z=z,
                precision_xy=p.get("precision_xy", 0.02),
                precision_z=p.get("precision_z"),
                geom=from_shape(Point(p["x"], p["y"], z or 0), srid=levantamiento.srid),
                fuente=p.get("fuente"),
            )
            self.db.add(punto)
            creados.append(punto)

        await self.db.commit()
        for p in creados:
            await self.db.refresh(p)
        return creados

    async def importar_puntos_csv(
        self, levantamiento_id: UUID, contenido_csv: str, formato: str = "penzd",
    ) -> List[PuntoTopografico]:
        """formato: 'penzd' (Punto,Este,Norte,Elevación,Descripción) o
        'generico' (CSV con encabezados)."""
        if formato == "penzd":
            importados = self.importador.desde_csv_penzd(contenido_csv)
        else:
            importados = self.importador.desde_csv_generico(contenido_csv)

        puntos_dict = [
            {"identificador": p.identificador, "x": p.x, "y": p.y, "z": p.z, "descripcion": p.descripcion}
            for p in importados
        ]
        return await self.agregar_puntos(levantamiento_id, puntos_dict)


    async def importar_las(
        self, levantamiento_id: UUID, contenido_las: bytes
    ) -> Dict[str, any]:
        """Importa nube de puntos desde archivo LAS/LAZ.

        Args:
            levantamiento_id: ID del levantamiento destino
            contenido_las: Bytes del archivo LAS

        Returns:
            dict con puntos importados, resumen estadístico, y metadatos
        """
        from pathlib import Path
        import tempfile

        # Guardar temporalmente para leer
        with tempfile.NamedTemporaryFile(suffix=".las", delete=False) as tmp:
            tmp.write(contenido_las)
            tmp_path = Path(tmp.name)

        try:
            importer = ImportadorLAS()
            puntos = importer.desde_archivo(tmp_path)
            resumen = importer.resumen()

            # Convertir a formato de agregar_puntos
            puntos_dict = [
                {
                    "identificador": p.identificador,
                    "x": p.x,
                    "y": p.y,
                    "z": p.z,
                    "descripcion": f"LAS-intensidad:{p.intensidad}-clase:{p.clasificacion}"
                }
                for p in puntos
            ]

            # Agregar al levantamiento
            agregados = await self.agregar_puntos(levantamiento_id, puntos_dict)

            return {
                "levantamiento_id": str(levantamiento_id),
                "puntos_importados": len(agregados),
                "resumen": resumen,
                "formato_detectado": f"LAS {resumen.get('version', 'unknown')}",
                "metadatos": {
                    "intensidad_max": max((p.intensidad for p in puntos), default=0),
                    "clases_detectadas": list(set(p.clasificacion for p in puntos)),
                }
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    # ─── Superficies TIN ─────────────────────────────────────────────

    async def triangular_superficie(
        self, levantamiento_id: UUID, nombre: str, tipo: str = "EXISTENTE",
        creado_por_id: Optional[UUID] = None,
    ) -> SuperficieTIN:
        levantamiento = await self.db.scalar(select(Levantamiento).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(Levantamiento.id == levantamiento_id, ExpedienteObra.tenant_id == self._require_tenant()))
        if not levantamiento:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Levantamiento {levantamiento_id} no encontrado")

        result = await self.db.execute(
            select(PuntoTopografico).where(PuntoTopografico.levantamiento_id == levantamiento_id)
        )
        puntos_db = list(result.scalars().all())
        if len(puntos_db) < 3:
            raise MegalodonException(
                ErrorCode.PUNTOS_INSUFICIENTES,
                f"El levantamiento tiene {len(puntos_db)} puntos; se necesitan al menos 3 para triangular",
            )

        puntos = [(float(p.x), float(p.y), float(p.z or 0)) for p in puntos_db]
        resultado = self.motor_triangulacion.triangular(puntos)

        superficie = SuperficieTIN(
            id=uuid4(),
            expediente_id=levantamiento.expediente_id,
            levantamiento_id=levantamiento_id,
            nombre=nombre,
            tipo=tipo,
            malla_vertices=resultado.malla.vertices,
            malla_caras=resultado.malla.caras,
            area_plan_m2=resultado.estadisticas.area_plan,
            area_superficie_m2=resultado.estadisticas.area_superficie,
            elevacion_min=resultado.estadisticas.elevacion_min,
            elevacion_max=resultado.estadisticas.elevacion_max,
            elevacion_media=resultado.estadisticas.elevacion_media,
            pendiente_media_pct=resultado.estadisticas.pendiente_media_pct,
            num_puntos=resultado.estadisticas.num_puntos,
            num_triangulos=resultado.estadisticas.num_triangulos,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(superficie)
        await self.db.commit()
        await self.db.refresh(superficie)
        return superficie

    async def _puntos_desde_superficie(self, superficie_id: UUID) -> Tuple[SuperficieTIN, List[Tuple[float, float, float]]]:
        superficie = await self.db.scalar(select(SuperficieTIN).join(Levantamiento, Levantamiento.id == SuperficieTIN.levantamiento_id).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(SuperficieTIN.id == superficie_id, ExpedienteObra.tenant_id == self._require_tenant()))
        if not superficie:
            raise MegalodonException(ErrorCode.SUPERFICIE_NO_ENCONTRADA, f"Superficie {superficie_id} no encontrada")
        v = superficie.malla_vertices
        puntos = [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
        return superficie, puntos

    # ─── Volúmenes ───────────────────────────────────────────────────

    async def calcular_volumen(
        self, *,
        superficie_existente_id: UUID,
        superficie_proyecto_id: Optional[UUID] = None,
        elevacion_referencia: Optional[float] = None,
        partida_id: Optional[UUID] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> CalculoVolumen:
        if not superficie_proyecto_id and elevacion_referencia is None:
            raise MegalodonException(
                ErrorCode.TOPOGRAFIA_ERROR,
                "Se necesita superficie_proyecto_id o elevacion_referencia para calcular volumen",
            )

        superficie_existente, puntos_existente = await self._puntos_desde_superficie(superficie_existente_id)

        if superficie_proyecto_id:
            resultado = self.motor_volumenes.calcular_entre_superficies(
                puntos_existente, (await self._puntos_desde_superficie(superficie_proyecto_id))[1],
            )
        else:
            resultado = self.motor_volumenes.calcular_contra_elevacion_referencia(
                puntos_existente, elevacion_referencia,
            )

        calculo = CalculoVolumen(
            id=uuid4(),
            expediente_id=superficie_existente.expediente_id,
            superficie_existente_id=superficie_existente_id,
            superficie_proyecto_id=superficie_proyecto_id,
            elevacion_referencia=elevacion_referencia,
            volumen_corte_m3=resultado.volumen_corte_m3,
            volumen_terraplen_m3=resultado.volumen_terraplen_m3,
            volumen_neto_m3=resultado.volumen_neto_m3,
            area_analizada_m2=resultado.area_analizada_m2,
            partida_id=partida_id,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(calculo)
        await self.db.commit()
        await self.db.refresh(calculo)
        return calculo

    async def generar_partida_movimiento_tierras(
        self, *, calculo_volumen_id: UUID, expediente_id: UUID,
        parametros_costeo: ParametrosCosteoSnapshot,
        nombre: str = "Presupuesto - Movimiento de tierras",
    ):
        """Crea un presupuesto con 2 partidas (corte y terraplén) a partir
        de un cálculo de volumen ya hecho -- mismo patrón que
        BIMService.crear_presupuesto_desde_bim (cantidades reales, sin
        precio unitario todavía)."""
        from app.services.presupuesto_service import PresupuestoService

        calculo = await self.db.scalar(select(CalculoVolumen).join(SuperficieTIN, SuperficieTIN.id == CalculoVolumen.superficie_existente_id).join(Levantamiento, Levantamiento.id == SuperficieTIN.levantamiento_id).join(ExpedienteObra, ExpedienteObra.id == Levantamiento.expediente_id).where(CalculoVolumen.id == calculo_volumen_id, ExpedienteObra.tenant_id == self._require_tenant()))
        if not calculo:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, f"Cálculo de volumen {calculo_volumen_id} no encontrado")

        partidas_data = []
        if float(calculo.volumen_corte_m3) > 0:
            partidas_data.append({
                "descripcion": "Corte / excavación (calculado desde superficie TIN real)",
                "unidad": "m3",
                "cantidad": float(calculo.volumen_corte_m3),
            })
        if float(calculo.volumen_terraplen_m3) > 0:
            partidas_data.append({
                "descripcion": "Terraplén / relleno (calculado desde superficie TIN real)",
                "unidad": "m3",
                "cantidad": float(calculo.volumen_terraplen_m3),
            })
        if not partidas_data:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "El cálculo de volumen no tiene corte ni terraplén (¿superficies idénticas?)")

        presupuesto_service = PresupuestoService(self.db, self._require_tenant())
        presupuesto = await presupuesto_service.crear_desde_costeo(
            expediente_id=expediente_id,
            nombre=nombre,
            partidas_data=partidas_data,
            parametros_costeo=parametros_costeo,
        )

        # Nota: el enlace partida_id -> calculo_volumen (para saber cuál
        # partida del presupuesto corresponde a este cálculo) se deja
        # pendiente hasta que exista un endpoint de "detalle de
        # presupuesto con partidas anidadas" -- misma limitación ya
        # documentada para BIM en CONEXION_BACKEND.md.
        return presupuesto

    # ─── Curvas de nivel y perfiles ──────────────────────────────────

    async def generar_curvas_nivel(self, superficie_id: UUID, intervalo: float = 1.0) -> Dict[float, list]:
        _, puntos = await self._puntos_desde_superficie(superficie_id)
        resultado = self.motor_triangulacion.triangular(puntos)
        return self.motor_triangulacion.generar_curvas_nivel(resultado, intervalo)

    async def generar_perfil(
        self, superficie_id: UUID, eje: List[Tuple[float, float]], intervalo_muestreo: float = 5.0,
    ):
        _, puntos = await self._puntos_desde_superficie(superficie_id)
        resultado = self.motor_triangulacion.triangular(puntos)
        return self.motor_perfiles.generar_perfil(resultado.interpolador, eje, intervalo_muestreo)

    # ─── Geodesia (sin persistencia, cálculo directo) ────────────────

    def transformar_coordenadas(self, puntos: List[Tuple[float, float]], crs_origen: str, crs_destino: str):
        return self.motor_geodesia.transformar_coordenadas(puntos, crs_origen, crs_destino)

    def cierre_poligonal(self, vertices: List[Tuple[float, float]]):
        return self.motor_geodesia.cierre_poligonal(vertices)

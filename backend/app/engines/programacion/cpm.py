# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de Programación de Obra - CPM (Critical Path Method)
Implementa: CPM determinista, PERT probabilístico, EVM (Earned Value Management),
Curva S, diagrama de Gantt, y análisis de holguras.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from decimal import Decimal

import numpy as np

from app.core.errors import MegalodonException, ErrorCode
from app.core.calendar import CalendarioLaboral


class TipoDependencia(str, Enum):
    FIN_INICIO = "FS"   # Finish-to-Start (por defecto)
    INICIO_INICIO = "SS"  # Start-to-Start
    FIN_FIN = "FF"      # Finish-to-Finish
    INICIO_FIN = "SF"   # Start-to-Finish


class TipoActividad(str, Enum):
    CONSTRUCCION = "CONSTRUCCION"
    SUMINISTRO = "SUMINISTRO"
    INSTALACION = "INSTALACION"
    PRUEBA = "PRUEBA"
    DOCUMENTACION = "DOCUMENTACION"
    HITO = "HITO"


@dataclass
class Actividad:
    """Actividad de la programación de obra."""
    id: str
    nombre: str
    descripcion: str = ""
    duracion: float = 0.0  # Días
    duracion_optimista: Optional[float] = None  # Para PERT
    duracion_probable: Optional[float] = None   # Para PERT
    duracion_pesimista: Optional[float] = None  # Para PERT
    tipo: TipoActividad = TipoActividad.CONSTRUCCION
    predecesoras: List[str] = field(default_factory=list)
    sucesoras: List[str] = field(default_factory=list)
    dependencias: Dict[str, TipoDependencia] = field(default_factory=dict)

    # Costos
    costo_presupuestado: float = 0.0
    costo_real: float = 0.0

    # Avance
    porcentaje_avance: float = 0.0  # 0-100

    # Fechas (calculadas por CPM)
    inicio_temprano: Optional[datetime] = None
    fin_temprano: Optional[datetime] = None
    inicio_tardio: Optional[datetime] = None
    fin_tardio: Optional[datetime] = None

    # Holgura
    holgura_total: float = 0.0
    holgura_libre: float = 0.0

    # Ruta crítica
    en_ruta_critica: bool = False

    # WBS
    wbs_nivel: int = 0
    wbs_codigo: str = ""

    # Metadatos
    metadatos: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RutaCritica:
    """Resultado del análisis de ruta crítica."""
    actividades_criticas: List[Actividad]
    duracion_total: float
    fecha_inicio: datetime
    fecha_fin: datetime
    holgura_total_proyecto: float


@dataclass
class ResultadoCPM:
    """Resultado completo del análisis CPM."""
    actividades: Dict[str, Actividad]
    ruta_critica: RutaCritica
    duracion_total: float
    gantt_data: List[Dict[str, Any]]
    curva_s: List[Dict[str, Any]]
    diagrama_red: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duracion_total": self.duracion_total,
            "ruta_critica": {
                "actividades": [a.id for a in self.ruta_critica.actividades_criticas],
                "duracion": self.ruta_critica.duracion_total,
                "fecha_inicio": self.ruta_critica.fecha_inicio.isoformat() if self.ruta_critica.fecha_inicio else None,
                "fecha_fin": self.ruta_critica.fecha_fin.isoformat() if self.ruta_critica.fecha_fin else None,
            },
            "actividades": {
                id: {
                    "nombre": a.nombre,
                    "duracion": a.duracion,
                    "inicio_temprano": a.inicio_temprano.isoformat() if a.inicio_temprano else None,
                    "fin_temprano": a.fin_temprano.isoformat() if a.fin_temprano else None,
                    "inicio_tardio": a.inicio_tardio.isoformat() if a.inicio_tardio else None,
                    "fin_tardio": a.fin_tardio.isoformat() if a.fin_tardio else None,
                    "holgura_total": a.holgura_total,
                    "holgura_libre": a.holgura_libre,
                    "en_ruta_critica": a.en_ruta_critica,
                    "avance": a.porcentaje_avance,
                }
                for id, a in self.actividades.items()
            },
            "gantt": self.gantt_data,
            "curva_s": self.curva_s,
        }


@dataclass
class ResultadoPERT:
    """Resultado del análisis PERT probabilístico."""
    duracion_esperada: float
    varianza_total: float
    desviacion_estandar: float
    probabilidad_terminar_a_tiempo: float
    fecha_probable_terminacion: datetime
    percentiles: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duracion_esperada": self.duracion_esperada,
            "varianza_total": self.varianza_total,
            "desviacion_estandar": self.desviacion_estandar,
            "probabilidad_terminar_a_tiempo": self.probabilidad_terminar_a_tiempo,
            "fecha_probable_terminacion": self.fecha_probable_terminacion.isoformat() if self.fecha_probable_terminacion else None,
            "percentiles": self.percentiles,
        }


@dataclass
class ResultadoEVM:
    """Resultado del análisis Earned Value Management."""
    pv: float  # Planned Value
    ev: float  # Earned Value
    ac: float  # Actual Cost
    sv: float  # Schedule Variance
    cv: float  # Cost Variance
    spi: float  # Schedule Performance Index
    cpi: float  # Cost Performance Index
    eac: float  # Estimate at Completion
    etc: float  # Estimate to Complete
    vac: float  # Variance at Completion
    tcpi: float  # To-Complete Performance Index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pv": self.pv,
            "ev": self.ev,
            "ac": self.ac,
            "sv": self.sv,
            "cv": self.cv,
            "spi": self.spi,
            "cpi": self.cpi,
            "eac": self.eac,
            "etc": self.etc,
            "vac": self.vac,
            "tcpi": self.tcpi,
            "interpretacion": {
                "cronograma": "ADELANTADO" if self.spi > 1.05 else "ATRASADO" if self.spi < 0.95 else "A_TIEMPO",
                "costo": "BAJO_PRESUPUESTO" if self.cpi > 1.05 else "SOBRE_PRESUPUESTO" if self.cpi < 0.95 else "A_PRESUPUESTO",
            }
        }


class MotorCPM:
    """
    Motor de CPM (Critical Path Method) para programación de obra.

    Implementa:
    - CPM determinista (forward/backward pass)
    - PERT probabilístico (tres estimaciones)
    - EVM (Earned Value Management)
    - Curva S de avance
    - Diagrama de Gantt
    """

    def __init__(self, calendario: Optional[CalendarioLaboral] = None):
        self.calendario = calendario or CalendarioLaboral()
        self.actividades: Dict[str, Actividad] = {}

    def agregar_actividad(self, actividad: Actividad) -> None:
        """Agrega una actividad al programa."""
        self.actividades[actividad.id] = actividad

    def _detectar_ciclos(self) -> Optional[List[str]]:
        """
        Detecta ciclos en el grafo de predecesoras (DFS con pila de
        recursión, coloreado blanco/gris/negro clásico).

        BUG ORIGINAL (referenciado desde programacion_service.py, nunca
        cerrado ahí porque arreglarlo en el service sin arreglar el
        motor daría una falsa sensación de seguridad -- solo detectaría
        auto-referencias directas, no ciclos indirectos A->B->C->A):
        _forward_pass tiene un `max_iter` como cinturón de seguridad,
        pero si hay un ciclo real, simplemente deja de iterar sin avisar
        -- las actividades atrapadas en el ciclo se quedan con
        inicio_temprano/fin_temprano en None, silenciosamente, y el
        resto del cálculo (duración total, ruta crítica, Gantt) sigue
        adelante ignorándolas como si no existieran.

        AHORA: se corre esto ANTES del forward pass. Si hay ciclo, se
        aborta con una excepción clara que incluye el ciclo completo
        (lista de ids en orden), en vez de dejar el resultado incompleto
        y sin explicación.

        Returns:
            La lista de ids del ciclo encontrado (en orden, cerrando en
            el mismo id donde empieza), o None si el grafo es acíclico.
        """
        # Iterativo a propósito (no recursión por actividad): un
        # programa de obra real puede encadenar miles de actividades, y
        # una versión recursiva reventaría el límite de recursión de
        # Python en un proyecto grande en vez de reportar el ciclo.
        BLANCO, GRIS, NEGRO = 0, 1, 2
        estado: Dict[str, int] = {aid: BLANCO for aid in self.actividades}
        pila_camino: List[str] = []  # ids en el camino actual (todos GRIS)

        for inicio in self.actividades:
            if estado[inicio] != BLANCO:
                continue

            # Cada elemento: (id, iterador pendiente de sus predecesoras)
            marco = [(inicio, iter(self.actividades[inicio].predecesoras))]
            estado[inicio] = GRIS
            pila_camino.append(inicio)

            while marco:
                aid, it_predecesoras = marco[-1]
                avanzo = False

                for pred_id in it_predecesoras:
                    if pred_id not in self.actividades:
                        # Predecesor inexistente: dato roto distinto a
                        # un ciclo -- el forward pass ya lo tolera
                        # (pred_fechas simplemente no lo incluye).
                        continue
                    if estado[pred_id] == GRIS:
                        idx = pila_camino.index(pred_id)
                        return pila_camino[idx:] + [pred_id]
                    if estado[pred_id] == BLANCO:
                        estado[pred_id] = GRIS
                        pila_camino.append(pred_id)
                        marco.append((pred_id, iter(self.actividades[pred_id].predecesoras)))
                        avanzo = True
                        break

                if not avanzo:
                    marco.pop()
                    pila_camino.pop()
                    estado[aid] = NEGRO

        return None

    def calcular_cpm(
        self,
        fecha_inicio: datetime,
        usar_calendario: bool = True,
    ) -> ResultadoCPM:
        """
        Calcula CPM completo: forward pass, backward pass, ruta crítica.
        """
        if not self.actividades:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                "No hay actividades para calcular CPM",
            )

        missing = sorted({
            pred
            for act in self.actividades.values()
            for pred in act.predecesoras
            if pred not in self.actividades
        })
        if missing:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                "El programa contiene predecesoras inexistentes.",
                details={"predecesoras_inexistentes": missing},
            )

        ciclo = self._detectar_ciclos()
        if ciclo:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                "El programa tiene una dependencia circular entre "
                f"actividades: {' -> '.join(ciclo)}. Corrige las "
                "predecesoras antes de calcular CPM -- con un ciclo, "
                "el forward pass no puede resolver fechas para las "
                "actividades atrapadas en él.",
                details={"ciclo": ciclo},
            )

        # Forward pass: calcular inicio/fin temprano
        self._forward_pass(fecha_inicio, usar_calendario)

        # Backward pass: calcular inicio/fin tardío
        fecha_fin_proyecto = max(
            (a.fin_temprano for a in self.actividades.values() if a.fin_temprano),
            default=fecha_inicio,
        )
        self._backward_pass(fecha_fin_proyecto, usar_calendario)

        # Calcular holguras y ruta crítica
        self._calcular_holguras()

        # Generar datos para visualización
        gantt = self._generar_gantt()
        curva_s = self._generar_curva_s()
        diagrama_red = self._generar_diagrama_red()

        # Identificar ruta crítica
        actividades_criticas = [
            a for a in self.actividades.values() if a.en_ruta_critica
        ]
        actividades_criticas.sort(key=lambda a: a.inicio_temprano or datetime.min)

        ruta_critica = RutaCritica(
            actividades_criticas=actividades_criticas,
            duracion_total=sum(a.duracion for a in actividades_criticas),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin_proyecto,
            holgura_total_proyecto=0.0,
        )

        duracion_total = max(
            (a.fin_temprano - a.inicio_temprano).days
            for a in self.actividades.values()
            if a.fin_temprano and a.inicio_temprano
        ) if any(a.fin_temprano for a in self.actividades.values()) else 0

        return ResultadoCPM(
            actividades=dict(self.actividades),
            ruta_critica=ruta_critica,
            duracion_total=duracion_total,
            gantt_data=gantt,
            curva_s=curva_s,
            diagrama_red=diagrama_red,
        )

    def _forward_pass(self, fecha_inicio: datetime, usar_calendario: bool) -> None:
        """Forward pass: calcula inicio y fin temprano."""
        # Inicializar actividades sin predecesoras
        for act in self.actividades.values():
            if not act.predecesoras:
                act.inicio_temprano = fecha_inicio
                if usar_calendario:
                    act.fin_temprano = self.calendario.sumar_dias_habiles(
                        fecha_inicio, int(act.duracion)
                    )
                else:
                    act.fin_temprano = fecha_inicio + timedelta(days=act.duracion)

        # Iterar hasta que todas tengan fechas
        cambios = True
        max_iter = len(self.actividades) * 2
        iter_count = 0

        while cambios and iter_count < max_iter:
            cambios = False
            iter_count += 1

            for act in self.actividades.values():
                if act.inicio_temprano is not None:
                    continue

                # Verificar que todas las predecesoras tengan fin temprano
                pred_fechas = []
                for pred_id in act.predecesoras:
                    pred = self.actividades.get(pred_id)
                    if pred and pred.fin_temprano:
                        pred_fechas.append(pred.fin_temprano)

                if len(pred_fechas) == len(act.predecesoras) and pred_fechas:
                    inicio = max(pred_fechas)
                    act.inicio_temprano = inicio

                    if usar_calendario:
                        act.fin_temprano = self.calendario.sumar_dias_habiles(
                            inicio, int(act.duracion)
                        )
                    else:
                        act.fin_temprano = inicio + timedelta(days=act.duracion)

                    cambios = True

    def _backward_pass(self, fecha_fin: datetime, usar_calendario: bool) -> None:
        """Backward pass: calcula inicio y fin tardío."""
        # Inicializar actividades sin sucesoras
        for act in self.actividades.values():
            if not act.sucesoras:
                act.fin_tardio = fecha_fin
                if usar_calendario:
                    act.inicio_tardio = self.calendario.restar_dias_habiles(
                        fecha_fin, int(act.duracion)
                    )
                else:
                    act.inicio_tardio = fecha_fin - timedelta(days=act.duracion)

        # Iterar hacia atrás
        cambios = True
        max_iter = len(self.actividades) * 2
        iter_count = 0

        while cambios and iter_count < max_iter:
            cambios = False
            iter_count += 1

            for act in self.actividades.values():
                if act.fin_tardio is not None:
                    continue

                # Verificar que todas las sucesoras tengan inicio tardío
                succ_fechas = []
                for succ_id in act.sucesoras:
                    succ = self.actividades.get(succ_id)
                    if succ and succ.inicio_tardio:
                        succ_fechas.append(succ.inicio_tardio)

                if len(succ_fechas) == len(act.sucesoras) and succ_fechas:
                    fin = min(succ_fechas)
                    act.fin_tardio = fin

                    if usar_calendario:
                        act.inicio_tardio = self.calendario.restar_dias_habiles(
                            fin, int(act.duracion)
                        )
                    else:
                        act.inicio_tardio = fin - timedelta(days=act.duracion)

                    cambios = True

    def _calcular_holguras(self) -> None:
        """Calcula holguras totales y libres, identifica ruta crítica."""
        for act in self.actividades.values():
            if act.inicio_temprano and act.inicio_tardio:
                act.holgura_total = (
                    act.inicio_tardio - act.inicio_temprano
                ).total_seconds() / 86400

            # Holgura libre: diferencia entre inicio temprano de sucesora y fin temprano
            if act.sucesoras:
                succ_inicios = []
                for succ_id in act.sucesoras:
                    succ = self.actividades.get(succ_id)
                    if succ and succ.inicio_temprano:
                        succ_inicios.append(succ.inicio_temprano)

                if succ_inicios and act.fin_temprano:
                    min_succ_inicio = min(succ_inicios)
                    act.holgura_libre = (
                        min_succ_inicio - act.fin_temprano
                    ).total_seconds() / 86400
            else:
                act.holgura_libre = act.holgura_total

            # Ruta crítica: holgura total = 0 (o muy cercana)
            act.en_ruta_critica = abs(act.holgura_total) < 0.001

    def calcular_pert(
        self,
        fecha_inicio: datetime,
        fecha_objetivo: Optional[datetime] = None,
    ) -> ResultadoPERT:
        """
        Calcula PERT (Program Evaluation and Review Technique).
        Usa tres estimaciones de duración.
        """
        duraciones_esperadas = []
        varianzas = []

        for act in self.actividades.values():
            if act.duracion_optimista and act.duracion_probable and act.duracion_pesimista:
                # Fórmula PERT: (o + 4m + p) / 6
                esperada = (
                    act.duracion_optimista +
                    4 * act.duracion_probable +
                    act.duracion_pesimista
                ) / 6

                # Varianza: ((p - o) / 6)²
                varianza = ((act.duracion_pesimista - act.duracion_optimista) / 6) ** 2

                duraciones_esperadas.append(esperada)
                varianzas.append(varianza)

                # Actualizar duración para CPM
                act.duracion = esperada
            else:
                duraciones_esperadas.append(act.duracion)
                varianzas.append(0)

        # Recalcular CPM con duraciones esperadas
        resultado_cpm = self.calcular_cpm(fecha_inicio)
        duracion_esperada = resultado_cpm.duracion_total

        # Varianza total de la ruta crítica
        varianza_total = sum(
            varianzas[i]
            for i, act in enumerate(self.actividades.values())
            if act.en_ruta_critica
        )

        desviacion = np.sqrt(varianza_total)

        # Probabilidad de terminar a tiempo
        probabilidad = 0.5
        if fecha_objetivo and duracion_esperada > 0:
            dias_objetivo = (fecha_objetivo - fecha_inicio).days
            z = (dias_objetivo - duracion_esperada) / desviacion if desviacion > 0 else 0
            from scipy import stats
            probabilidad = stats.norm.cdf(z)

        # Percentiles
        percentiles = {}
        if desviacion > 0:
            for p in [10, 25, 50, 75, 90, 95]:
                dias = duracion_esperada + stats.norm.ppf(p/100) * desviacion
                percentiles[f"p{p}"] = dias

        return ResultadoPERT(
            duracion_esperada=duracion_esperada,
            varianza_total=varianza_total,
            desviacion_estandar=desviacion,
            probabilidad_terminar_a_tiempo=probabilidad,
            fecha_probable_terminacion=fecha_inicio + timedelta(days=int(duracion_esperada)),
            percentiles=percentiles,
        )

    def calcular_evm(self, fecha_corte: datetime) -> ResultadoEVM:
        """
        Calcula Earned Value Management (EVM) al fecha de corte.
        """
        pv = 0.0  # Planned Value
        ev = 0.0  # Earned Value
        ac = 0.0  # Actual Cost

        for act in self.actividades.values():
            if act.inicio_temprano and act.fin_temprano:
                # PV: valor planeado según cronograma
                if act.fin_temprano <= fecha_corte:
                    pv += act.costo_presupuestado
                elif act.inicio_temprano <= fecha_corte:
                    # Proporcional al tiempo transcurrido
                    dias_total = (act.fin_temprano - act.inicio_temprano).days
                    dias_transcurridos = (fecha_corte - act.inicio_temprano).days
                    pv += act.costo_presupuestado * (dias_transcurridos / dias_total)

                # EV: valor ganado según avance real
                ev += act.costo_presupuestado * (act.porcentaje_avance / 100)

                # AC: costo real
                ac += act.costo_real

        # Métricas EVM
        sv = ev - pv
        cv = ev - ac
        spi = ev / pv if pv != 0 else 0
        cpi = ev / ac if ac != 0 else 0

        # Proyecciones
        bac = sum(a.costo_presupuestado for a in self.actividades.values())  # Budget at Completion
        eac = bac / cpi if cpi != 0 else bac
        etc = eac - ac
        vac = bac - eac
        tcpi = (bac - ev) / (bac - ac) if (bac - ac) != 0 else 0

        return ResultadoEVM(
            pv=pv, ev=ev, ac=ac,
            sv=sv, cv=cv,
            spi=spi, cpi=cpi,
            eac=eac, etc=etc,
            vac=vac, tcpi=tcpi,
        )

    def _generar_gantt(self) -> List[Dict[str, Any]]:
        """Genera datos para diagrama de Gantt."""
        gantt = []
        for act in self.actividades.values():
            if act.inicio_temprano and act.fin_temprano:
                gantt.append({
                    "id": act.id,
                    "nombre": act.nombre,
                    "inicio": act.inicio_temprano.isoformat(),
                    "fin": act.fin_temprano.isoformat(),
                    "duracion": act.duracion,
                    "avance": act.porcentaje_avance,
                    "critica": act.en_ruta_critica,
                    "holgura": act.holgura_total,
                    "predecesoras": act.predecesoras,
                    "tipo": act.tipo.value,
                    "wbs": act.wbs_codigo,
                })
        return gantt

    def _generar_curva_s(self, puntos: int = 50) -> List[Dict[str, Any]]:
        """Genera curva S de avance acumulado."""
        if not self.actividades:
            return []

        # Encontrar rango de fechas
        fechas_inicio = [a.inicio_temprano for a in self.actividades.values() if a.inicio_temprano]
        fechas_fin = [a.fin_temprano for a in self.actividades.values() if a.fin_temprano]

        if not fechas_inicio or not fechas_fin:
            return []

        fecha_min = min(fechas_inicio)
        fecha_max = max(fechas_fin)
        duracion_total = (fecha_max - fecha_min).days

        if duracion_total <= 0:
            return []

        curva = []
        for i in range(puntos + 1):
            fecha = fecha_min + timedelta(days=(duracion_total * i / puntos))

            # Calcular avance planeado acumulado
            avance_plan = 0.0
            avance_real = 0.0
            costo_plan = 0.0
            costo_real = 0.0

            for act in self.actividades.values():
                if not act.inicio_temprano or not act.fin_temprano:
                    continue

                dias_act = (act.fin_temprano - act.inicio_temprano).days
                if dias_act <= 0:
                    continue

                # Avance planeado
                if fecha >= act.fin_temprano:
                    avance_plan += 1
                    costo_plan += act.costo_presupuestado
                elif fecha > act.inicio_temprano:
                    prop = (fecha - act.inicio_temprano).days / dias_act
                    avance_plan += prop
                    costo_plan += act.costo_presupuestado * prop

                # Avance real
                avance_real += act.porcentaje_avance / 100
                costo_real += act.costo_real

            total_act = len(self.actividades)
            curva.append({
                "fecha": fecha.isoformat(),
                "avance_plan_pct": round((avance_plan / total_act) * 100, 2) if total_act > 0 else 0,
                "avance_real_pct": round((avance_real / total_act) * 100, 2) if total_act > 0 else 0,
                "costo_plan": round(costo_plan, 2),
                "costo_real": round(costo_real, 2),
                "dias_transcurridos": (fecha - fecha_min).days,
            })

        return curva

    def _generar_diagrama_red(self) -> Dict[str, Any]:
        """Genera datos para diagrama de red de actividades (ADM)."""
        nodos = []
        aristas = []

        for act in self.actividades.values():
            nodos.append({
                "id": act.id,
                "nombre": act.nombre,
                "duracion": act.duracion,
                "critica": act.en_ruta_critica,
                "holgura": act.holgura_total,
            })

            for pred_id in act.predecesoras:
                aristas.append({
                    "desde": pred_id,
                    "hasta": act.id,
                    "tipo": act.dependencias.get(pred_id, TipoDependencia.FIN_INICIO).value,
                })

        return {"nodos": nodos, "aristas": aristas}

    def actualizar_avance(
        self,
        actividad_id: str,
        porcentaje: float,
        costo_real: Optional[float] = None,
    ) -> Actividad:
        """Actualiza el avance de una actividad."""
        if actividad_id not in self.actividades:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Actividad {actividad_id} no encontrada",
            )

        act = self.actividades[actividad_id]
        act.porcentaje_avance = max(0, min(100, porcentaje))

        if costo_real is not None:
            act.costo_real = costo_real

        return act


    def exportar_ms_project(self) -> bytes:
        """Exporta programa a formato XML de Microsoft Project (.xml).

        Genera XML válido según el esquema MSPDI (Microsoft Project Data Interchange).
        Compatible con MS Project 2007+ y Project Online.
        """
        import xml.etree.ElementTree as ET
        from datetime import datetime

        ns = {
            '': 'http://schemas.microsoft.com/project',
        }

        # Register namespace to avoid ns0: prefix
        ET.register_namespace('', 'http://schemas.microsoft.com/project')

        root = ET.Element('Project', xmlns='http://schemas.microsoft.com/project')

        # Project info
        ET.SubElement(root, 'Name').text = self.nombre or "Programa de Obra"
        ET.SubElement(root, 'Subject').text = "Programación CPM"
        ET.SubElement(root, 'CreationDate').text = datetime.utcnow().isoformat()
        ET.SubElement(root, 'LastSaved').text = datetime.utcnow().isoformat()
        ET.SubElement(root, 'ScheduleFromStart').text = "1"
        ET.SubElement(root, 'StartDate').text = self.fecha_inicio.isoformat() if self.fecha_inicio else datetime.utcnow().isoformat()
        ET.SubElement(root, 'CurrencySymbol').text = "$"
        ET.SubElement(root, 'CurrencyCode').text = "MXN"
        ET.SubElement(root, 'CurrencyDigits').text = "2"

        # Tasks
        tasks = ET.SubElement(root, 'Tasks')

        # Task 0 = project summary
        t0 = ET.SubElement(tasks, 'Task')
        ET.SubElement(t0, 'UID').text = "0"
        ET.SubElement(t0, 'ID').text = "0"
        ET.SubElement(t0, 'Name').text = self.nombre or "Programa de Obra"
        ET.SubElement(t0, 'Type').text = "1"
        ET.SubElement(t0, 'IsNull').text = "0"
        ET.SubElement(t0, 'WBS').text = "0"
        ET.SubElement(t0, 'OutlineNumber').text = "0"
        ET.SubElement(t0, 'OutlineLevel').text = "0"
        ET.SubElement(t0, 'Priority').text = "500"
        ET.SubElement(t0, 'Start').text = self.fecha_inicio.isoformat() if self.fecha_inicio else datetime.utcnow().isoformat()
        ET.SubElement(t0, 'Finish').text = self.fecha_fin.isoformat() if self.fecha_fin else datetime.utcnow().isoformat()
        ET.SubElement(t0, 'Duration').text = f"PT{int(self.duracion_total or 0)}H0M0S"
        ET.SubElement(t0, 'DurationFormat').text = "7"
        ET.SubElement(t0, 'PercentComplete').text = "0"
        ET.SubElement(t0, 'PercentWorkComplete').text = "0"
        ET.SubElement(t0, 'FixedCostAccrual').text = "2"
        ET.SubElement(t0, 'ConstraintType').text = "0"
        ET.SubElement(t0, 'CalendarUID').text = "-1"

        # Real tasks
        for i, act in enumerate(self.actividades, 1):
            t = ET.SubElement(tasks, 'Task')
            ET.SubElement(t, 'UID').text = str(i)
            ET.SubElement(t, 'ID').text = str(i)
            ET.SubElement(t, 'Name').text = act.nombre or f"Actividad {i}"
            ET.SubElement(t, 'Type').text = "1"  # Fixed Units
            ET.SubElement(t, 'IsNull').text = "0"
            ET.SubElement(t, 'WBS').text = act.wbs or str(i)
            ET.SubElement(t, 'OutlineNumber').text = act.wbs or str(i)
            ET.SubElement(t, 'OutlineLevel').text = str(len(act.wbs.split('.')) if act.wbs else 1)
            ET.SubElement(t, 'Priority').text = "500"

            # Dates
            if act.early_start:
                ET.SubElement(t, 'Start').text = act.early_start.isoformat()
                ET.SubElement(t, 'EarlyStart').text = act.early_start.isoformat()
            if act.early_finish:
                ET.SubElement(t, 'Finish').text = act.early_finish.isoformat()
                ET.SubElement(t, 'EarlyFinish').text = act.early_finish.isoformat()
            if act.late_start:
                ET.SubElement(t, 'LateStart').text = act.late_start.isoformat()
            if act.late_finish:
                ET.SubElement(t, 'LateFinish').text = act.late_finish.isoformat()

            # Duration in hours (MS Project uses minutes in XML but displays according to format)
            dur_horas = int(act.duracion or 0)
            ET.SubElement(t, 'Duration').text = f"PT{dur_horas}H0M0S"
            ET.SubElement(t, 'DurationFormat').text = "7"  # Hours
            ET.SubElement(t, 'Work').text = f"PT{dur_horas}H0M0S"
            ET.SubElement(t, 'WorkFormat').text = "7"

            # Cost
            if act.costo is not None:
                ET.SubElement(t, 'Cost').text = str(float(act.costo))
                ET.SubElement(t, 'FixedCost').text = str(float(act.costo))

            # Percent complete
            pct = int(act.avance or 0)
            ET.SubElement(t, 'PercentComplete').text = str(pct)
            ET.SubElement(t, 'PercentWorkComplete').text = str(pct)

            # Critical path
            ET.SubElement(t, 'Critical').text = "1" if act.es_critica else "0"
            ET.SubElement(t, 'Milestone').text = "1" if act.duracion == 0 else "0"

            # Float
            if act.holgura_total is not None:
                ET.SubElement(t, 'TotalSlack').text = str(int(act.holgura_total))
            if act.holgura_libre is not None:
                ET.SubElement(t, 'FreeSlack').text = str(int(act.holgura_libre))

            # Predecessors
            if act.predecesoras:
                preds = ET.SubElement(t, 'PredecessorLink')
                for pred_id in act.predecesoras:
                    try:
                        pred_idx = next(j for j, a in enumerate(self.actividades, 1) if a.id == pred_id)
                        pl = ET.SubElement(preds, 'PredecessorLink')
                        ET.SubElement(pl, 'PredecessorUID').text = str(pred_idx)
                        ET.SubElement(pl, 'Type').text = "1"  # Finish-to-Start
                        ET.SubElement(pl, 'LinkLag').text = "0"
                        ET.SubElement(pl, 'LagFormat').text = "7"
                    except StopIteration:
                        logger.error(
                            "cpm_predecesora_no_encontrada_xml",
                            actividad_id=act.id,
                            predecesora_id=pred_id,
                            export_format="ms_project_xml",
                            note="Grafo con predecesora fantasma. Exportacion XML incompleta.",
                        )

            ET.SubElement(t, 'FixedCostAccrual').text = "2"
            ET.SubElement(t, 'ConstraintType').text = "0"
            ET.SubElement(t, 'CalendarUID').text = "-1"

        # Resources (empty but required for valid schema)
        ET.SubElement(root, 'Resources')

        # Assignments (empty but required)
        ET.SubElement(root, 'Assignments')

        tree = ET.ElementTree(root)
        import io
        buf = io.BytesIO()
        tree.write(buf, encoding='UTF-8', xml_declaration=True)
        return buf.getvalue()

    def exportar_primavera(self) -> bytes:
        """Exporta programa a formato XER de Primavera P6.

        Genera archivo XER válido con tablas PROJECT, WBS, TASK, TASKPRED,
        TASKRSRC, CALENDAR, UDFTYPE, UDFVALUE.
        """
        lines = []

        def emit_table(name, fields, rows):
            lines.append(f"%T\t{name}")
            lines.append(f"%F\t{'\t'.join(fields)}")
            for row in rows:
                escaped = [str(v).replace("\t", " ").replace("\n", " ").replace("\r", "") for v in row]
                lines.append(f"%R\t{'\t'.join(escaped)}")

        # PROJECT
        emit_table("PROJECT", [
            "proj_id", "proj_short_name", "proj_name", "plan_start_date",
            "plan_end_date", "last_recalc_date", "sched_type", "proj_url"
        ], [[
            "1", self.nombre or "PROY1", self.nombre or "Programa de Obra",
            (self.fecha_inicio or __import__('datetime').datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
            (self.fecha_fin or __import__('datetime').datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
            __import__('datetime').datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "CPM", ""
        ]])

        # WBS
        wbs_rows = [["1", "1", "0", self.nombre or "Programa", "0", "1"]]
        wbs_map = {"0": "1"}

        for i, act in enumerate(self.actividades, 1):
            parent = act.wbs.rsplit('.', 1)[0] if act.wbs and '.' in act.wbs else "0"
            parent_id = wbs_map.get(parent, "1")
            wbs_id = str(i + 1)
            wbs_map[act.wbs or str(i)] = wbs_id
            wbs_rows.append([
                wbs_id, "1", parent_id, act.nombre or f"Act {i}",
                str(len(act.wbs.split('.')) if act.wbs else 1), str(i)
            ])

        emit_table("WBS", ["wbs_id", "proj_id", "parent_wbs_id", "wbs_name", "wbs_level", "seq_num"], wbs_rows)

        # CALENDAR
        emit_table("CALENDAR", ["clndr_id", "clndr_name", "day_hr_cnt", "week_hr_cnt", "month_hr_cnt", "year_hr_cnt"], [
            ["1", "Standard", "8", "40", "172", "2000"]
        ])

        # TASK
        task_rows = []
        for i, act in enumerate(self.actividades, 1):
            wbs_id = wbs_map.get(act.wbs or str(i), "1")
            task_rows.append([
                str(i), "1", wbs_id, "1", act.nombre or f"Act {i}",
                (act.early_start or __import__('datetime').datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
                (act.early_finish or __import__('datetime').datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
                str(int(act.duracion or 0)),
                str(int(act.duracion or 0)),
                "1" if act.es_critica else "0",
                str(int(act.holgura_total or 0)),
                str(int(act.avance or 0)),
                str(float(act.costo or 0)),
                "", "", ""
            ])

        emit_table("TASK", [
            "task_id", "proj_id", "wbs_id", "clndr_id", "task_name",
            "act_start_date", "act_end_date", "target_drtn_hr_cnt",
            "total_float_hr_cnt", "cstr_type", "free_float_hr_cnt",
            "complete_pct_type", "task_type", "status_code"
        ], task_rows)

        # TASKPRED (predecessors)
        pred_rows = []
        for i, act in enumerate(self.actividades, 1):
            if act.predecesoras:
                for pred_id in act.predecesoras:
                    try:
                        pred_idx = next(j for j, a in enumerate(self.actividades, 1) if a.id == pred_id)
                        pred_rows.append([
                            str(i), str(pred_idx), "FS", "0", "", ""
                        ])
                    except StopIteration:
                        logger.error(
                            "cpm_predecesora_no_encontrada_p6",
                            actividad_id=act.id,
                            predecesora_id=pred_id,
                            export_format="primavera_p6",
                            note="Grafo con predecesora fantasma. Exportacion P6 incompleta.",
                        )

        if pred_rows:
            emit_table("TASKPRED", ["task_id", "pred_task_id", "pred_type", "lag_hr_cnt", "float_path", "aref"], pred_rows)

        # UDFTYPE (custom fields)
        emit_table("UDFTYPE", ["udf_type_id", "table_name", "udf_type_name", "udf_type_label", "logical_data_type"], [
            ["1", "TASK", "WBS_MEGALODON", "WBS Megalodon", "Text"],
            ["2", "TASK", "COSTO_REAL", "Costo Real", "Cost"]
        ])

        # UDFVALUE
        udf_rows = []
        for i, act in enumerate(self.actividades, 1):
            udf_rows.append([str(i), "1", act.wbs or str(i)])
            if act.costo_real is not None:
                udf_rows.append([str(i), "2", str(float(act.costo_real))])

        if udf_rows:
            emit_table("UDFVALUE", ["udf_type_id", "fk_id", "udf_text", "udf_date", "udf_number"], udf_rows)

        xer_content = "\n".join(lines)
        return xer_content.encode('utf-8')


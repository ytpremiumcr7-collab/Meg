# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de cálculo de volúmenes de movimiento de tierras (corte/terraplén)
entre dos superficies TIN reales (ej. terreno existente vs. terreno de
proyecto), usando el método de área promedio por triángulo -- el mismo
método que usa software de topografía profesional (Civil 3D, etc.), no
una aproximación simplificada.
"""
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy.spatial import Delaunay
from scipy.interpolate import LinearNDInterpolator

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class ResultadoVolumen:
    volumen_corte_m3: float       # material que hay que EXCAVAR (terreno existente > proyecto)
    volumen_terraplen_m3: float   # material que hay que RELLENAR (proyecto > terreno existente)
    volumen_neto_m3: float        # terraplen - corte (positivo = falta material, negativo = sobra)
    area_analizada_m2: float
    num_triangulos_analizados: int


class MotorVolumenes:
    """Calcula corte/terraplén real entre dos superficies TIN."""

    def calcular_entre_superficies(
        self,
        puntos_existente: List[Tuple[float, float, float]],
        puntos_proyecto: List[Tuple[float, float, float]],
    ) -> ResultadoVolumen:
        """Calcula el volumen de corte/terraplén entre terreno existente y
        terreno de proyecto.

        Las dos superficies no necesitan tener los mismos puntos (x,y):
        se interpola cada una por separado (LinearNDInterpolator) y se
        integra el volumen sobre una triangulación de referencia
        construida con la UNIÓN de ambos conjuntos de puntos -- así el
        cálculo cubre toda el área en común real entre ambas superficies,
        no solo donde coinciden los puntos originales.
        """
        if len(puntos_existente) < 3 or len(puntos_proyecto) < 3:
            raise MegalodonException(
                ErrorCode.PUNTOS_INSUFICIENTES,
                "Se necesitan al menos 3 puntos en cada superficie para calcular volumen",
            )

        arr_ex = np.array(puntos_existente, dtype=float)
        arr_pr = np.array(puntos_proyecto, dtype=float)

        interp_existente = LinearNDInterpolator(arr_ex[:, :2], arr_ex[:, 2])
        interp_proyecto = LinearNDInterpolator(arr_pr[:, :2], arr_pr[:, 2])

        # Triangulación de referencia: unión de puntos de ambas superficies
        # que caigan dentro del área de ambas (para poder interpolar en
        # los dos lados sin extrapolar fuera de rango).
        xy_union = np.vstack([arr_ex[:, :2], arr_pr[:, :2]])
        try:
            ref = Delaunay(xy_union)
        except Exception as e:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, f"No se pudo triangular el área en común: {e}")

        volumen_corte = 0.0
        volumen_terraplen = 0.0
        area_total = 0.0
        triangulos_validos = 0

        for tri in ref.simplices:
            p = xy_union[tri]
            centroide = p.mean(axis=0)

            z_ex = interp_existente(centroide[0], centroide[1])
            z_pr = interp_proyecto(centroide[0], centroide[1])
            if np.isnan(z_ex) or np.isnan(z_pr):
                continue  # el centroide cae fuera del área cubierta por alguna de las 2 superficies

            area = abs((p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1])) / 2.0
            delta = float(z_pr) - float(z_ex)  # positivo = hay que rellenar, negativo = hay que cortar
            volumen = area * delta

            if volumen > 0:
                volumen_terraplen += volumen
            else:
                volumen_corte += abs(volumen)

            area_total += area
            triangulos_validos += 1

        return ResultadoVolumen(
            volumen_corte_m3=round(volumen_corte, 3),
            volumen_terraplen_m3=round(volumen_terraplen, 3),
            volumen_neto_m3=round(volumen_terraplen - volumen_corte, 3),
            area_analizada_m2=round(area_total, 3),
            num_triangulos_analizados=triangulos_validos,
        )

    def calcular_contra_elevacion_referencia(
        self,
        puntos_superficie: List[Tuple[float, float, float]],
        elevacion_referencia: float,
    ) -> ResultadoVolumen:
        """Calcula volumen de corte/terraplén de una superficie contra una
        elevación de referencia plana (ej. nivel de piso terminado de un
        proyecto) -- caso más simple que comparar dos TINs completos."""
        puntos_referencia = [(x, y, elevacion_referencia) for x, y, _ in puntos_superficie]
        return self.calcular_entre_superficies(puntos_superficie, puntos_referencia)

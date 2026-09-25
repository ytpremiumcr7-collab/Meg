/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { megalodonClient } from '@/lib/api-client';
import type { Expediente } from '@/lib/megalodon-client';

export interface NuevoExpedienteInput {
  titulo: string;
  organo: string;
  unidad_administrativa: string;
  serie_documental: string;
  subserie_documental: string;
  descripcion?: string;
  proyecto_nombre?: string;
  ubicacion_obra?: string;
  monto_contrato?: number;
  plazo_dias?: number;
  tipo_contrato?: string;
  responsable_tecnico?: string;
  responsable_ejecutivo?: string;
}

interface ExpedienteState {
  expedientes: Expediente[];
  expedienteActivoId: string | null;
  isLoading: boolean;
  error: string | null;

  cargarExpedientes: () => Promise<void>;
  crearExpediente: (data: NuevoExpedienteInput) => Promise<Expediente>;
  setExpedienteActivo: (id: string | null) => void;
  expedienteActivo: () => Expediente | null;
}

// Fuente única de verdad de "en qué expediente estoy trabajando" para
// todo el sistema (costos, BIM, documentos, etc.). Antes no existía nada
// de esto -- cada app operaba sobre datos de demo hardcodeados, sin
// ningún expediente real detrás.
export const useExpedienteStore = create<ExpedienteState>()(
  persist(
    (set, get) => ({
      expedientes: [],
      expedienteActivoId: null,
      isLoading: false,
      error: null,

      cargarExpedientes: async () => {
        set({ isLoading: true, error: null });
        try {
          const expedientes = await megalodonClient.expedientes.list({ limit: 100 });
          set({ expedientes, isLoading: false });

          // Si el expediente activo guardado ya no existe (borrado,
          // cuenta distinta, etc.), se limpia en vez de dejarlo apuntando
          // a algo inválido.
          const activoId = get().expedienteActivoId;
          if (activoId && !expedientes.some((e) => e.id === activoId)) {
            set({ expedienteActivoId: null });
          }
        } catch (e) {
          set({
            isLoading: false,
            error: e instanceof Error ? e.message : 'No se pudieron cargar los expedientes',
          });
        }
      },

      crearExpediente: async (data) => {
        set({ isLoading: true, error: null });
        try {
          const nuevo = await megalodonClient.expedientes.create(data);
          set((state) => ({
            expedientes: [nuevo, ...state.expedientes],
            expedienteActivoId: nuevo.id, // el recién creado pasa a ser el activo
            isLoading: false,
          }));
          return nuevo;
        } catch (e) {
          const message = e instanceof Error ? e.message : 'No se pudo crear el expediente';
          set({ isLoading: false, error: message });
          throw new Error(message);
        }
      },

      setExpedienteActivo: (id) => set({ expedienteActivoId: id }),

      expedienteActivo: () => {
        const { expedientes, expedienteActivoId } = get();
        return expedientes.find((e) => e.id === expedienteActivoId) ?? null;
      },
    }),
    {
      name: 'megalodon-expediente-activo',
      // Solo se persiste CUÁL es el activo; la lista se vuelve a pedir al
      // backend en cada sesión (podría estar desactualizada si se persiste).
      partialize: (state) => ({ expedienteActivoId: state.expedienteActivoId }),
    }
  )
);

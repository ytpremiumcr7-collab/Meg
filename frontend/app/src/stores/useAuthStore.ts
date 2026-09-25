/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import type { User } from '@/types';
import { megalodonClient } from '@/lib/api-client';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isBootComplete: boolean;
  accessToken: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  error: string | null;
  /** Login real contra el backend (email + password). */
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setBootComplete: (complete: boolean) => void;
}

// ANTES: login(username, _password?) era síncrono, aceptaba CUALQUIER
// texto de 2+ caracteres como si fuera un usuario válido, y jamás tocaba
// el backend -- el propio código lo decía: "en producción esto irá
// contra el backend". Ahora sí va contra el backend real.
//
// TAMBIÉN SE ELIMINÓ loginAsGuest(): entraba al shell con
// isAuthenticated=true y accessToken=null. No era solo un modo demo
// inofensivo -- era un bypass real de autenticación (cualquiera podía
// entrar al escritorio sin credenciales), y de cualquier forma cada
// llamada real al backend le habría fallado con 401 al no traer token.
// El freeze técnico acordado es explícito: sin auth de invitado en producción.
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isBootComplete: false,
  accessToken: null,
  refreshToken: null,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const token = await megalodonClient.auth.login(email, password);
      const backendUser = await megalodonClient.auth.me();
      const user: User = {
        id: backendUser.id,
        name: backendUser.full_name,
        username: backendUser.email,
        isGuest: false,
      };
      set({
        user,
        isAuthenticated: true,
        isBootComplete: false,
        accessToken: token.access_token,
        refreshToken: token.refresh_token,
        isLoading: false,
      });
      import('./useEntitlementsStore').then(({ useEntitlementsStore }) => {
        void useEntitlementsStore.getState().cargar();
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : 'No se pudo iniciar sesión';
      set({ isLoading: false, error: message, isAuthenticated: false });
      throw new Error(message);
    }
  },

  logout: () => {
    void megalodonClient.auth.logout().catch(() => undefined);
    megalodonClient.setToken('');
    set({
      user: null,
      isAuthenticated: false,
      isBootComplete: false,
      accessToken: null,
      refreshToken: null,
    });
  },

  setBootComplete: (complete) => set({ isBootComplete: complete }),
}));

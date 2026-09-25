/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Instancia única del cliente Megalodon para toda la app.
 *
 * URL configurable vía VITE_API_URL (ver .env.example en la raíz del
 * frontend). Si no se define, cae a localhost:8000 para desarrollo local.
 */
import { MegalodonClient } from './megalodon-client';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const megalodonClient = new MegalodonClient(API_URL);

// Si ya había un token guardado (ver useAuthStore), se re-aplica al
// recargar la página -- si no se hace esto, tras un refresh el usuario
// se ve "autenticado" en el store pero el cliente HTTP no manda el
// header Authorization en ninguna request.
const STORAGE_KEY = 'megalodon-auth';
try {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    const parsed = JSON.parse(stored);
    const token = parsed?.state?.accessToken;
    if (token) megalodonClient.setToken(token);
  }
} catch {
  // localStorage puede no estar disponible (SSR, modo privado, etc.) --
  // no es crítico, el usuario simplemente tendría que volver a iniciar
  // sesión.
}

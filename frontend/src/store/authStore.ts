/**
 * Zustand-хранилище авторизации.
 *
 * Хранит JWT и профиль, переживает перезагрузку страницы (persist в
 * localStorage) и связывает Axios-клиент со своим состоянием: клиент получает
 * токен отсюда, а при 401 вызывает logout().
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { bindAuth } from "@/api/client";
import { fetchMe, login as loginRequest } from "@/api/endpoints";
import type { LoginPayload, User } from "@/types/models";

interface AuthState {
  token: string | null;
  user: User | null;
  login: (payload: LoginPayload) => Promise<User>;
  logout: () => void;
  /** Обновляет профиль по токену; при невалидном токене разлогинивает. */
  syncUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,

      login: async (payload) => {
        const response = await loginRequest(payload);
        set({ token: response.access_token, user: response.user });
        return response.user;
      },

      logout: () => set({ token: null, user: null }),

      syncUser: async () => {
        const { token } = useAuthStore.getState();
        if (!token) return;
        try {
          const user = await fetchMe();
          set({ user });
        } catch {
          // Токен просрочен или отозван — сессию надо закрыть.
          set({ token: null, user: null });
        }
      },
    }),
    {
      name: "protokol-auth",
      storage: createJSONStorage(() => localStorage),
      // В localStorage кладём только данные сессии, не функции.
      partialize: (state) => ({ token: state.token, user: state.user }),
    },
  ),
);

// Связка «клиент → стор» без циклического импорта.
bindAuth({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: () => useAuthStore.getState().logout(),
});

/** Есть ли активная сессия. Используется PrivateRoute. */
export const useIsAuthenticated = (): boolean => useAuthStore((state) => state.token !== null);

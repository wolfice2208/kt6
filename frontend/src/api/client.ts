/**
 * Единственный Axios-клиент приложения.
 *
 * * baseURL берётся из VITE_API_URL — адрес бэкенда не размазан по коду;
 * * request-interceptor подставляет JWT из хранилища авторизации;
 * * response-interceptor перехватывает 401 (истёкший токен) и разлогинивает,
 *   чтобы пользователь не оставался «полуавторизованным».
 *
 * Зависимости не циклические: модуль не импортирует стор, а получает от него
 * две функции через bindAuth(). Стор вызывает bindAuth() при создании.
 */

import axios, { type AxiosError, type AxiosInstance } from "axios";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

interface AuthBindings {
  /** Текущий токен или null, если пользователь не вошёл. */
  getToken: () => string | null;
  /** Вызывается при 401, кроме самой попытки входа. */
  onUnauthorized: () => void;
}

let bindings: AuthBindings = {
  getToken: () => null,
  onUnauthorized: () => undefined,
};

/** Связывает клиент с хранилищем авторизации (вызывается один раз при его создании). */
export function bindAuth(next: AuthBindings): void {
  bindings = next;
}

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = bindings.getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status;
    const url = error.config?.url ?? "";
    // Неверный пароль на форме входа — это не «сессия истекла».
    const isLoginAttempt = url.includes("/auth/login");
    if (status === 401 && !isLoginAttempt) {
      bindings.onUnauthorized();
    }
    return Promise.reject(error);
  },
);

/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Базовый адрес API, например http://127.0.0.1:8000/api */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

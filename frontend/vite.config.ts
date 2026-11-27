import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Адрес API задаётся переменной окружения VITE_API_URL (см. .env.example),
// чтобы не пересобирать проект при смене бэкенда.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    watch: {
      // Скрипты проверки интерфейса и временные каталоги не должны попадать
      // в наблюдение Vite: иначе hot-reload пытается следить за своими же
      // временными файлами и падает с EBUSY на Windows.
      ignored: ["**/scripts/**", "**/.tmp/**"],
    },
  },
});

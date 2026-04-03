// Конфиг для локальной разработки (npm run dev:local)
// Проксирует API-запросы на локально запущенный config-api (localhost:8000)
// В Docker используется vite.config.js + nginx.conf
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/cameras': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})

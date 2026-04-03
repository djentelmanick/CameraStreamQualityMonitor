import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/cameras': 'http://config-api:8000',
      '/health': 'http://config-api:8000',
    },
  },
})

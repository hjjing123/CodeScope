import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const hmrClientPort = Number(process.env.VITE_HMR_CLIENT_PORT || 0)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
  server: {
    hmr:
      hmrClientPort > 0
        ? {
            port: hmrClientPort,
            clientPort: hmrClientPort,
          }
        : undefined,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, ''), // We don't need rewrite because backend expects /api
      },
    },
  },
})

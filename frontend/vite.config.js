import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  // Load .env from the parent project dir so we share IMAGE_SERVICE_PORT.
  const env = loadEnv(mode, '../', '')
  const backendPort = env.IMAGE_SERVICE_PORT || '8765'
  const frontendPort = parseInt(env.FRONTEND_PORT || '5173', 10)

  return {
    plugins: [vue()],
    server: {
      port: frontendPort,
      strictPort: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})

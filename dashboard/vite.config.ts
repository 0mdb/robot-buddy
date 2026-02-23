import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../supervisor/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/ws': {
        target: 'ws://192.168.55.100:8080',
        ws: true,
      },
      '/status': 'http://192.168.55.100:8080',
      '/params': 'http://192.168.55.100:8080',
      '/actions': 'http://192.168.55.100:8080',
      '/video': 'http://192.168.55.100:8080',
      '/debug': 'http://192.168.55.100:8080',
    },
  },
})

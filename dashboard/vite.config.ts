import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  // @copilotkit/react-core and its /v2 subpath share internal chunks;
  // pre-bundling them separately (Vite's default, dep-by-dep behavior)
  // produced two disconnected module graphs and a "more than one copy of
  // React" crash inside the shared chunk. Listing both together forces one
  // consistent optimize pass.
  optimizeDeps: {
    include: ['@copilotkit/react-core', '@copilotkit/react-core/v2'],
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8123',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})

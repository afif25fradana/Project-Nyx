import { defineConfig, type HttpProxy } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Dynamically inject bootstrap auth token into Vite proxy requests
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tokenPath = path.resolve(__dirname, '../backend/data/.auth_token');
const attachAuthProxy = (proxy: HttpProxy.Server) => {
  proxy.on('error', (_err, _req, res) => {
    // Return 503 cleanly when backend (port 8765) is offline instead of dumping ECONNREFUSED terminal logs
    if (res && 'writeHead' in res && typeof res.writeHead === 'function' && !res.headersSent) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Backend daemon offline (127.0.0.1:8765)' }));
    }
  });
  proxy.on('proxyReq', (proxyReq) => {
    try {
      if (fs.existsSync(tokenPath)) {
        const token = fs.readFileSync(tokenPath, 'utf-8').trim();
        if (token) proxyReq.setHeader('X-Nyx-Token', token);
      }
    } catch {
      // Backend may not have initialized token file yet
    }
  });
  proxy.on('proxyReqWs', (proxyReq) => {
    try {
      if (fs.existsSync(tokenPath)) {
        const token = fs.readFileSync(tokenPath, 'utf-8').trim();
        if (token) proxyReq.setHeader('X-Nyx-Token', token);
      }
    } catch {
      // Backend may not have initialized token file yet
    }
  });
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        configure: attachAuthProxy,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8765',
        ws: true,
        configure: attachAuthProxy,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});

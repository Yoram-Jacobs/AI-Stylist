// Vite config for the DressApp Chrome Extension (Manifest V3).
//
// We use @crxjs/vite-plugin which:
//   * reads ``manifest.json`` and emits a Web-Store-compliant ``dist/``
//   * bundles each entry point (popup, content script, service worker)
//     with HMR in dev (``vite dev``), so reloading the extension at
//     ``chrome://extensions`` picks up code changes instantly.
//   * rewrites asset paths inside manifest.json for production builds.
//
// Why a path alias for ``@/``? It lets us match the main app's import
// style (``import { Button } from '@/components/...'``) so future
// shared-component extraction is a one-line move.
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { crx } from '@crxjs/vite-plugin';
import manifest from './manifest.json' with { type: 'json' };

export default defineConfig({
  plugins: [react(), crx({ manifest })],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
    target: 'esnext',
    rollupOptions: {
      // Keep chunk names predictable so reviewers can pin SHAs in
      // the future Web-Store submission.
      output: { chunkFileNames: 'assets/[name]-[hash].js' },
    },
  },
  server: {
    // crxjs HMR uses port 5173 by default; keep it explicit so
    // ``yarn dev`` is reproducible across machines.
    port: 5173,
    strictPort: true,
  },
});

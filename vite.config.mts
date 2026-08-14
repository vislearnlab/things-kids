import { defineConfig } from 'vite';
import { resolve } from 'path';

// Vite frontend build config — mirrors the lab pattern from
// vislearnlab/hybrid-drawing-rating.
//
// `base: './'` makes asset paths relative so the same `dist/` works when
// served from `/` locally or from `/<study-prefix>/` behind nginx.
//
// `publicDir: public/` is the default — files there are served at root in
// dev and copied verbatim into `dist/` at build. That's where stimuli,
// audio, and Zorpie GIFs live.
export default defineConfig({
  base: './',
  publicDir: resolve(__dirname, 'public'),
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
  server: {
    port: 3000,
    open: false,
    // Forward data routes to the Express server (npm run start on :9000)
    // so `npm run dev` writes to Mongo with hot reload.
    proxy: {
      '/submit': 'http://localhost:9000',
      '/health': 'http://localhost:9000',
    },
  },
  preview: {
    port: 4000,
  },
});

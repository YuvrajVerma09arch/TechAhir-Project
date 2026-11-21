import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The backend is a separate FastAPI service. The dashboard talks to it over REST;
// the base URL is configured at build time with VITE_API_BASE_URL (see src/api.js).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});

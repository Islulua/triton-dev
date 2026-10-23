import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Local development only. The production bundle uses same-origin /api directly.
const target = process.env.TRITON_DEV_API_TARGET || 'http://127.0.0.1:8765';
const backend = new URL(target);
if (!['127.0.0.1', 'localhost'].includes(backend.hostname) || backend.protocol !== 'http:') {
  throw new Error('The developer API proxy accepts local HTTP targets only');
}
export default defineConfig({
  build: { outDir: 'dist/client' },
  optimizeDeps: { include: ['react', 'react-dom/client'] },
  server: {
    host: '127.0.0.1', allowedHosts: ['terminal.local', 'localhost'],
    proxy: { '/api': {
      target, changeOrigin: true,
      configure(proxy) {
        proxy.on('proxyReq', (proxyReq, req) => {
          const origin = req.headers.origin;
          // Reject cross-origin browser traffic; only translate our own dev origin.
          if (origin === `http://${req.headers.host}`) proxyReq.setHeader('Origin', backend.origin);
        });
      },
    } },
  },
  plugins: [react()],
});

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    // Sonner ships a JS style injector as well as the same standalone stylesheet.
    // Bundle the stylesheet and omit only that injector call; keep script CSP strict.
    { name: 'sonner-external-css', enforce: 'pre', transform(code, id) {
      if (id.replaceAll('\\', '/').endsWith('/sonner/dist/index.mjs')) {
        const next = code.replace(/^__insertCSS\(".*"\);$/m, '')
        if (next === code) throw new Error('Pinned Sonner CSS injector changed; review before building.')
        return {code:next,map:null}
      }
    } },
    react(), tailwindcss(),
  ],
  base: '/static/app/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: { outDir: '../static/app', emptyOutDir: true, assetsInlineLimit: 0, sourcemap: false },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})

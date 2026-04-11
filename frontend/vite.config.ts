import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import pkg from './package.json'

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  plugins: [
    react(),
    VitePWA({
      // F-058: prompt-mode instead of autoUpdate. autoUpdate + controllerchange
      // reloads the page silently on deploy — users who are mid-form lose
      // their unsaved input. The SW still downloads the new assets in the
      // background; the UI shows a toast and lets the user opt in.
      registerType: 'prompt',
      includeAssets: ['vite.svg'],
      manifest: {
        name: 'PraxisZeit - Zeiterfassung',
        short_name: 'PraxisZeit',
        description: 'Zeiterfassung fuer Arztpraxen',
        theme_color: '#4A90B8',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        icons: [
          {
            src: '/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /\.pdf$/],
        // No API caching - API responses contain sensitive user data
        // that must not persist in Cache Storage after logout
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

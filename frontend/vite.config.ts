import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      workbox: {
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024
      },
      manifest: {
        name: '智能旅行助手',
        short_name: '旅行助手',
        description: '基于AI与设备传感器信息的旅行规划助手',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#ffffff',
        icons: [
          {
            src: '/icon.svg',
            sizes: '512x512',
            type: 'image/svg+xml',
            purpose: 'any'
          }
        ]
      },
      devOptions: {
        enabled: true
      }
    })
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    host: true,
    port: 5173,
    // 允许通过公网隧道域名访问 dev server（作业演示常用）
    // Vite 支持 true(允许所有Host) 或字符串数组(白名单)
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 让 FastAPI 文档也能通过同一公网域名访问（适合课堂演示/作业提交）
      '/docs': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/redoc': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})


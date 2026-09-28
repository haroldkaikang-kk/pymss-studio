import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  build: {
    // Conservative syntax baseline. Runtime APIs, CSS and native playback
    // still require verification with Monterey's Safari/WebKit 17.6.
    target: 'safari15',
    cssTarget: 'safari15',
  },
  plugins: [
    vue(),
    Components({
      resolvers: [NaiveUiResolver()],
      dts: false,
      types: [],
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ['**/src-tauri/**'] },
  },
})

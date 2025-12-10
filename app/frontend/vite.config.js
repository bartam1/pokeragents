import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      // Allow serving files from the parent data folder
      allow: ['..'],
    },
  },
  resolve: {
    alias: {
      '@data': path.resolve(__dirname, '../data/results'),
    },
  },
})

import { defineConfig } from 'vitest/config'

export default defineConfig({
  build: {
    emptyOutDir: true,
    manifest: true,
    outDir: '../static/studio/dist',
    rollupOptions: {
      input: {
        articleEditor: 'src/article-editor.ts',
        editor: 'src/editor.ts',
      },
    },
  },
  test: {
    environment: 'happy-dom',
  },
})

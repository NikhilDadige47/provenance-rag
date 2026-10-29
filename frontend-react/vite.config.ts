import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin, type ProxyOptions } from 'vite'

const apiProxy: ProxyOptions = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  cookieDomainRewrite: '',
}

function serveDemoCorpusPdfs(): Plugin {
  const corpusDir = path.resolve(__dirname, '../demo_corpus')
  const serve = (
    req: { url?: string },
    res: {
      statusCode: number
      setHeader: (k: string, v: string) => void
      end: (body?: string) => void
    },
    next: () => void
  ) => {
    const filename = path.basename(decodeURIComponent((req.url || '').split('?')[0] || ''))
    if (!filename.toLowerCase().endsWith('.pdf')) {
      next()
      return
    }
    const filePath = path.resolve(corpusDir, filename)
    if (!filePath.startsWith(corpusDir) || !fs.existsSync(filePath)) {
      res.statusCode = 404
      res.end('Not found')
      return
    }
    res.setHeader('Content-Type', 'application/pdf')
    res.setHeader('Content-Disposition', 'inline')
    fs.createReadStream(filePath).pipe(res as unknown as NodeJS.WritableStream)
  }

  return {
    name: 'serve-demo-corpus-pdfs',
    configureServer(server) {
      server.middlewares.use('/demo_corpus', serve)
    },
    configurePreviewServer(server) {
      server.middlewares.use('/demo_corpus', serve)
    },
  }
}

export default defineConfig({
  plugins: [serveDemoCorpusPdfs(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/session': apiProxy,
      '/chat': apiProxy,
      '/upload': apiProxy,
      '/jobs': apiProxy,
      '/usage': apiProxy,
      '/examples': apiProxy,
      '/connections': apiProxy,
      '/health': apiProxy,
      '/metrics': apiProxy,
      '/terms': apiProxy,
    },
  },
})

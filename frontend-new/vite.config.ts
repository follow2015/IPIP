import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';


export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    },
    dedupe: ['react', 'react-dom', 'antd', '@ant-design/icons', '@ant-design/icons-svg']
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      
      '/realtime': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/realtime/, ''),
        ws: false 
      }
    }
  },
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        
        if (warning.message.includes('@ant-design/icons-svg')) return;
        warn(warning);
      },
      output: {
        manualChunks(id) {
          if (
            id.includes('node_modules/react') ||
            id.includes('node_modules/react-dom') ||
            id.includes('node_modules/react-router-dom')
          ) {
            return 'vendor';
          }
          if (id.includes('node_modules/antd') || id.includes('node_modules/@ant-design')) {
            return 'antd';
          }
          if (id.includes('node_modules/@tanstack/react-query')) {
            return 'query';
          }
          if (id.includes('node_modules/@antv')) {
            return 'g6';
          }
        }
      }
    },
    cssCodeSplit: true,
    commonjsOptions: {
      include: [/node_modules/]
    }
  },
  optimizeDeps: {
    include: ['antd', '@ant-design/icons']
  }
});

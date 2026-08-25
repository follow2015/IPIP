import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
/**
 * Vite 构建配置
 * - React 插件 + 路径别名 + 开发代理 + 分包策略
 */
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
            // ASGI 推送网关（realtime_gateway），SSE 事件流
            '/realtime': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/realtime/, ''),
                ws: false // SSE 不需要 WebSocket
            }
        }
    },
    build: {
        rollupOptions: {
            onwarn(warning, warn) {
                // 忽略 @ant-design/icons-svg 模块解析警告
                if (warning.message.includes('@ant-design/icons-svg'))
                    return;
                warn(warning);
            },
            output: {
                manualChunks(id) {
                    if (id.includes('node_modules/react') ||
                        id.includes('node_modules/react-dom') ||
                        id.includes('node_modules/react-router-dom')) {
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

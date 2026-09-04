import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

/**
 * ESLint Flat Config（ESLint 10 原生格式）
 *
 * 说明：项目原使用 .eslintrc.cjs，但 ESLint 9+ 默认只认 flat config，
 * 旧配置在 ESLint 10 下完全不生效（lint 命令空转）。本文件为等价迁移，
 * 并补充了测试文件 / 配置文件的豁免规则（P0 工程化门禁的一部分）。
 */

// Node 全局（供 vite.config.ts / vitest.config.ts 等构建配置文件使用）
const nodeGlobals = {
  __dirname: 'readonly',
  __filename: 'readonly',
  process: 'readonly',
  console: 'readonly',
  module: 'readonly',
  require: 'readonly',
  global: 'readonly'
};

export default tseslint.config(
  {
    ignores: ['dist', 'coverage', 'node_modules', 'src/types/api-generated.ts']
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true }
      }
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh
    },
    rules: {
      // 禁止 any 类型：存量代码有约 47 处 any（含 G6 拓扑图回调），
      // 统一降为 warning 作为技术债标记，待专项清理后再升为 error
      '@typescript-eslint/no-explicit-any': 'warn',
      // 禁止 window 全局变量（有意的兜底场景用 eslint-disable 标注）
      'no-restricted-globals': ['error', 'window'],
      // 未使用变量/参数：降级为 warning，与 tsconfig 中 noUnusedLocals:false 保持一致
      // （存量代码有约 197 处未使用导入/变量，需后续清理后再升为 error）
      // varsIgnorePattern/argsIgnorePattern: 允许 `_` 前缀的占位（如 rest 解构 `{ key: _k, ...r }`），
      // 配合 ignoreRestSiblings 根治"为绕过 no-unused-vars 而散落的 eslint-disable"问题（见 N1）。
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { varsIgnorePattern: '^_', argsIgnorePattern: '^_', ignoreRestSiblings: true }
      ],
      // React Hooks 规则（等价 plugin:react-hooks/recommended）
      // 原为 warn：存量 Detail 页 early-return 后再调用 Hook 会导致
      // "Rendered more hooks than during the previous render" 偶发整页崩溃。
      // 2026-07-22 已清零全部 41 处违规，升级为 error 纳入 CI 门禁，防止回归。
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // 无副作用的表达式（如裸函数调用）保持 error
      'no-unused-expressions': 'error'
    }
  },
  // 测试文件：允许 any（mock 类型宽松）与 window（jsdom 环境），关闭组件导出限制
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx', 'src/test/**/*'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-restricted-globals': 'off',
      'react-refresh/only-export-components': 'off'
    }
  },
  // 构建 / 测试配置文件：提供 node 全局（__dirname / process 等）
  {
    files: [
      '*.config.ts',
      '*.config.js',
      '*.config.cjs',
      '*.config.mjs',
      'vitest.config.ts',
      'vite.config.ts'
    ],
    languageOptions: { globals: nodeGlobals }
  }
);

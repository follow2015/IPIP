import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';


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
      
      
      '@typescript-eslint/no-explicit-any': 'warn',
      
      'no-restricted-globals': ['error', 'window'],
      
      
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { varsIgnorePattern: '^_', argsIgnorePattern: '^_', ignoreRestSiblings: true }
      ],
      
      
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      
      'no-unused-expressions': 'error'
    }
  },
  
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx', 'src/test/**/*'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-restricted-globals': 'off',
      'react-refresh/only-export-components': 'off'
    }
  },
  
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

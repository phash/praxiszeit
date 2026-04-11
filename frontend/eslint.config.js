// F-062: ESLint 9 flat config for the PraxisZeit frontend.
//
// Philosophy: enforce the minimum set of rules that would have caught the
// Sprint-6 useEffect-deps / NaN-formatter / stored-XSS bugs. No stylistic
// nit-picking — Prettier is not installed and the codebase is inconsistent
// on whitespace. We only flag behavioural bugs and TypeScript safety.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';

export default tseslint.config(
  {
    // Global ignores
    ignores: [
      'dist/**',
      'node_modules/**',
      'public/**',
      'vite.config.ts', // type-checked via tsc, no lint deps needed
      'postcss.config.js',
      'tailwind.config.js',
      'eslint.config.js',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // react-hooks plugin — the one that would have caught sprint 6.1
      ...reactHooks.configs.recommended.rules,
      'react-hooks/exhaustive-deps': 'warn',

      // react-refresh: HMR boundary enforcement
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // TypeScript: keep it practical. The codebase has a handful of
      // deliberate `any` for third-party untyped libraries; warn, don't
      // error. `@ts-ignore` is allowed when commented.
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      '@typescript-eslint/no-empty-object-type': 'off',

      // Behavioural rules that prevent real bugs
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
      'no-debugger': 'error',
      'no-alert': 'off', // window.confirm is used for PWA update prompt
      'prefer-const': 'warn',
      'eqeqeq': ['error', 'smart'],
    },
  }
);

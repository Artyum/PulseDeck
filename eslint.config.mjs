import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      "frontend/static/vendor/**",
      "**/*.min.js",
      "frontend/static/js/editor.bundle.js",
      "report/**",
      "logs/**",
      "mount/**",
      ".venv/**",
    ],
  },
  js.configs.recommended,
  eslintConfigPrettier,
  {
    files: ["frontend/static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        ...globals.browser,
        Alpine: "readonly",
        L: "readonly",
        htmx: "readonly",
      },
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": [
        "warn",
        {
          vars: "local",
          args: "none",
          caughtErrors: "none",
        },
      ],
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-useless-assignment": "off",
      "no-control-regex": "off",
      "no-prototype-builtins": "off",
    },
  },
  {
    files: ["frontend/static/sw.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        ...globals.serviceworker,
      },
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": [
        "warn",
        {
          vars: "local",
          args: "none",
          caughtErrors: "none",
        },
      ],
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
  {
    files: ["frontend/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "module",
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrors: "none",
        },
      ],
    },
  },
];

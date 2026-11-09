import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["tests/js/**/*.test.js"],
    coverage: {
      provider: "v8",
      include: ["schoolmenu/static/menus/app.js"],
      reporter: ["text", "json-summary", "lcov"],
      thresholds: { lines: 96, branches: 96, functions: 96, statements: 96 },
    },
  },
});

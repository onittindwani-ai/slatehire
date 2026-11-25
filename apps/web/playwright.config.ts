import { defineConfig } from "@playwright/test";
import { existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const PORT = process.env.WEB_PORT ?? "3000";
const ROOT = resolve(__dirname, "../..");
// the API runs from the project's own virtual environment (make install), or from the Python on PATH when there is none
const PY = process.env.PYTHON ?? (existsSync(`${ROOT}/.venv/bin/python`) ? `${ROOT}/.venv/bin/python` : "python3");
mkdirSync(resolve(ROOT, ".demo/exports"), { recursive: true }); // the demo database and handoff files live here and are not committed
const env = {
  ...process.env,
  MODE: "live", DEMO_MODE: "true", DATABASE_URL: `sqlite:///${ROOT}/.demo/e2e.sqlite3`, EXPORT_DIR: `${ROOT}/.demo/exports`, SEED_DIR: `${ROOT}/data`,
  SESSION_SECRET: "e2e-only-session-secret-not-for-real-use", APPLICATION_WEBHOOK_SECRET: "e2e-hook-secret", API_BASE_URL: "http://127.0.0.1:8000", LOGIN_BURST: "100", // every test signs in as the same person from the same address; the real limit has its own test
  INSECURE_COOKIES: "1", NEXT_PUBLIC_DEMO_HINT: "1",
} as Record<string, string>;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${PORT}`, channel: "chrome", headless: true },
  webServer: [
    { command: `"${PY}" -m uvicorn slatehire.api.app:app_from_env --factory --port 8000 --log-level warning --proxy-headers --forwarded-allow-ips 127.0.0.1`, cwd: ROOT, url: "http://127.0.0.1:8000/health", reuseExistingServer: false, env, timeout: 60_000 },
    { command: `pnpm exec next start -p ${PORT}`, cwd: __dirname, url: `http://localhost:${PORT}/login`, reuseExistingServer: false, env, timeout: 60_000 },
  ],
});

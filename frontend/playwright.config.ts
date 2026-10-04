import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  workers: 1,
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  webServer: [
    {
      command: 'cd ../backend && ../.venv/bin/uvicorn app.main:app --port 8000',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
    },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true },
  ],
})

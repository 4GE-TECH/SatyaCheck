import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1, timeout: 30_000,
  reporter: 'list', outputDir: './.impeccable/test-results',
  use: {
    baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 },
    colorScheme: 'light', reducedMotion: 'reduce', permissions: ['microphone'],
    launchOptions: { executablePath: process.env.SATYACHECK_TEST_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe', chromiumSandbox: true, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] },
  },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
});


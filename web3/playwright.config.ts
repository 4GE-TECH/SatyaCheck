import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  timeout: 40_000,
  reporter: 'list',
  outputDir: './.test-results',
  use: {
    baseURL: 'http://127.0.0.1:5175',
    viewport: { width: 1440, height: 1000 },
    colorScheme: 'dark',
    permissions: ['microphone'],
    launchOptions: {
      executablePath: process.env.SATYACHECK_TEST_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
    },
  },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --strictPort', url: 'http://127.0.0.1:5175', reuseExistingServer: true },
});

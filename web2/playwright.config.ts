import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 45000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', permissions: ['microphone'], launchOptions: { executablePath: process.env.SATYACHECK_TEST_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'] } },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5174', reuseExistingServer: true },
});

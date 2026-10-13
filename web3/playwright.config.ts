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
  // The admin console needs sign-in, so tests build against a stand-in Supabase project that
  // the specs answer with page.route (tests/browser/admin.spec.ts). No real service is used.
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --strictPort', url: 'http://127.0.0.1:5175', reuseExistingServer: false,
    env: { VITE_SUPABASE_URL: 'https://supabase.test', VITE_SUPABASE_ANON_KEY: 'test-anon-key' },
  },
});

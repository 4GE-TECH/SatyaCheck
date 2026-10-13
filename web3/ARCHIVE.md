# The earlier user dashboard

The web app is now the admin console: Overview, Live calls, All calls, Accounts. The pages it
replaced are kept, not deleted:

- check a recording
- listen live
- phone calls (Exotel feed)
- known voices
- reports
- help

They're preserved in two places:

1. **In this tree.** `src/features/{check,live,calls,voices,report,help}` are unchanged. They
   are no longer routed, and they still compile with the rest of the app. Their browser tests
   are in `tests/archive/user-dashboard.spec.ts`, which Playwright does not run.
2. **On a branch.** `archive/web3-user-dashboard` is the whole repo as it was before the
   switch (commit `59f8564`).

## Bringing them back

To restore the old app exactly:

```bash
git checkout archive/web3-user-dashboard -- web3/src/main.tsx web3/src/app/Shell.tsx \
  web3/src/app/CommandPalette.tsx web3/tests/browser web3/playwright.config.ts
```

To have both, add the old routes next to the admin ones in `src/main.tsx`, for example
`/check` → `CheckPage`, and the old `AuthGate` for non-admin accounts.

The branch exists only on the machine that made it until someone pushes it
(`git push -u origin archive/web3-user-dashboard`).

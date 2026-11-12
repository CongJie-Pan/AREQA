# Initial render consistency fix and validation

Date: 2026-11-12. Follows [the investigation](./report.md). Product changes remain local until deployed.

## Changed behavior

- `frontend/src/app/globals.css` now owns composer shell, row, textarea and expanded geometry. The corresponding definitions were removed from `ChatInput/styles.ts` and its class composition. Empty-state spacing, logo sizing, copy reservation and critical control sizing now match their hydrated values, preventing the surrounding content from moving the composer.
- `ChatContainer/index.tsx` exposes independent mobile-open and desktop-collapsed flags on the floating navigation anchor. Responsive CSS positions the anchor from the relevant flag before React knows the viewport. Existing pressed/hover feedback remains intact.
- `lib/interfacePreferences.ts` provides shared, allowlisted preference values. A blocking head script applies the theme before paint, reads legacy localStorage best-effort and mirrors theme/language into cookies. No untrusted cookie or storage string is inserted into script source.
- `app/layout.tsx` reads validated cookie preferences and passes one snapshot through `AppProviders` into `UserPreferencesProvider`. React uses that server snapshot through hydration, then exposes browser preferences using `useSyncExternalStore`. The provider avoids resetting the bootstrap's document attributes during hydration.
- `ChatInput/index.tsx` measures textarea height before paint, caps it at 200px and enables vertical overflow only beyond the cap. Width changes, resize events, language changes and completed font loading trigger remeasurement. Observers, frame callbacks and event listeners are cleaned up when the textarea is replaced or unmounted.

## Regression evidence

The new `UserPreferences.hydration.test.tsx` failed against the original implementation: restoring a saved Traditional Chinese/light preference caused React's recoverable hydration error and subtree regeneration. It passes with the fix.

The delayed-JavaScript research probe was also repeated for mobile light mode and a legacy Traditional Chinese preference:

| Measurement at 390×844 | Original server → hydrated | Fixed server → hydrated |
|---|---|---|
| Composer height | 56 → 50px | 50 → 50px |
| Composer radius | 20 → 999px | 999 → 999px |
| Composer y position | 398.7 → 444.6px | 444.6 → 444.6px |
| Navigation x position | 228 → 16px | 16 → 16px |
| Light composer background | Dark → white | White → white |
| Legacy Chinese hydration errors | Present | None recorded |

Screenshots and detailed probe samples remain under the uncommitted `.audit/initial-render-research/fixed-*` paths. The committed browser suite reproduces the first-paint assertions without relying on those local files.

## Validation

- Focused Vitest: **71 tests passed** across ChatInput, preference bootstrap, actual SSR/hydration, auth/logout, sidebar state, mobile viewport styles and light surfaces. After the final textarea scheduling adjustment, the 47 tests covering the changed paths were repeated successfully.
- `npm run check:report:strict`: **passed** after the final production source changes (ESLint with zero warnings, TypeScript).
- `npm run build`: **passed**, including production compilation, TypeScript, page collection and static generation.
- Production Playwright: **16 cases passed** in Chromium and WebKit. For each engine: 320px, 390px and 1280px × light/dark; delayed script loading with exact pre/post geometry; sidebar opening/collapse; empty/single-line overflow; long input capped at 200px with scrolling; legacy Chinese migration and cookie-backed reload; localStorage denial with cookie fallback.
- Additional production Playwright: unchanged draft reflow on viewport/font changes, **2 cases passed**, one per engine.
- `git diff --check`: passed.

Initial browser execution was interrupted by an unresponsive development server left over from the environment restart. After restarting it, two WebKit assertions measured the button's transient press-scale transform instead of its layout anchor; the test was corrected to inspect the anchor. The complete 16-case suite then passed against the production build. No product change was made to remove the intended feedback animation.

Existing JSDOM/Ant Design warnings about pseudo-element computed styles and feedback TextArea height appeared in the auth tests, which passed. The build emitted the existing stale `baseline-browser-mapping` data notice. These did not fail the checks. The entire repository test suite was not run; historical guest-chat integration failures from the investigation were outside this change's focused validation.

## Compatibility and remaining limits

- Cookie-backed layouts use dynamic, per-request SSR instead of a shared static page. Hosting must support the existing Next.js server runtime; the production build and `next start` were validated locally.
- Legacy localStorage remains supported. On the first visit without mirrored cookies, language text can update once after hydration; subsequent requests can render the selected language on the server. The first migration no longer causes hydration failure or the measured composer/navigation layout shift.
- Cookie and localStorage persistence are best-effort. UI choices remain usable in local state when storage is unavailable. Only validated UI theme/language values are stored in the new cookies; authentication storage and provider secrets are unaffected.
- The originally reported gold line was not conclusively identified on a physical phone. The fix removes native textarea overflow for empty/short drafts and preserves intentional overflow for long drafts; it does not claim a physical-device reproduction of the original artifact.
- Chromium and WebKit engine checks cover responsive layouts, not actual iOS/Android hardware, browser chrome or on-screen keyboard behavior. Physical Safari/Chrome refresh, rotation and keyboard verification remains useful before rollout.
- No new render/measurement logs were added: geometry and preference synchronization would produce noisy startup/typing logs, and do not involve a new provider or external state machine. Existing safe sidebar transition logging remains in place.

## Reproduction commands

From the repository root:

```bash
npm --prefix frontend test -- ../tests/frontend/components/ChatInput/index.test.tsx ../tests/frontend/components/UserPreferences.hydration.test.tsx ../tests/frontend/lib/interfacePreferences.test.ts ../tests/frontend/components/auth.logout.test.tsx ../tests/frontend/components/ChatContainer/sidebarState.test.tsx ../tests/frontend/components/ChatContainer/mobileViewportStyles.test.ts ../tests/frontend/components/lightThemeSurfaces.test.ts
npm --prefix frontend run check:report:strict
npm --prefix frontend run build
npm --prefix frontend run start -- --port 3006
```

With the production server running, in another terminal:

```bash
AREQA_TEST_BASE_URL=http://localhost:3006 node frontend/node_modules/@playwright/test/cli.js test --config tests/e2e/initial-render/playwright.config.ts
```

Without `AREQA_TEST_BASE_URL`, the Playwright configuration starts or reuses the development server on port 3005.

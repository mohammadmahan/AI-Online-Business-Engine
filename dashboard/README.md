# Local Dashboard

Static Persian (RTL) status dashboard for the AI-First Online Business
Engine. Reads `dashboard/state_summary.json` at runtime (with an
embedded fallback object, so opening `index.html` directly via
`file://` still renders).

> **Historical archive, not live telemetry.** The current snapshot is
> `HISTORICAL_STATIC`, captured from `f17a9a0` on 2026-09-16. Its product and
> test counts are historical and must never be read as current health or test
> evidence. The page shows this warning prominently.
>
> Run the metadata/freshness guard after any snapshot edit:
>
> ```bash
> node dashboard/check-snapshot.mjs
> ```
>
> A `CURRENT` snapshot is accepted only when its commit equals HEAD and its
> observation is at most 24 hours old. A historical snapshot must carry source,
> environment, commit, observation date, a warning, and matching HTML markers.

Run local static server from repository root:

```bash
python3 -m http.server 8080 --directory dashboard
```

Open in browser:

```
http://localhost:8080/
```

Notes:

- No build step, no npm, no Node.js — plain HTML5 + vanilla JS +
  Tailwind CSS + Vazirmatn font.
- The Tailwind Play engine is **vendored locally** at
  `assets/tailwind-play.js` (local-first: the dashboard renders fully
  styled with no network access; the font CSS remains CDN-linked with
  a system-ui fallback).
- The **بارگذاری مجدد داده‌ها** button refetches
  `state_summary.json` without a full page reload.
- The engine's local Docker stack deliberately uses ports
  18080 / 55432 / 15678 / 19000–19001, so 8080 is reserved for this
  dashboard and never collides.
- Edit `dashboard/state_summary.json` only through a deliberate snapshot
  capture. Update the HTML meta markers and warning together, then run
  `node dashboard/check-snapshot.mjs` before committing.

# Local Dashboard

Static Persian (RTL) status dashboard for the AI-First Online Business
Engine. Reads `dashboard/state_summary.json` at runtime (with an
embedded fallback object, so opening `index.html` directly via
`file://` still renders).

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
- Edit `dashboard/state_summary.json` to update the snapshot the
  dashboard displays; refresh from the button afterwards.

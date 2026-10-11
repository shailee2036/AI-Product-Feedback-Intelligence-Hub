# Feedback Hub web app

Next.js (App Router) frontend for the Product Feedback Intelligence Hub.

| Path | Purpose |
| --- | --- |
| `src/proxy.ts` | Refreshes the Supabase session and guards `/dashboard` |
| `src/app/login` | Email and password sign-in and sign-up (server actions) |
| `src/app/auth/callback` | Email confirmation handler |
| `src/app/dashboard` | Workspace view and GitHub repository registration |
| `src/lib/api` | Server-only, schema-validated client for the FastAPI backend |
| `src/lib/supabase` | Supabase clients for server components and the proxy |

## Environment

| Variable | Exposed to browser | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | yes | Supabase publishable key (RLS-protected by design) |
| `API_URL` | no | FastAPI base URL, used only on the server |
| `SITE_URL` | no | Public origin for email confirmation links |

Never put the Supabase secret key in this app.

## Scripts

```bash
npm run dev            # http://localhost:3100
npm run lint
npm run typecheck
npm run test:coverage  # 75% floor on src/lib
npm run build
```

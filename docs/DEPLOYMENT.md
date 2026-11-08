# Deployment

The public demo runs on free plans only: one Render web service built from `Dockerfile.render`, and one Neon PostgreSQL database.
The API serves the dashboard from the same origin, so no CORS setup is needed.

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Neon's **direct** connection string (pooling off), set only in the Render dashboard |
| `JWT_SECRET` | Long random value |
| `METRICS_TOKEN` | Long random value, because this service is public |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Administrator account |
| `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD` | Read-only account behind the demo button |
| `DEMO_USER_ROLE` | `viewer` |
| `DEMO_LOGIN_ENABLED` | `true` shows **View the demo** on the sign-in page |

Limits of the free plans:

- The service sleeps after 15 minutes without traffic. The next visit takes about a minute to wake it.
- The Neon database sleeps after 5 minutes idle and wakes on the next request. If a monthly free limit is reached it pauses
  until the next month. Startup uses PostgreSQL session advisory locks, which is why the direct connection is required.

`ANTHROPIC_API_KEY` is not set on the demo, so the advisor runs in its labeled rule-based fallback mode.

Docker Compose, Kubernetes and Terraform options are in [infrastructure/README.md](../infrastructure/README.md).

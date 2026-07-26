# Render deployment note for RC11

- `render.yaml` creates a new PostgreSQL database and the web service.
- `deploy/render_existing_postgres.yaml` creates only the web service and asks for a secret `DATABASE_URL`.
- Use the second file when the Render workspace already has its allowed free PostgreSQL instance.
- Run Alembic migrations against the chosen database before treating the deployment as ready.
- Staging defaults are for sanitized demo/UAT data only.

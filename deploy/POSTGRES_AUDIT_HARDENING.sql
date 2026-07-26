-- Execute after creating a dedicated application role.
-- Replace corvax_app with the actual least-privilege runtime role.
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_logs FROM corvax_app;
GRANT SELECT, INSERT ON TABLE audit_logs TO corvax_app;
GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO corvax_app;
-- Alembic/migration role must remain separate and may own schema changes.

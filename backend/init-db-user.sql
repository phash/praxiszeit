-- Create non-superuser app role for RLS enforcement
-- This script runs on first database initialization only
-- Password is set via: ALTER ROLE praxiszeit_app PASSWORD '<value>'
-- after running this script (see deployment docs)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'praxiszeit_app') THEN
        CREATE ROLE praxiszeit_app LOGIN;
    END IF;
END
$$;

-- Grant permissions on the database
GRANT CONNECT ON DATABASE praxiszeit TO praxiszeit_app;
GRANT USAGE ON SCHEMA public TO praxiszeit_app;

-- Grant table permissions (current and future tables)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO praxiszeit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO praxiszeit_app;

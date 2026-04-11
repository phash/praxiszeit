-- Create non-superuser app role for RLS enforcement.
-- This script runs on first database initialization only.
-- The password is applied by init-db-user.sh (same directory) which reads
-- APP_DB_PASSWORD from the container environment and executes
-- ALTER ROLE praxiszeit_app PASSWORD '...' after this script.
-- F-025: never leave this role with a NULL password in case the .sh step
-- is skipped — unlogin-able role fails closed rather than open.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'praxiszeit_app') THEN
        CREATE ROLE praxiszeit_app LOGIN NOINHERIT;
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

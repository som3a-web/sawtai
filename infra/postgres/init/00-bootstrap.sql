-- Bootstrap-only roles. Application objects are created exclusively by Alembic.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sawtai_app') THEN
        CREATE ROLE sawtai_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sawtai_breakglass') THEN
        CREATE ROLE sawtai_breakglass NOLOGIN;
    END IF;
END
$$;


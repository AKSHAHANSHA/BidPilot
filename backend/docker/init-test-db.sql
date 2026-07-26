-- Runs once when the PostgreSQL volume is first initialized.
-- Integration tests target a separate database so they can drop and rebuild the schema
-- without touching seeded demo data in `bidpilot`.
CREATE DATABASE bidpilot_test OWNER bidpilot;

-- Append-only enforcement (SQLite). PostgreSQL equivalents: migrations/postgres_extras.sql
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS journal_entries_no_update BEFORE UPDATE ON journal_entries BEGIN SELECT RAISE(ABORT, 'journal_entries are immutable; post a reversal'); END;
CREATE TRIGGER IF NOT EXISTS journal_entries_no_delete BEFORE DELETE ON journal_entries BEGIN SELECT RAISE(ABORT, 'journal_entries are immutable; post a reversal'); END;
CREATE TRIGGER IF NOT EXISTS journal_lines_no_update BEFORE UPDATE ON journal_lines BEGIN SELECT RAISE(ABORT, 'journal_lines are immutable; post a reversal'); END;
CREATE TRIGGER IF NOT EXISTS journal_lines_no_delete BEFORE DELETE ON journal_lines BEGIN SELECT RAISE(ABORT, 'journal_lines are immutable; post a reversal'); END;
CREATE TRIGGER IF NOT EXISTS custody_no_update BEFORE UPDATE ON custody_events BEGIN SELECT RAISE(ABORT, 'custody_events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS custody_no_delete BEFORE DELETE ON custody_events BEGIN SELECT RAISE(ABORT, 'custody_events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS credit_no_update BEFORE UPDATE ON credit_assessments BEGIN SELECT RAISE(ABORT, 'credit_assessments are immutable history'); END;
CREATE TRIGGER IF NOT EXISTS credit_no_delete BEFORE DELETE ON credit_assessments BEGIN SELECT RAISE(ABORT, 'credit_assessments are immutable history'); END;
CREATE TRIGGER IF NOT EXISTS inventory_no_update BEFORE UPDATE ON inventory_movements BEGIN SELECT RAISE(ABORT, 'inventory_movements are immutable'); END;
CREATE TRIGGER IF NOT EXISTS inventory_no_delete BEFORE DELETE ON inventory_movements BEGIN SELECT RAISE(ABORT, 'inventory_movements are immutable'); END;
CREATE TRIGGER IF NOT EXISTS transitions_no_update BEFORE UPDATE ON state_transitions BEGIN SELECT RAISE(ABORT, 'state_transitions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS transitions_no_delete BEFORE DELETE ON state_transitions BEGIN SELECT RAISE(ABORT, 'state_transitions are immutable'); END;

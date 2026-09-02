-- ============================================================
-- STEP 3: SEED DATA
-- ============================================================

-- Insert test accounts
INSERT INTO accounts (account_id, balance)
VALUES
    (1001, 10000.00),
    (1002, 5000.00),
    (1003, 2500.00)
ON CONFLICT (account_id) DO NOTHING;
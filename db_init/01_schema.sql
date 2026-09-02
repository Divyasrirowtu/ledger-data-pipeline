-- ============================================================
-- STEP 2: LEDGER DATABASE SCHEMA
-- ============================================================

-- Create accounts table
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    balance NUMERIC(15, 2) NOT NULL,
    
    CONSTRAINT accounts_balance_non_negative
        CHECK (balance >= 0)
);


-- Create ledger transactions table
CREATE TABLE IF NOT EXISTS ledger_transactions (
    tx_id VARCHAR(100) PRIMARY KEY,

    from_account_id INTEGER NOT NULL,

    to_account_id INTEGER NOT NULL,

    amount NUMERIC(15, 2) NOT NULL,

    status VARCHAR(20) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ledger_transactions_amount_positive
        CHECK (amount > 0),

    CONSTRAINT ledger_transactions_status_valid
        CHECK (status IN ('SUCCESS', 'FAILED')),

    CONSTRAINT ledger_transactions_from_account_fk
        FOREIGN KEY (from_account_id)
        REFERENCES accounts(account_id),

    CONSTRAINT ledger_transactions_to_account_fk
        FOREIGN KEY (to_account_id)
        REFERENCES accounts(account_id)
);
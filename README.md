# Ledger Data Pipeline

A containerized ledger data pipeline that processes pending financial transactions from CSV files, maintains account balances in PostgreSQL using ACID transactions, records transaction status as SUCCESS or FAILED, and archives processed CSV files to MinIO using Hive-style partitioning.

---

## 1. Project Overview

This project implements a simple financial ledger processing system with:

- PostgreSQL for account and transaction storage
- Python for CSV transaction processing
- ACID transactions for safe balance updates
- Rollback for invalid transactions
- SUCCESS and FAILED transaction tracking
- MinIO for processed CSV archival
- Docker Compose for infrastructure setup
- Environment variables for configuration

### Processing Flow

```text
                 pending_transactions.csv
                           |
                           v
                    Python Processor
                           |
                           v
                    Read CSV Records
                           |
                           v
                  Validate Transaction
                           |
                +----------+----------+
                |                     |
             VALID                 INVALID
                |                     |
                v                     v
        Begin DB Transaction       Rollback
                |                     |
        Deduct Sender Balance          |
                |                     |
        Add Receiver Balance            |
                |                     |
        Insert SUCCESS                  |
                |                     |
             COMMIT                     |
                |                     |
                +----------+------------+
                           |
                           v
                  Insert FAILED
                  for invalid rows
                           |
                           v
                  Archive CSV to
                       MinIO
                           |
                           v
        processed/year=YYYY/month=MM/day=DD/
2. Technologies Used
Technology	Purpose
Python	Transaction processing
PostgreSQL	Ledger database
Docker	Containerization
Docker Compose	Infrastructure orchestration
MinIO	Object storage / CSV archival
boto3	S3-compatible MinIO access
psycopg2	PostgreSQL connection
python-dotenv	Environment configuration
3. Project Structure
ledger-data-pipeline/
│
├── .env
├── .env.example
├── .gitignore
├── docker-compose.yml
├── processor.py
├── requirements.txt
├── pending_transactions.csv
├── acid_test.csv
├── invalid_account.csv
│
├── db_init/
│   ├── 01_schema.sql
│   └── 02_seed.sql
│
├── data/
│
└── logs/

.env contains local configuration and credentials and must not be committed to GitHub.

4. Step 1 — Docker Infrastructure

Docker Compose is used to run PostgreSQL and MinIO.

The project contains two services:

PostgreSQL
PostgreSQL 15
Port: 5432
Database: ledger_db
User: ledger_user
MinIO
S3-compatible object storage
API port: 9000
Web console: 9001
Start the services

Run:

docker compose up -d

Check the containers:

docker compose ps

Expected services:

ledger-postgres
ledger-minio
Stop the services
docker compose down
Stop and remove database volumes

Use this only when you want a fresh database initialization:

docker compose down -v

This removes the PostgreSQL Docker volume and causes the initialization SQL scripts to run again when the containers are recreated.

5. PostgreSQL Database

PostgreSQL is initialized automatically using:

db_init/
├── 01_schema.sql
└── 02_seed.sql

Docker mounts this directory into:

/docker-entrypoint-initdb.d
6. Step 2 — Database Schema

The database contains two main tables.

Accounts Table
CREATE TABLE accounts (
    account_id INTEGER PRIMARY KEY,
    balance NUMERIC(15, 2) NOT NULL,
    CHECK (balance >= 0)
);

The balance >= 0 constraint prevents an account from having a negative balance.

Ledger Transactions Table

The transaction table contains:

Transaction ID
Sender account
Receiver account
Amount
Transaction status
Creation timestamp

Important constraints include:

tx_id                 PRIMARY KEY
from_account_id       FOREIGN KEY
to_account_id         FOREIGN KEY
amount                CHECK (amount > 0)
status                SUCCESS or FAILED
7. Step 3 — Seed Data

The database is initialized with three accounts.

Account 1001 → 10000.00
Account 1002 →  5000.00
Account 1003 →  2500.00

These accounts are used for transaction testing.

The seed file is:

db_init/02_seed.sql

Example:

INSERT INTO accounts (account_id, balance)
VALUES
    (1001, 10000.00),
    (1002, 5000.00),
    (1003, 2500.00)
ON CONFLICT (account_id) DO NOTHING;
Verify Seed Data

Connect to PostgreSQL:

docker exec -it ledger-postgres psql -U ledger_user -d ledger_db

Run:

SELECT * FROM accounts ORDER BY account_id;

Expected:

 account_id | balance
------------+----------
 1001       | 10000.00
 1002       |  5000.00
 1003       |  2500.00
8. Step 4 — Environment Configuration

Configuration is stored in environment variables.

The local .env file contains:

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ledger_user
POSTGRES_PASSWORD=ledger_password
POSTGRES_DB=ledger_db

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123

MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=ledger-archive

For sharing the project, use .env.example.

Example:

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_postgres_user
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=your_database_name

MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=your_minio_access_key
MINIO_SECRET_KEY=your_minio_secret_key
MINIO_BUCKET=ledger-archive
Security

The .env file is excluded from Git using:

.env

in .gitignore.

Never commit real production credentials.

9. Step 5 — Python CSV Processor

The main processing application is:

processor.py

The processor:

Reads a CSV file
Connects to PostgreSQL
Validates each transaction
Checks account existence
Checks sufficient balance
Deducts money from sender
Adds money to receiver
Records SUCCESS
Rolls back invalid transactions
Records FAILED
Archives the processed CSV to MinIO
10. CSV Input Format

The processor accepts a CSV path as a command-line argument.

Example:

transaction_id,sender,receiver,amount
TX001,1001,1002,1000.00
TX002,1003,1002,5000.00

The required information is:

transaction_id
sender
receiver
amount

The processor also supports common alternatives such as:

tx_id
from_account_id
to_account_id
11. Running the Processor

The default CSV filename is:

pending_transactions.csv

Run:

python processor.py

Or provide a CSV path:

python processor.py pending_transactions.csv

Example:

python processor.py acid_test.csv
12. Step 6 — ACID Transaction Processing

Each transaction is processed using an explicit PostgreSQL transaction.

The processing sequence is:

BEGIN
  |
  +-- Lock sender/receiver rows
  |
  +-- Check accounts
  |
  +-- Check balance
  |
  +-- Deduct sender balance
  |
  +-- Add receiver balance
  |
  +-- Insert SUCCESS
  |
COMMIT

If any operation fails:

Exception
    |
    v
ROLLBACK
    |
    v
No balance changes
    |
    v
Record FAILED

This ensures that a failed transaction does not partially update the account balances.

13. Valid Transaction Example

Consider:

Transaction: TX001
Sender:      1001
Receiver:    1002
Amount:      1000.00

Initial balances:

1001 = 10000.00
1002 =  5000.00

After successful processing:

1001 = 9000.00
1002 = 6000.00

Ledger status:

TX001 → SUCCESS
14. Invalid Transaction Example

Consider:

Transaction: TX002
Sender:      1003
Receiver:    1002
Amount:      5000.00

Account 1003 has:

2500.00

The transaction requires:

5000.00

Therefore the transaction fails.

The processor performs:

Insufficient balance
        |
        v
ROLLBACK
        |
        v
No balance deducted
        |
        v
Record FAILED

Account 1003 remains:

2500.00
15. SUCCESS and FAILED Records

The ledger_transactions table stores transaction status.

Example:

tx_id  | from | to   | amount  | status
-------+------+------+---------+--------
TX001  | 1001 | 1002 | 1000.00 | SUCCESS
TX002  | 1003 | 1002 | 5000.00 | FAILED

This provides a persistent record of both successful and unsuccessful transactions.

16. Verify Transactions

Connect to PostgreSQL:

docker exec -it ledger-postgres psql -U ledger_user -d ledger_db

Run:

SELECT
    tx_id,
    from_account_id,
    to_account_id,
    amount,
    status,
    created_at
FROM ledger_transactions
ORDER BY created_at;
17. Verify Account Balances

Run:

SELECT
    account_id,
    balance
FROM accounts
ORDER BY account_id;

For a failed transaction, the sender's balance must remain unchanged.

18. Step 7 — MinIO CSV Archival

After all transactions in the CSV are processed, the CSV file is uploaded to MinIO.

The MinIO bucket is:

ledger-archive

The processor uses boto3 to communicate with MinIO through its S3-compatible API.

19. Hive-Style Archive Path

Processed files are stored using:

processed/year=YYYY/month=MM/day=DD/<filename>.csv

Example:

processed/
└── year=2026/
    └── month=09/
        └── day=04/
            └── pending_transactions.csv

This structure allows files to be organized using date-based partitions.

20. Access MinIO Console

Open:

http://localhost:9001

Login using the credentials configured in .env.

For the development configuration:

Username: minioadmin
Password: minioadmin123

Open:

Buckets
    |
    +-- ledger-archive
          |
          +-- processed
                |
                +-- year=YYYY
21. MinIO API

The MinIO S3-compatible API is available at:

http://localhost:9000

The Python processor uses:

MINIO_ENDPOINT=http://localhost:9000
22. Python Dependencies

The project uses the following Python libraries:

psycopg2-binary
python-dotenv
boto3

Install them using:

pip install -r requirements.txt
23. Complete Testing
Start Docker
docker compose up -d
Verify containers
docker compose ps
Verify database
docker exec -it ledger-postgres psql -U ledger_user -d ledger_db

Then:

SELECT * FROM accounts ORDER BY account_id;

Exit:

\q
Process CSV
python processor.py pending_transactions.csv
Verify ledger
docker exec -it ledger-postgres psql -U ledger_user -d ledger_db
SELECT
    tx_id,
    from_account_id,
    to_account_id,
    amount,
    status
FROM ledger_transactions
ORDER BY created_at;
Verify balances
SELECT * FROM accounts ORDER BY account_id;
Verify MinIO

Open:

http://localhost:9001

Check:

ledger-archive
    └── processed
        └── year=YYYY
            └── month=MM
                └── day=DD
                    └── CSV file
24. Git Commands

Initialize the repository:

git init

Check status:

git status

Add files:

git add .

Commit:

git commit -m "Implement ledger data pipeline"

Push:

git push
25. Security

The following file contains local credentials:

.env

It must not be committed.

The project provides:

.env.example

with placeholder values for users to configure their own environment.

The .gitignore contains:

.env
26. Requirements Implemented
Requirement	Implementation	Status
PostgreSQL Docker service	docker-compose.yml	Complete
MinIO Docker service	docker-compose.yml	Complete
Database schema	db_init/01_schema.sql	Complete
Seed data	db_init/02_seed.sql	Complete
CSV transaction processing	processor.py	Complete
ACID transaction handling	PostgreSQL transactions	Complete
Rollback on failure	conn.rollback()	Complete
SUCCESS/FAILED status	ledger_transactions	Complete
MinIO archival	boto3	Complete
Hive-style partitioning	processed/year=/month=/day=	Complete
Environment configuration	.env / .env.example	Complete
Python dependencies	requirements.txt	Complete
27. Expected Final Architecture
                         +-----------------------+
                         | pending_transactions  |
                         |        .csv           |
                         +-----------+-----------+
                                     |
                                     v
                         +-----------------------+
                         |   Python Processor    |
                         |     processor.py      |
                         +-----------+-----------+
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
          +-------------------+              +-------------------+
          |    PostgreSQL     |              |      MinIO        |
          |                   |              |                   |
          |    accounts       |              | ledger-archive    |
          |                   |              |                   |
          | ledger_transactions|             | processed/        |
          +-------------------+              | year=/month=/day= |
                                             +-------------------+
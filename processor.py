import csv
import os
import sys
from datetime import datetime
from decimal import Decimal

import boto3
import psycopg2
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()


DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "ledger_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ledger_password")
DB_NAME = os.getenv("POSTGRES_DB", "ledger_db")

MINIO_ENDPOINT = os.getenv(
    "MINIO_ENDPOINT",
    "http://localhost:9000"
)

MINIO_ACCESS_KEY = os.getenv(
    "MINIO_ACCESS_KEY",
    "minioadmin"
)

MINIO_SECRET_KEY = os.getenv(
    "MINIO_SECRET_KEY",
    "minioadmin123"
)

MINIO_BUCKET = os.getenv(
    "MINIO_BUCKET",
    "ledger-archive"
)

def get_connection():
    """Create a PostgreSQL database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def process_transaction(conn, tx_id, from_account_id, to_account_id, amount):
    """
    Process one transaction using an explicit database transaction.
    """

    try:
        with conn.cursor() as cursor:

            # Lock sender and receiver rows.
            cursor.execute(
                """
                SELECT account_id, balance
                FROM accounts
                WHERE account_id IN (%s, %s)
                FOR UPDATE
                """,
                (from_account_id, to_account_id),
            )

            accounts = {
                row[0]: row[1]
                for row in cursor.fetchall()
            }

            # Validate accounts
            if from_account_id not in accounts:
                raise ValueError(
                    f"Sender account {from_account_id} does not exist"
                )

            if to_account_id not in accounts:
                raise ValueError(
                    f"Receiver account {to_account_id} does not exist"
                )

            # Validate transaction amount
            if amount <= 0:
                raise ValueError("Transaction amount must be greater than zero")

            sender_balance = accounts[from_account_id]

            # Check sufficient balance
            if sender_balance < amount:
                raise ValueError(
                    f"Insufficient balance in account {from_account_id}"
                )

            # Deduct from sender
            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance - %s
                WHERE account_id = %s
                """,
                (amount, from_account_id),
            )

            # Add to receiver
            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance + %s
                WHERE account_id = %s
                """,
                (amount, to_account_id),
            )

            # Record successful transaction
            cursor.execute(
                """
                INSERT INTO ledger_transactions
                (
                    tx_id,
                    from_account_id,
                    to_account_id,
                    amount,
                    status
                )
                VALUES (%s, %s, %s, %s, 'SUCCESS')
                """,
                (
                    tx_id,
                    from_account_id,
                    to_account_id,
                    amount,
                ),
            )

        # Commit the complete transaction
        conn.commit()

        print(
            f"SUCCESS: {tx_id} | "
            f"{from_account_id} -> {to_account_id} | "
            f"{amount}"
        )

    except Exception as error:

        # Roll back ALL balance changes
        conn.rollback()

        print(
            f"FAILED: {tx_id} | {error}"
        )

        # Record FAILED status in a new transaction
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ledger_transactions
                    (
                        tx_id,
                        from_account_id,
                        to_account_id,
                        amount,
                        status
                    )
                    VALUES (%s, %s, %s, %s, 'FAILED')
                    """,
                    (
                        tx_id,
                        from_account_id,
                        to_account_id,
                        amount,
                    ),
                )

            conn.commit()

        except Exception as ledger_error:
            conn.rollback()
            print(
                f"ERROR recording FAILED transaction "
                f"{tx_id}: {ledger_error}"
            )


def read_csv(csv_path):
    """Read transactions from CSV."""

    with open(csv_path, "r", newline="", encoding="utf-8") as file:

        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("CSV file has no header")

        print("CSV columns:", reader.fieldnames)

        for row in reader:

            # Support common column-name variations
            tx_id = (
                row.get("tx_id")
                or row.get("transaction_id")
                or row.get("transaction_id".lower())
                or row.get("id")
            )

            sender = (
                row.get("from_account_id")
                or row.get("sender")
                or row.get("from")
            )

            receiver = (
                row.get("to_account_id")
                or row.get("receiver")
                or row.get("to")
            )

            amount = row.get("amount")

            if not tx_id:
                raise ValueError("Missing transaction ID")

            if not sender:
                raise ValueError(
                    f"Missing sender for transaction {tx_id}"
                )

            if not receiver:
                raise ValueError(
                    f"Missing receiver for transaction {tx_id}"
                )

            if not amount:
                raise ValueError(
                    f"Missing amount for transaction {tx_id}"
                )

            yield (
                tx_id,
                int(sender),
                int(receiver),
                Decimal(amount),
            )


def main():

    # CSV path can be supplied as a command-line argument.
    # Otherwise use pending_transactions.csv.
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = "pending_transactions.csv"

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    print(f"Processing CSV: {csv_path}")

    conn = None

    try:
        conn = get_connection()

        print("Connected to PostgreSQL")

        for transaction in read_csv(csv_path):

            process_transaction(
                conn,
                transaction[0],
                transaction[1],
                transaction[2],
                transaction[3],
            )

        print("Transaction processing completed")

    except Exception as error:

        print(f"ERROR: {error}")
        sys.exit(1)

    finally:

        if conn:
            conn.close()
            print("Database connection closed")


if __name__ == "__main__":
    def archive_csv_to_minio(csv_path):
    """
    Upload the processed CSV file to MinIO using
    Hive-style partitioning:
    processed/year=YYYY/month=MM/day=DD/
    """

    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
        )

        # Check whether bucket exists
        try:
            s3_client.head_bucket(
                Bucket=MINIO_BUCKET
            )

        except ClientError:
            # Create bucket if it doesn't exist
            s3_client.create_bucket(
                Bucket=MINIO_BUCKET
            )

        now = datetime.now()

        filename = os.path.basename(csv_path)

        object_key = (
            f"processed/"
            f"year={now.year}/"
            f"month={now.month:02d}/"
            f"day={now.day:02d}/"
            f"{filename}"
        )

        s3_client.upload_file(
            csv_path,
            MINIO_BUCKET,
            object_key
        )

        print(
            f"ARCHIVED: "
            f"s3://{MINIO_BUCKET}/{object_key}"
        )

    except Exception as error:
        print(
            f"ERROR: Could not archive CSV to MinIO: "
            f"{error}"
        )
        raise
    main()
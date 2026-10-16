import os

# Every test app gets a fresh in-memory database, never the dev database in instance/.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SMS_PROVIDER"] = "console"

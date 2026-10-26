import os
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import database_settings


class DatabaseConfigTests(unittest.TestCase):
    def test_postgres_uses_small_pool_and_verified_ssl(self):
        with patch.dict(os.environ, {"DATABASE_SSL": "verify-full", "DATABASE_SSL_CA_FILE": ""}):
            url, settings = database_settings("postgresql://user:password@pooler.supabase.com:5432/postgres?sslmode=require")
        self.assertEqual(url.drivername, "postgresql+asyncpg")
        self.assertNotIn("sslmode", url.query)
        self.assertEqual((settings["pool_size"], settings["max_overflow"]), (2, 0))
        self.assertTrue(settings["connect_args"]["ssl"].check_hostname)
        self.assertEqual(settings["connect_args"]["ssl"].verify_mode, ssl.CERT_REQUIRED)

    def test_remote_ssl_cannot_be_disabled(self):
        with patch.dict(os.environ, {"DATABASE_SSL": "disable"}), self.assertRaises(RuntimeError):
            database_settings("postgresql://user:password@pooler.supabase.com/postgres")

    def test_production_cannot_silently_use_sqlite(self):
        with patch.dict(os.environ, {"NODE_ENV": "production"}), self.assertRaises(RuntimeError):
            database_settings("sqlite+aiosqlite:///./dev.db")

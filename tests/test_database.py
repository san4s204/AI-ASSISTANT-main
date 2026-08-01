from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.services import db, token_wallet


class DatabaseMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_patch = patch.object(db, "DB_PATH", self.db_path)
        self.wallet_patch = patch.object(token_wallet, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.wallet_patch.start()

    async def asyncTearDown(self) -> None:
        self.wallet_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    async def test_clean_database_contains_all_runtime_tables(self) -> None:
        await db.ensure_database()
        await token_wallet.ensure_tables()

        with sqlite3.connect(self.db_path) as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

        self.assertTrue(
            {
                "users",
                "user_terms",
                "user_prefs",
                "google_tokens",
                "chat_memory",
                "token_wallets",
                "token_tx",
            }.issubset(names)
        )

    async def test_wallet_resets_spend_when_month_changes(self) -> None:
        await token_wallet.ensure_tables()
        current_start, current_end = token_wallet._month_bounds()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO token_wallets(
                    user_id, period_start, period_end,
                    allowance_tokens, spent_tokens, status
                ) VALUES(?, ?, ?, ?, ?, 'active')
                """,
                (42, "2000-01-01", "2000-02-01", 1000, 900),
            )

        await token_wallet.ensure_current_wallet(42, 2000)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT period_start, period_end, allowance_tokens, spent_tokens
                FROM token_wallets WHERE user_id=42
                """
            ).fetchone()

        self.assertEqual(row, (current_start, current_end, 2000, 0))

    async def test_wallet_preserves_spend_inside_current_month(self) -> None:
        await token_wallet.ensure_tables()
        await token_wallet.ensure_current_wallet(42, 1000)
        self.assertTrue(await token_wallet.debit(42, 250))

        await token_wallet.ensure_current_wallet(42, 2000)
        allowance, spent, remaining = await token_wallet.get_balance(42)

        self.assertEqual((allowance, spent, remaining), (2000, 250, 1750))


if __name__ == "__main__":
    unittest.main()

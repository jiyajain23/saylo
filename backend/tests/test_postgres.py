"""Opt-in real PostgreSQL migrations/RLS tests on an empty, loopback-only test DB.

PG_TEST_DATABASE_URL=postgresql+asyncpg://.../saylo_test_phase2
Every test rolls back its transaction; no production URL or Supabase project is used.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from migrations.runner import upgrade, check_schema

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


@unittest.skipUnless(os.environ.get("PG_TEST_DATABASE_URL"), "set PG_TEST_DATABASE_URL to an empty local saylo_test_* database")
class PostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = make_url(os.environ["PG_TEST_DATABASE_URL"])
        if url.host not in ("localhost", "127.0.0.1", "::1") or not (url.database or "").startswith("saylo_test_"):
            raise RuntimeError("Tests require a loopback-only database named saylo_test_*")
        self.engine = create_async_engine(url.set(drivername="postgresql+asyncpg"), hide_parameters=True)
        self.conn = await self.engine.connect()
        self.tx = await self.conn.begin()
        try:
            tables = await self.conn.run_sync(lambda conn: inspect(conn).get_table_names())
            if tables:
                raise RuntimeError("PostgreSQL test database must be empty")
            # Minimal Supabase Auth contract, only inside this rollback transaction.
            for role in ("anon", "authenticated"):
                exists = await self.conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
                if not exists:
                    await self.conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
            await self.conn.execute(text("CREATE SCHEMA auth"))
            await self.conn.execute(text("CREATE TABLE auth.users (id UUID PRIMARY KEY)"))
            await self.conn.execute(text("""CREATE FUNCTION auth.uid() RETURNS UUID LANGUAGE SQL STABLE AS
                'SELECT nullif(current_setting(''request.jwt.claim.sub'', true), '''')::uuid'"""))
            await self.conn.execute(text("GRANT USAGE ON SCHEMA auth, public TO authenticated, anon"))
            await self.conn.run_sync(upgrade)
            for user, session in ((ALICE, "alice"), (BOB, "bob")):
                await self.conn.execute(text("INSERT INTO auth.users (id) VALUES (CAST(:id AS UUID))"), {"id": user})
                await self.conn.execute(text('INSERT INTO public."User" (id) VALUES (CAST(:id AS UUID))'), {"id": user})
                await self.conn.execute(text('INSERT INTO public."Session" (id, "userId") VALUES (:session, CAST(:id AS UUID))'), {"session": session, "id": user})
                await self.conn.execute(text('INSERT INTO public."TranscriptSegment" (id, "sessionId", speaker, text) VALUES (:id, :id, \'user\', \'private answer\')'), {"id": session})
                await self.conn.execute(text('INSERT INTO public."AnalysisResult" (id, "sessionId", confidence, voice) VALUES (:id, :id, .8, \'{"available": true}\')'), {"id": session})
        except BaseException:
            await self.tx.rollback()
            await self.conn.close()
            await self.engine.dispose()
            raise

    async def asyncTearDown(self):
        await self.tx.rollback()
        await self.conn.close()
        await self.engine.dispose()

    async def test_migration_repeat_preserves_data_and_indexes(self):
        await self.conn.run_sync(upgrade)
        await self.conn.run_sync(check_schema)
        self.assertEqual(await self.conn.scalar(text('SELECT count(*) FROM public."Session"')), 2)
        indexes = await self.conn.run_sync(lambda conn: inspect(conn).get_indexes("Session"))
        self.assertTrue({"ix_session_owner_created", "ix_session_owner_status"} <= {i["name"] for i in indexes})
        self.assertEqual(await self.conn.scalar(text('SELECT voice FROM public."AnalysisResult" LIMIT 1')), {"available": True})

    async def test_rls_filters_parent_transcripts_and_results_for_both_users(self):
        await self.conn.execute(text("SET LOCAL ROLE authenticated"))
        for user, session in ((ALICE, "alice"), (BOB, "bob")):
            await self.conn.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {"id": user})
            for table in ("Session", "TranscriptSegment", "AnalysisResult"):
                rows = (await self.conn.execute(text(f'SELECT id FROM public."{table}"'))).scalars().all()
                self.assertEqual(rows, [session])
        can_insert = await self.conn.scalar(text("SELECT has_table_privilege(current_user, 'public.\"AnalysisResult\"', 'INSERT')"))
        self.assertFalse(can_insert)

    async def test_auth_user_deletion_cascades_only_that_owner(self):
        await self.conn.execute(text("DELETE FROM auth.users WHERE id = CAST(:id AS UUID)"), {"id": ALICE})
        for table in ("Session", "TranscriptSegment", "AnalysisResult"):
            rows = (await self.conn.execute(text(f'SELECT id FROM public."{table}"'))).scalars().all()
            self.assertEqual(rows, ["bob"])

    async def test_anon_has_no_access(self):
        await self.conn.execute(text("SET LOCAL ROLE anon"))
        self.assertFalse(await self.conn.scalar(text("SELECT has_table_privilege(current_user, 'public.\"Session\"', 'SELECT')")))

    async def test_import_keeps_original_scores_and_assigns_explicit_owner(self):
        from datetime import datetime
        from migrations.import_sqlite import import_rows
        timestamp = datetime(2026, 1, 1)
        data = {
            "Session": [{"id": "imported", "status": "READY", "createdAt": timestamp}],
            "TranscriptSegment": [{"id": "imported-turn", "sessionId": "imported", "speaker": "user", "text": "original answer"}],
            "AnalysisResult": [{"id": "imported-result", "sessionId": "imported", "confidence": .91,
                                "voice": {"available": True}, "scoring_version": "2"}],
        }
        await import_rows(self.conn, data, ALICE)
        row = (await self.conn.execute(text('SELECT "userId", "createdAt" FROM public."Session" WHERE id = \'imported\''))).one()
        self.assertEqual(str(row[0]), ALICE)
        self.assertEqual(row[1], timestamp)
        self.assertEqual(await self.conn.scalar(text('SELECT confidence FROM public."AnalysisResult" WHERE id = \'imported-result\'')), .91)

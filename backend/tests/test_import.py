import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession
from models.schemas import Base, Session, AnalysisResult, TranscriptSegment
from migrations.import_sqlite import read_snapshot

OWNER = "11111111-1111-4111-8111-111111111111"


class SQLiteImportTests(unittest.TestCase):
    def test_preview_preserves_source_and_nested_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.db"
            engine = create_engine("sqlite:///" + path.as_posix())
            Base.metadata.create_all(engine)
            with DBSession(engine) as db:
                db.add(Session(id="old", status="READY"))
                db.flush()
                db.add(TranscriptSegment(id="turn", sessionId="old", speaker="user", text="original words"))
                db.add(AnalysisResult(id="analysis", sessionId="old", confidence=.91, voice={"available": True}, scoring_version="2"))
                db.commit()
            engine.dispose()
            original = path.read_bytes()
            rows = read_snapshot(path, OWNER)
            self.assertEqual(path.read_bytes(), original)
            self.assertIsNone(rows["Session"][0]["userId"])
            self.assertEqual(rows["AnalysisResult"][0]["confidence"], .91)
            self.assertEqual(rows["AnalysisResult"][0]["voice"], {"available": True})
            self.assertEqual(rows["TranscriptSegment"][0]["text"], "original words")

    def test_missing_source_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            with self.assertRaises(ValueError):
                read_snapshot(path, OWNER)
            self.assertFalse(path.exists())

-- New Supabase PostgreSQL database only. Existing SQLite is left untouched.
CREATE TABLE public."User" (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR UNIQUE,
    name VARCHAR,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public."Session" (
    id VARCHAR PRIMARY KEY,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR NOT NULL DEFAULT 'LIVE',
    scenario VARCHAR NOT NULL DEFAULT 'INTERVIEW',
    title VARCHAR,
    persona VARCHAR NOT NULL DEFAULT 'DEFAULT',
    "pressureLevel" INTEGER NOT NULL DEFAULT 0,
    "userId" UUID NOT NULL REFERENCES public."User"(id) ON DELETE CASCADE,
    "contextRaw" TEXT,
    "contextJson" JSON
);
CREATE TABLE public."TranscriptSegment" (
    id VARCHAR PRIMARY KEY,
    "sessionId" VARCHAR NOT NULL REFERENCES public."Session"(id) ON DELETE CASCADE,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    speaker VARCHAR NOT NULL,
    text TEXT NOT NULL,
    "audioStartSeconds" FLOAT,
    "audioEndSeconds" FLOAT
);
CREATE TABLE public."AnalysisResult" (
    id VARCHAR PRIMARY KEY,
    "sessionId" VARCHAR NOT NULL UNIQUE REFERENCES public."Session"(id) ON DELETE CASCADE,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "speechMetrics" JSON,
    "nlpMetrics" JSON,
    alignment JSON,
    confidence FLOAT,
    highlights JSON,
    strengths JSON,
    weaknesses JSON,
    suggestions JSON,
    voice JSON,
    emotion JSON,
    vision JSON,
    jobs JSON,
    errors JSON,
    insights JSON,
    scoring_version VARCHAR
);
CREATE INDEX ix_session_owner_created ON public."Session" ("userId", "createdAt");
CREATE INDEX ix_session_owner_status ON public."Session" ("userId", status);
CREATE INDEX ix_segment_session_created ON public."TranscriptSegment" ("sessionId", "createdAt");
ALTER TABLE public."User" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."Session" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."TranscriptSegment" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."AnalysisResult" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public."User", public."Session", public."TranscriptSegment", public."AnalysisResult" FROM anon, authenticated;
GRANT SELECT ON public."User", public."Session", public."TranscriptSegment", public."AnalysisResult" TO authenticated;
CREATE POLICY user_self_read ON public."User" FOR SELECT TO authenticated USING (id = (SELECT auth.uid()));
CREATE POLICY session_owner_read ON public."Session" FOR SELECT TO authenticated USING ("userId" = (SELECT auth.uid()));
CREATE POLICY transcript_owner_read ON public."TranscriptSegment" FOR SELECT TO authenticated USING (
    EXISTS (SELECT 1 FROM public."Session" s WHERE s.id = "sessionId" AND s."userId" = (SELECT auth.uid()))
);
CREATE POLICY analysis_owner_read ON public."AnalysisResult" FOR SELECT TO authenticated USING (
    EXISTS (SELECT 1 FROM public."Session" s WHERE s.id = "sessionId" AND s."userId" = (SELECT auth.uid()))
);

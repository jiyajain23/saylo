ALTER TABLE public."Session" ADD COLUMN "audioBytes" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public."Session" ADD COLUMN "liveHeartbeatAt" TIMESTAMP;
ALTER TABLE public."Session" ADD COLUMN "failureCode" VARCHAR;
CREATE TABLE public."AnalysisJob" (
 id VARCHAR PRIMARY KEY,
 "sessionId" VARCHAR NOT NULL UNIQUE REFERENCES public."Session"(id) ON DELETE CASCADE,
 "userId" UUID NOT NULL REFERENCES public."User"(id) ON DELETE CASCADE,
 status VARCHAR NOT NULL DEFAULT 'QUEUED',
 attempts INTEGER NOT NULL DEFAULT 0,
 "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 "updatedAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 "availableAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 "expiresAt" TIMESTAMP NOT NULL,
 "leaseToken" VARCHAR,
 "leaseExpiresAt" TIMESTAMP,
 "heartbeatAt" TIMESTAMP,
 "audioKey" VARCHAR,
 "audioBytes" INTEGER NOT NULL DEFAULT 0,
 "audioDeletedAt" TIMESTAMP,
 "errorCode" VARCHAR,
 CHECK (status IN ('UPLOADING', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);
CREATE INDEX ix_job_status_available ON public."AnalysisJob" (status, "availableAt");
CREATE INDEX ix_job_owner_created ON public."AnalysisJob" ("userId", "createdAt");
CREATE UNIQUE INDEX ix_job_one_active_owner ON public."AnalysisJob" ("userId") WHERE status IN ('UPLOADING', 'QUEUED', 'RUNNING');
ALTER TABLE public."AnalysisJob" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public."AnalysisJob" FROM anon, authenticated;
GRANT SELECT ON public."AnalysisJob" TO authenticated;
CREATE POLICY job_owner_read ON public."AnalysisJob" FOR SELECT TO authenticated USING ("userId" = (SELECT auth.uid()));
-- No anonymous or end-user Storage policies: only server keys access this bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('saylo-audio', 'saylo-audio', false, 30000000, ARRAY['application/octet-stream'])
ON CONFLICT (id) DO NOTHING;

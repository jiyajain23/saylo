-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_Session" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'LIVE',
    "scenario" TEXT NOT NULL DEFAULT 'INTERVIEW',
    "title" TEXT,
    "persona" TEXT NOT NULL DEFAULT 'DEFAULT',
    "pressureLevel" INTEGER NOT NULL DEFAULT 0,
    "userId" TEXT,
    "contextRaw" TEXT,
    "contextJson" JSONB,
    CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_Session" ("contextJson", "contextRaw", "createdAt", "id", "scenario", "status", "title", "updatedAt", "userId") SELECT "contextJson", "contextRaw", "createdAt", "id", "scenario", "status", "title", "updatedAt", "userId" FROM "Session";
DROP TABLE "Session";
ALTER TABLE "new_Session" RENAME TO "Session";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

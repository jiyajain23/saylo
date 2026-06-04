import { PrismaClient } from "@prisma/client";

const isDev = process.env.NODE_ENV !== "production";

/**
 * Singleton Prisma client.
 * Logs queries in development; only errors/warnings in production.
 */
export const prisma = new PrismaClient({
  log: isDev
    ? [
        { emit: "stdout", level: "query" },
        { emit: "stdout", level: "info" },
        { emit: "stdout", level: "warn" },
        { emit: "stdout", level: "error" }
      ]
    : [
        { emit: "stdout", level: "warn" },
        { emit: "stdout", level: "error" }
      ]
});

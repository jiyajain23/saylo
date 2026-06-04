import { z } from "zod";
import { normalizeScenario, type Scenario } from "./scenarios.js";

const ContextInputSchema = z.object({
  scenario: z.string().optional(),
  resumeText: z.string().trim().max(30_000).optional(),
  jobDescription: z.string().trim().max(30_000).optional(),
  topicNotes: z.string().trim().max(30_000).optional(),
  freeText: z.string().trim().max(30_000).optional(),
  text: z.string().trim().max(30_000).optional()
});

export type StructuredContext = {
  scenario: Scenario;
  role?: string;
  company?: string;
  level?: string;
  audience?: string;
  objective?: string;
  skills?: string[];
  projects?: string[];
  focusAreas?: string[];
  candidateBackground?: string[];
  rawSummary?: string;
  sources: {
    resume?: string;
    jobDescription?: string;
    topicNotes?: string;
    freeText?: string;
  };
};

function uniq(items: string[]) {
  return Array.from(new Set(items.map((s) => s.trim()).filter(Boolean)));
}

function firstLineValue(text: string, labels: string[]) {
  const labelPattern = labels.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const match = text.match(new RegExp(`^(?:${labelPattern})\\s*:\\s*(.+)$`, "im"));
  return match?.[1]?.trim();
}

function splitTerms(text: string, patterns: RegExp[]) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  return uniq(
    lines
      .filter((line) => patterns.some((pattern) => pattern.test(line)))
      .flatMap((line) =>
        line
          .replace(/^.*?:\s*/g, "")
          .split(/[,/|;]+/g)
          .map((term) => term.trim())
      )
  );
}

function compact(parts: Array<string | undefined>) {
  return parts.filter((part): part is string => Boolean(part && part.trim())).join("\n\n");
}

export function buildStructuredContext(input: unknown): {
  contextRaw: string;
  contextJson: StructuredContext;
} {
  const body = ContextInputSchema.parse(input);
  const scenario = normalizeScenario(body.scenario);
  const sources = {
    resume: body.resumeText || undefined,
    jobDescription: body.jobDescription || undefined,
    topicNotes: body.topicNotes || undefined,
    freeText: body.freeText || body.text || undefined
  };
  const text = compact([sources.resume, sources.jobDescription, sources.topicNotes, sources.freeText]);
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const role =
    firstLineValue(text, ["role", "target role", "position"]) ||
    text.match(/(product manager|software engineer|data analyst|designer|founder|sales|consultant)(?:\s+(intern|new grad|junior|senior|lead))?/i)?.[0];

  const company =
    firstLineValue(text, ["company", "organization"]) ||
    text.match(/at\s+([A-Z][\w&.-]{1,})/g)?.[0]?.replace(/^at\s+/i, "").trim();

  const audience = firstLineValue(text, ["audience", "stakeholders", "listener"]);
  const objective = firstLineValue(text, ["objective", "goal", "purpose", "meeting goal", "pitch goal"]);

  const skills = splitTerms(text, [/skills/i, /tech/i, /stack/i, /tools/i]);
  const projects = uniq(lines.filter((line) => /project|built|launched|shipped/i.test(line)).slice(0, 8));
  const focusAreas = splitTerms(text, [/focus/i, /looking for/i, /evaluate/i, /assessment/i, /areas/i]);
  const candidateBackground = uniq(
    lines.filter((line) => /experience|background|worked|led|built|managed|intern/i.test(line)).slice(0, 8)
  );

  const contextJson: StructuredContext = {
    scenario,
    role: role?.trim(),
    company: company?.trim(),
    audience: audience?.trim(),
    objective: objective?.trim(),
    skills: skills.length ? skills : undefined,
    projects: projects.length ? projects : undefined,
    focusAreas: focusAreas.length ? focusAreas : undefined,
    candidateBackground: candidateBackground.length ? candidateBackground : undefined,
    rawSummary: lines.slice(0, 10).join(" | "),
    sources
  };

  return { contextRaw: text, contextJson };
}

export function formatContextForPrompt(ctx: StructuredContext | null | undefined) {
  if (!ctx) return "";
  const parts: string[] = [];
  if (ctx.role) parts.push(`Role/topic target: ${ctx.role}`);
  if (ctx.company) parts.push(`Company/organization: ${ctx.company}`);
  if (ctx.audience) parts.push(`Audience/stakeholders: ${ctx.audience}`);
  if (ctx.objective) parts.push(`Objective: ${ctx.objective}`);
  if (ctx.level) parts.push(`Level: ${ctx.level}`);
  if (ctx.skills?.length) parts.push(`Skills: ${ctx.skills.join(", ")}`);
  if (ctx.projects?.length) parts.push(`Projects/examples: ${ctx.projects.slice(0, 5).join("; ")}`);
  if (ctx.focusAreas?.length) parts.push(`Focus areas: ${ctx.focusAreas.join(", ")}`);
  if (ctx.candidateBackground?.length) {
    parts.push(`Candidate background: ${ctx.candidateBackground.slice(0, 4).join("; ")}`);
  }
  if (ctx.rawSummary) parts.push(`Notes: ${ctx.rawSummary}`);
  return parts.length ? `\n\nSession context:\n- ${parts.join("\n- ")}` : "";
}

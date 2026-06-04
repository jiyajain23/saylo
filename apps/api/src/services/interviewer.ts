import { formatContextForPrompt, type StructuredContext } from "./contextEngine.js";

type Turn = { speaker: "user" | "ai"; text: string };

function toTranscriptSnippet(turns: Turn[], maxTurns: number) {
  const slice = turns.slice(-maxTurns);
  return slice
    .map((t) => `${t.speaker === "ai" ? "Interviewer" : "Candidate"}: ${t.text}`)
    .join("\n");
}

function fallbackQuestion(turns: Turn[], ctx?: StructuredContext | null) {
  const hasIntro = turns.filter((t) => t.speaker === "ai").length === 0;
  if (hasIntro) {
    return `Hi! Let's start with a quick intro. Can you tell me about yourself and what draws you to this role?`;
  }

  const lastUser = [...turns].reverse().find((t) => t.speaker === "user")?.text ?? "";
  if (/team|conflict|disagree/i.test(lastUser)) {
    return "Thanks—what did you learn from that situation, and what would you do differently next time?";
  }
  if (/project|built|implemented/i.test(lastUser)) {
    return "Can you walk me through the impact—what metrics moved or what changed because of your work?";
  }
  if (ctx?.role && /product/i.test(ctx.role)) {
    return "How would you decide what to build next if you had limited time and stakeholder pressure?";
  }
  return "Good. Can you share a specific example, and explain your reasoning step-by-step?";
}

async function geminiGenerate(prompt: string) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) return null;

  const url =
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" +
    encodeURIComponent(key);

  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.6,
        maxOutputTokens: 220
      }
    })
  });

  if (!res.ok) return null;
  const json = (await res.json()) as any;
  const text: string | undefined =
    json?.candidates?.[0]?.content?.parts?.map((p: any) => p?.text).join("") ?? undefined;
  return text?.trim() || null;
}

export async function nextInterviewTurn(args: {
  turns: Turn[];
  context?: StructuredContext | null;
}): Promise<string> {
  const { turns, context } = args;
  const contextBlock = formatContextForPrompt(context);

  const prompt = `You are an interviewer running a realistic, supportive interview simulation.
- Keep questions concise (1-2 sentences).
- Ask one question at a time.
- Ask dynamic follow-ups based on the candidate's last answer.
- Use the candidate context when relevant (don't mention that you have it).
- Avoid being judgmental; sound professional.

Scenario: job interview (MVP).
${contextBlock}

Conversation so far:
${toTranscriptSnippet(turns, 10)}

Now respond with ONLY the next interviewer message.`;

  const llm = await geminiGenerate(prompt);
  if (llm) return llm.replace(/^Interviewer:\s*/i, "").trim();
  return fallbackQuestion(turns, context);
}


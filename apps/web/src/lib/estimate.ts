export type Workflow = "chat" | "coding" | "agents" | "support";
export type Level = "light" | "regular" | "heavy";

const LEVEL_TOKENS = { light: 2, regular: 12, heavy: 40 } as const;
const WORKFLOW_FACTOR = { chat: 1, coding: 1.2, agents: 1.6, support: 0.8 } as const;

export function estimateUsage(workflow: Workflow, level: Level): { millionTokens: number; suggestedUsd: 10 | 50 | 100 } {
  const millionTokens = Math.round(LEVEL_TOKENS[level] * WORKFLOW_FACTOR[workflow] * 10) / 10;
  const cost = millionTokens * 3;
  const suggestedUsd = cost <= 15 ? 10 : cost <= 60 ? 50 : 100;
  return { millionTokens, suggestedUsd };
}

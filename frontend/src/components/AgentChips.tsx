import { colorForAgent } from "../lib/palette";
import type { LeaderboardEntry } from "../types";

interface Props {
  agents: LeaderboardEntry[];
  hiddenIds: string[];
  onToggle: (agentId: string) => void;
}

export function AgentChips({ agents, hiddenIds, onToggle }: Props) {
  if (agents.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-3">
      {agents.map((agent) => {
        const active = !hiddenIds.includes(agent.id);
        const color = colorForAgent(agent.id, agent.is_benchmark);

        return (
          <button
            key={agent.id}
            type="button"
            onClick={() => onToggle(agent.id)}
            className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-sm transition ${
              active
                ? "border-stone-300 bg-white text-stone-900 shadow-sm"
                : "border-stone-200 bg-stone-50 text-stone-400"
            }`}
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span>{agent.name}</span>
          </button>
        );
      })}
    </div>
  );
}

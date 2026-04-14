import { colorForAgent } from "../lib/palette";
import { stripPaperMarker } from "../lib/format";
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
    <div className="flex flex-wrap gap-2.5">
      {agents.map((agent) => {
        const active = !hiddenIds.includes(agent.id);
        const color = colorForAgent(agent.id, agent.is_benchmark);

        return (
          <button
            key={agent.id}
            type="button"
            onClick={() => onToggle(agent.id)}
            className={`inline-flex items-center gap-2 border px-3 py-2 transition ${
              active
                ? "border-stone-300 bg-[#fffdf8] text-stone-900"
                : "border-stone-200 bg-transparent text-stone-400"
            }`}
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="whitespace-nowrap text-[12px] leading-none font-normal tracking-normal">
              {stripPaperMarker(agent.name)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

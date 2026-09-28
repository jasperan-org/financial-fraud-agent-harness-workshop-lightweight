import { Database, Brain, Globe2 } from "lucide-react";
import WorldExplorer from "./WorldExplorer";
import MemoryContext from "./MemoryContext";
import DataExplorer from "./DataExplorer";

const TABS = [
  { key: "world",   label: "World",   icon: Globe2,   text: "text-accent-skill",  bar: "bg-accent-skill" },
  { key: "context", label: "Context", icon: Brain,    text: "text-accent-memory", bar: "bg-accent-memory" },
  { key: "data",    label: "Data",    icon: Database, text: "text-accent-oracle", bar: "bg-accent-oracle" },
];

/**
 * The right-hand instrument panel. Hosts the three "instruments" — the 3D
 * World, the Memory Context, and the Data Explorer — as tabs so they sit in
 * parallel with the chat instead of competing for the same screen real estate.
 *
 * Width is driven by the `--panel-frac` CSS variable set on the workspace
 * (see Layout); on narrow viewports it collapses to a full-width band below
 * the chat.
 */
export default function InstrumentPanel({
  tab, onTabChange,
  identityId, agentFocus, focusTarget, onDismissFocus,
  contextWindow, tokenUsage, touched,
}) {
  const activeIndex = Math.max(0, TABS.findIndex((t) => t.key === tab));
  const active = TABS[activeIndex];

  return (
    <section className="shrink-0 flex flex-col min-w-0 h-[55vh] w-full border-t border-white/5 lg:h-full lg:w-[var(--panel-frac)] lg:border-t-0 lg:border-l bg-bg-panel">
      {/* Tab bar with a sliding indicator */}
      <div className="relative shrink-0 h-9 flex border-b border-white/5 bg-bg-panel">
        {TABS.map((t) => {
          const Icon = t.icon;
          const isActive = t.key === tab;
          return (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`flex-1 flex items-center justify-center gap-1.5 text-[11px] uppercase tracking-wider transition-colors ${
                isActive ? "text-text-primary" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <Icon size={12} className={isActive ? t.text : ""} />
              {t.label}
            </button>
          );
        })}
        <span
          className={`absolute bottom-0 left-0 h-[2px] transition-transform duration-300 ease-out ${active.bar}`}
          style={{ width: `${100 / TABS.length}%`, transform: `translateX(${activeIndex * 100}%)` }}
        />
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "world" && (
          <WorldExplorer
            identityId={identityId}
            agentFocus={agentFocus}
            focusTarget={focusTarget}
            onDismissFocus={onDismissFocus}
          />
        )}
        {tab === "context" && (
          <MemoryContext contextWindow={contextWindow} tokenUsage={tokenUsage} />
        )}
        {tab === "data" && (
          <DataExplorer identityId={identityId} touched={touched} />
        )}
      </div>
    </section>
  );
}

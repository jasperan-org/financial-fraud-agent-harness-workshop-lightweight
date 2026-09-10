import { ShieldCheck, Sparkles, MapPin, EyeOff, Lock, Newspaper, Globe2, Ban } from "lucide-react";

const CLEARANCE_BADGE = {
  EXECUTIVE: "bg-accent-tool/20 text-accent-tool border-accent-tool/40",
  STANDARD: "bg-accent-skill/20 text-accent-skill border-accent-skill/40",
};

// Starter prompts per persona. Each entry has:
//   text     — the prompt the button sends as a chat message
//   tag      — optional pill: 'news' | 'globe' | 'denied'
//   denyHint — when tag === 'denied', a 1-line explanation of which boundary
//              the question is expected to hit so the user understands the
//              red badge means "this is supposed to fail for this persona".
const STARTERS = {
  agent: [
    { text: "Briefly summarize the FINANCE schema — what entities and how they relate." },
    { text: "How many transactions were flagged or blocked by the AML rules in the last 90 days, and for which reasons?" },
    { text: "Pull up the SAR narrative for customer 42 and summarize the investigation.",
      tag: "denied",
      denyHint: "SAR_REPORTS is compliance-only — this persona can't read it at all." },
    { text: "Search the news for recent banking-fraud headlines and tell me which of our merchant categories they touch.",
      tag: "news" },
  ],
  cfo: [
    { text: "What's the total transaction volume in USD over the last 90 days?" },
    { text: "Show me the top 5 branches by transaction count, with the average amount." },
    { text: "Search the news for sanctions updates affecting cross-border payments.",
      tag: "news" },
    { text: "Fly the globe to the Wall Street branch and tell me about its region.",
      tag: "globe" },
    { text: "Open AGENT.AGENT_AUTHORIZATIONS and list every persona's region access.",
      tag: "denied",
      denyHint: "even the CFO is forbidden from AGENT admin tables — those are internal-only." },
  ],
  "compliance.officer": [
    { text: "List the open SAR reports with their reason codes and customer risk ratings." },
    { text: "Which customers drive the most flagged transactions, and what patterns do they show?" },
    { text: "Fly the globe to BitVault Exchange and show me flagged activity near it.",
      tag: "globe" },
    { text: "Search the news for the latest AML regulatory fines.",
      tag: "news" },
    { text: "Open AGENT.AGENT_AUTHORIZATIONS and list every persona's region access.",
      tag: "denied",
      denyHint: "even compliance can't open AGENT admin tables." },
  ],
  "analyst.east": [
    { text: "Which branches in EUROPE or MIDDLE_EAST have the most flagged transactions?" },
    { text: "What's the transaction mix by channel for my region over the last 90 days?" },
    { text: "Search the news for fraud trends in Europe affecting card payments.",
      tag: "news" },
    { text: "Fly the globe to the EUROPE region and highlight flagged activity.",
      tag: "globe" },
    { text: "Show me the top AMERICAS transactions by amount — I want to compare against my region.",
      tag: "denied",
      denyHint: "analyst.east can't see AMERICAS rows, AND transaction amounts are masked for this clearance." },
  ],
  "analyst.west": [
    { text: "Which merchants in AMERICAS or ASIA_PACIFIC attract the most flagged activity?" },
    { text: "List the casinos and crypto exchanges in my region." },
    { text: "Search the news for crypto or card-fraud incidents affecting Asia-Pacific.",
      tag: "news" },
    { text: "Fly the globe to Marina Bay Sands and show nearby flagged transactions.",
      tag: "globe" },
    { text: "What's the total transaction value for EUROPE over the last 90 days?",
      tag: "denied",
      denyHint: "analyst.west can't see EUROPE rows — and amounts are masked for this clearance anyway." },
  ],
  "ops.viewer": [
    { text: "How many branches are in each region, and where are they?" },
    { text: "Which merchants have the most flagged transactions in the last 120 days?" },
    { text: "Search the news for major banking outages or payment-rail incidents in the last 24h.",
      tag: "news" },
    { text: "Fly the globe to Dubai (DXB) and zoom in.",
      tag: "globe" },
    { text: "Show me the customer record for the account with the highest balance.",
      tag: "denied",
      denyHint: "ops.viewer is forbidden from FINANCE.CUSTOMERS — operations only, no customer PII." },
  ],
};

const FALLBACK_STARTERS = [
  { text: "What's in the FINANCE schema?" },
  { text: "How many transactions were flagged in the last 90 days?" },
];

const TAG_META = {
  news:   { icon: Newspaper, label: "live news", cls: "bg-accent-skill/15 text-accent-skill border-accent-skill/30" },
  globe:  { icon: Globe2,    label: "globe",     cls: "bg-accent-memory/15 text-accent-memory border-accent-memory/30" },
  denied: { icon: Ban,       label: "expected: denied", cls: "bg-accent-sql/15 text-accent-sql border-accent-sql/40" },
};

/**
 * Shown in the chat pane before the first message of a thread. Describes the
 * acting persona (clearance / regions / masks / forbidden tables) and offers
 * starter-prompt buttons calibrated to what that persona can actually see.
 *
 * Each persona's starter list now includes:
 *   • A live-news question (search_tavily) tagged "news".
 *   • A globe-driving question (focus_world) tagged "globe".
 *   • One question deliberately calibrated to FAIL for this persona's
 *     authorization rules — flagged with a red "expected: denied" chip so the
 *     user learns where the boundary is.
 */
export default function WelcomeMat({ identity, onStart }) {
  if (!identity) return null;
  const starters = STARTERS[identity.id] || FALLBACK_STARTERS;
  const clearanceCls =
    CLEARANCE_BADGE[identity.clearance] ||
    "bg-text-secondary/20 text-text-secondary border-text-secondary/40";

  return (
    <div className="max-w-3xl mx-auto mt-6 mb-8">
      <div className="bg-bg-elev border border-white/5 rounded-lg overflow-hidden">
        {/* Persona header */}
        <div className="px-5 py-4 border-b border-white/5 bg-gradient-to-r from-bg-panel/80 to-bg-elev">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck size={16} className="text-accent-oracle" />
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              You are acting as
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-semibold text-text-primary">
              {identity.label}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${clearanceCls}`}>
              {identity.clearance}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-white/[0.05] text-text-secondary">
              id: {identity.id}
            </span>
          </div>
          <p className="mt-2 text-[13px] text-text-accent leading-snug">
            {identity.description}
          </p>
        </div>

        {/* Restriction summary */}
        <div className="px-5 py-3 grid grid-cols-1 sm:grid-cols-3 gap-3 border-b border-white/5">
          <RestrictionTile
            icon={<MapPin size={12} className="text-accent-skill" />}
            label="Authorized regions"
            items={identity.regions || ["all regions"]}
            allOpenLabel="all regions"
          />
          <RestrictionTile
            icon={<EyeOff size={12} className="text-accent-sql" />}
            label="Masked columns"
            items={(identity.mask_cols || []).map((c) => c.split(".").slice(-2).join("."))}
            emptyLabel="none — every column visible"
          />
          <RestrictionTile
            icon={<Lock size={12} className="text-accent-sql" />}
            label="Forbidden tables"
            items={(identity.forbid_tables || []).map((c) => c.split(".").slice(-2).join("."))}
            emptyLabel="none — every table readable"
          />
        </div>

        {/* Starters */}
        <div className="px-5 py-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Sparkles size={12} className="text-accent-tool" />
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                Starter questions for this role
              </span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-text-muted">
              <Legend />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {starters.map((q) => (
              <StarterButton key={q.text} q={q} onStart={onStart} />
            ))}
          </div>
          <p className="mt-3 text-[10px] text-text-muted">
            Click a card to send it as your first message — or type your own
            below. Cards marked <span className="text-accent-sql">expected: denied</span>{" "}
            intentionally hit this persona's authorization boundary so you can
            see how the agent surfaces the denial. Switch persona in the
            header to change what you can see.
          </p>
        </div>
      </div>
    </div>
  );
}

function StarterButton({ q, onStart }) {
  const meta = q.tag ? TAG_META[q.tag] : null;
  const Icon = meta?.icon;
  const borderCls = q.tag === "denied"
    ? "border-accent-sql/30 hover:border-accent-sql"
    : "border-white/[0.06] hover:border-accent-oracle/40";
  return (
    <button
      onClick={() => onStart(q.text)}
      className={`text-left text-[12px] leading-snug px-3 py-2 rounded border bg-white/[0.02] hover:bg-white/[0.06] text-text-accent ${borderCls}`}
      title={q.denyHint || undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <span>{q.text}</span>
        {meta && (
          <span className={`shrink-0 inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono border ${meta.cls}`}>
            {Icon ? <Icon size={9} /> : null}
            {meta.label}
          </span>
        )}
      </div>
      {q.tag === "denied" && q.denyHint && (
        <div className="mt-1 text-[10px] text-accent-sql/80 italic">
          {q.denyHint}
        </div>
      )}
    </button>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {Object.entries(TAG_META).map(([k, m]) => {
        const Icon = m.icon;
        return (
          <span
            key={k}
            className={`inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono border ${m.cls}`}
          >
            <Icon size={9} />
            {m.label}
          </span>
        );
      })}
    </div>
  );
}

function RestrictionTile({ icon, label, items, emptyLabel, allOpenLabel }) {
  return (
    <div className="bg-bg-panel/40 rounded p-2.5 border border-white/[0.04]">
      <div className="flex items-center gap-1.5 mb-1.5">
        {icon}
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          {label}
        </span>
      </div>
      <div className="flex flex-wrap gap-1">
        {items.length === 0 || (items.length === 1 && items[0] === allOpenLabel) ? (
          items.length === 0 ? (
            <span className="text-[10px] text-text-secondary italic">
              {emptyLabel}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-memory/15 text-accent-memory font-mono">
              {items[0]}
            </span>
          )
        ) : (
          items.map((it) => (
            <span
              key={it}
              className="text-[10px] px-1.5 py-0.5 rounded bg-accent-skill/10 text-text-accent font-mono border border-white/5"
            >
              {it}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

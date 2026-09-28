import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";
import { Globe2, Search, Building2, Store, AlertTriangle, RefreshCw, Crosshair } from "lucide-react";

const LAYER_COLORS = {
  branch:             "#ffd166", // accent-tool
  merchant:           "#118ab2", // accent-skill
  suspicious_activity: "#f80000", // accent-oracle — red AML dots
  customer:           "#06d6a0", // accent-memory
  region:             "#3b82f6",
  coords:             "#a78bfa",
};

// Arc color by AML flag reason (activity_arcs).
const FLAG_ARC_COLOR = {
  STRUCTURING:        "#ef476f", // accent-sql
  GEO_VELOCITY:       "#06d6a0", // accent-memory
  HIGH_RISK_COUNTRY:  "#ffd166",
  RAPID_CASH_OUT:     "#118ab2",
  LARGE_CASH_DEPOSIT: "#f80000",
};

// Live-feed arcs are transient: only the freshest few are drawn, and any older
// than this window drop off, so new AML hits appear as lines and then fade
// instead of piling up on the globe forever.
const LIVE_ARC_WINDOW_MS = 90_000;
const LIVE_ARC_MAX = 8;

const KIND_ICON = {
  branch:   Building2,
  merchant: Store,
  suspicious_activity: AlertTriangle,
};

/**
 * The World Explorer — a 3D globe that renders the Meridian Bank dataset
 * geographically. Branches, merchants, and the bank's suspicious-activity
 * layer (recent FLAGGED / BLOCKED transactions plotted at their merchant, with
 * arcs from the account's home branch to the merchant).
 *
 * It fills its parent container (the Instrument panel's World tab) instead of
 * being a collapsible bottom drawer, so it can sit in parallel with the chat.
 *
 * The globe respects the "Use As:" identity: switching personas re-fetches
 * /api/world with `as_user=` so an analyst.east user only sees EUROPE +
 * MIDDLE_EAST branches, merchants, and flagged activity.
 *
 * `agentFocus` / `focusTarget` come from the Layout-level useWorldFocus hook so
 * the agent's `focus_world` tool still flies the camera even though this
 * component may be mounted only while the World tab is active.
 */
export default function WorldExplorer({
  identityId, agentFocus, focusTarget, lastActivity,
  autoFollow, onToggleAutoFollow, onDismissFocus,
  touched = {}, trace = [], isThinking = false,
  live, identity,
}) {
  const [data, setData] = useState({
    branches: [], merchants: [], suspicious_activity: [], activity_arcs: [],
    customers_forbidden: false,
    stats: { branches: 0, merchants: 0, suspicious_activity: 0, activity_arcs: 0 },
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQ, setSearchQ] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const [layers, setLayers] = useState({
    branches: true, merchants: true, suspicious_activity: true,
  });
  // Briefly true after the agent moves the globe, so the live strip can pulse.
  const [activityFresh, setActivityFresh] = useState(false);

  const globeRef = useRef(null);
  const wrapRef = useRef(null);
  const [globeSize, setGlobeSize] = useState({ w: 720, h: 480 });

  useEffect(() => {
    if (!lastActivity) return;
    setActivityFresh(true);
    const t = window.setTimeout(() => setActivityFresh(false), 5000);
    return () => window.clearTimeout(t);
  }, [lastActivity]);

  // ---- Live reaction to the tool calls streaming in from the chat ----------
  // The backend emits `tables_touched` (a map of SCHEMA.TABLE → {action, ts})
  // plus tool_started / tool_finished events. We turn those into visible
  // motion: the layer the agent is reading pulses, a radar sweep runs while it
  // works, and a ticker names the current tool — so the globe reads as live
  // even when a query has no single location to fly to.
  const pulseLayers = useMemo(() => {
    const out = new Set();
    for (const key of Object.keys(touched || {})) {
      const t = key.toUpperCase();
      if (t.endsWith(".*")) {
        out.add("branches"); out.add("merchants"); out.add("suspicious_activity");
        continue;
      }
      if (t.includes("TRANSACTION") || t.includes("SAR") || t.includes("SANCTION")) out.add("suspicious_activity");
      if (t.includes("MERCHANT")) out.add("merchants");
      if (t.includes("BRANCH") || t.includes("ACCOUNT") || t.includes("CUSTOMER") || t.includes("LOAN")) out.add("branches");
    }
    return out;
  }, [touched]);
  const pulseKey = useMemo(() => [...pulseLayers].sort().join(","), [pulseLayers]);
  const [pulseOn, setPulseOn] = useState(false);

  useEffect(() => {
    if (!pulseKey) { setPulseOn(false); return; }
    const id = window.setInterval(() => setPulseOn((v) => !v), 550);
    return () => window.clearInterval(id);
  }, [pulseKey]);

  const liveTool = useMemo(() => {
    const evs = (trace || []).filter((t) => t.type === "tool_started" || t.type === "tool_finished");
    const last = evs[evs.length - 1];
    if (!last) return null;
    return {
      name: last.name,
      done: last.type === "tool_finished",
      tables: Object.keys(touched || {}),
    };
  }, [trace, touched]);

  // ---- Live data feed ------------------------------------------------------
  // The backend streams simulated banking activity. We keep only the events
  // this persona is allowed to see (same region contract as /api/world) and
  // render them as fresh, pulsing markers + arcs on top of the fetched layers.
  const amountMasked = useMemo(() => {
    const masks = identity?.mask_cols || [];
    return masks.some((m) => String(m).toUpperCase().endsWith("AMOUNT_CENTS"));
  }, [identity]);

  // Tick so the recency window below re-evaluates as events age — otherwise a
  // live arc would only disappear when the next event happened to arrive.
  const [nowTick, setNowTick] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 4000);
    return () => window.clearInterval(id);
  }, []);

  // Region-gated (for the ticker + counters) — no time window.
  const liveAllowed = useMemo(() => {
    const regs = identity?.regions;
    return (live?.events || []).filter((e) => !regs || regs.includes(e.region));
  }, [live?.events, identity]);

  // Recent only — drives the transient arcs, points and rings so the globe
  // never accumulates lines.
  const liveRecent = useMemo(
    () => liveAllowed.filter((e) => nowTick - (e.receivedAt || nowTick) < LIVE_ARC_WINDOW_MS),
    [liveAllowed, nowTick],
  );

  const liveFlagged = useMemo(
    () => liveRecent.filter((e) => e.status === "FLAGGED" || e.status === "BLOCKED"),
    [liveRecent],
  );

  const livePoints = useMemo(
    () => liveFlagged.slice(0, 60).map((e) => ({
      kind: "suspicious_activity",
      id: `live-${e.txn_id}`,
      txn_id: e.txn_id,
      txn_ts: e.txn_ts,
      amount_cents: e.amount_cents,
      status: e.status,
      flag_reason: e.flag_reason,
      channel: e.channel,
      region: e.region,
      merchant: e.merchant,
      merchant_category: e.merchant_category,
      lat: e.lat,
      lng: e.lng,
      live: true,
    })),
    [liveFlagged],
  );

  const liveArcs = useMemo(
    () => liveFlagged
      .filter((e) => e.origin && e.lat != null)
      .slice(0, LIVE_ARC_MAX)
      .map((e) => ({
        kind: "activity_arc",
        id: `live-${e.txn_id}`,
        status: e.status,
        flag_reason: e.flag_reason,
        region: e.region,
        branch: e.origin.branch,
        branch_code: e.origin.branch_code,
        merchant: e.merchant,
        startLat: e.origin.lat,
        startLng: e.origin.lng,
        endLat: e.lat,
        endLng: e.lng,
        color: FLAG_ARC_COLOR[e.flag_reason] || "#ffffff",
        live: true,
      })),
    [liveFlagged],
  );

  const fetchWorld = () => {
    setLoading(true);
    setError(null);
    fetch(`/api/world?as_user=${encodeURIComponent(identityId || "agent")}`)
      .then(async (r) => {
        const text = await r.text();
        // If the dev server fell through to index.html (because the backend's
        // /api/world endpoint isn't registered yet — usually means the Flask
        // process needs a restart), produce a useful error instead of a JSON
        // parse error.
        if (text.startsWith("<")) {
          throw new Error(
            "/api/world returned HTML — backend likely needs a restart so the new world routes register."
          );
        }
        try {
          return JSON.parse(text);
        } catch {
          throw new Error(`/api/world returned non-JSON: ${text.slice(0, 120)}`);
        }
      })
      .then((d) => {
        if (d && d.error) {
          setError(d.error);
          return;
        }
        setData(d);
      })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  };

  // Fetch on mount and whenever the acting identity changes.
  useEffect(() => {
    fetchWorld();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identityId]);

  // When the agent resolves a focus target, fly the camera to it. Runs on mount
  // too, so a focus that arrived while the tab was hidden still applies.
  useEffect(() => {
    if (!focusTarget || focusTarget.lat == null || focusTarget.lng == null) return;
    const t = window.setTimeout(() => {
      if (globeRef.current) {
        globeRef.current.pointOfView(
          { lat: focusTarget.lat, lng: focusTarget.lng, altitude: focusTarget.altitude || 1.5 },
          1500,
        );
      }
    }, 60);
    setSearchResult({
      kind: focusTarget.kind,
      id: focusTarget.target,
      name: focusTarget.label,
      lat: focusTarget.lat,
      lng: focusTarget.lng,
      region: focusTarget.region,
    });
    return () => window.clearTimeout(t);
  }, [focusTarget]);

  // react-globe.gl wants explicit pixel dimensions; measure the canvas wrapper.
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(() => {
      const rect = wrapRef.current.getBoundingClientRect();
      setGlobeSize({
        w: Math.max(240, Math.round(rect.width)),
        h: Math.max(240, Math.round(rect.height)),
      });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const points = useMemo(() => {
    const out = [];
    // The layer the agent is currently reading breathes (1.35× → 1.9×) so the
    // map visibly responds to the tool call even without a camera move.
    const grow = (layer) =>
      pulseLayers.has(layer) ? (pulseOn ? 1.9 : 1.35) : 1;
    if (layers.branches) {
      for (const b of data.branches) {
        out.push({ ...b, _layer: "branches", size: 0.18 * grow("branches"), color: LAYER_COLORS.branch });
      }
    }
    if (layers.merchants) {
      for (const m of data.merchants) {
        out.push({ ...m, _layer: "merchants", size: 0.12 * grow("merchants"), color: LAYER_COLORS.merchant });
      }
    }
    if (layers.suspicious_activity) {
      for (const s of data.suspicious_activity || []) {
        out.push({ ...s, _layer: "suspicious_activity", size: 0.3 * grow("suspicious_activity"), color: LAYER_COLORS.suspicious_activity });
      }
      // Live AML hits stream in — slightly larger so fresh ones stand out.
      for (const s of livePoints) {
        out.push({ ...s, _layer: "suspicious_activity", size: 0.45 * grow("suspicious_activity"), color: LAYER_COLORS.suspicious_activity });
      }
    }
    if (searchResult) {
      out.push({
        ...searchResult,
        kind: searchResult.kind,
        size: 0.9,
        color: LAYER_COLORS[searchResult.kind] || "#ffffff",
        searchAnchor: true,
      });
    }
    return out;
  }, [data, layers, searchResult, pulseLayers, pulseOn, livePoints]);

  const arcs = useMemo(() => {
    if (!layers.suspicious_activity) return [];
    const base = (data.activity_arcs || [])
      .filter((a) => a.origin && a.destination)
      .map((a) => ({
        startLat: a.origin.lat,
        startLng: a.origin.lng,
        endLat: a.destination.lat,
        endLng: a.destination.lng,
        color: FLAG_ARC_COLOR[a.flag_reason] || "#ffffff",
        ...a,
      }));
    return [...base, ...liveArcs];
  }, [data.activity_arcs, layers.suspicious_activity, liveArcs]);

  // Ripples: the anchor the agent flew to, plus the freshest live AML hits —
  // so new detections visibly pulse on the globe as they arrive.
  const rings = useMemo(() => {
    const out = [];
    if (searchResult && searchResult.lat != null && searchResult.lng != null) {
      out.push({
        lat: searchResult.lat,
        lng: searchResult.lng,
        color: LAYER_COLORS[searchResult.kind] || "#ffd166",
      });
    }
    for (const e of liveFlagged.slice(0, 3)) {
      if (e.lat != null && e.lng != null) {
        out.push({ lat: e.lat, lng: e.lng, color: FLAG_ARC_COLOR[e.flag_reason] || "#f80000" });
      }
    }
    return out;
  }, [searchResult, liveFlagged]);

  const onSearch = (e) => {
    e.preventDefault();
    const raw = searchQ.trim();
    if (!raw) return;
    const cleaned = sanitizeQuery(raw);
    setSearchError(null);
    fetch(
      `/api/world/search?q=${encodeURIComponent(cleaned)}&as_user=${encodeURIComponent(identityId || "agent")}`
    )
      .then(async (r) => {
        const text = await r.text();
        if (text.startsWith("<")) {
          return { ok: false, body: { error: "backend missing /api/world/search — restart backend" } };
        }
        let body;
        try {
          body = JSON.parse(text);
        } catch {
          body = { error: `non-JSON response: ${text.slice(0, 120)}` };
        }
        return { ok: r.ok, body };
      })
      .then(({ ok, body }) => {
        if (!ok || body.error) {
          setSearchError(body.error || "search failed");
          setSearchResult(null);
          return;
        }
        setSearchResult(body);
        if (globeRef.current && body.lat != null && body.lng != null) {
          globeRef.current.pointOfView({ lat: body.lat, lng: body.lng, altitude: 1.6 }, 1500);
        }
      })
      .catch((e) => {
        setSearchError(String(e?.message || e));
        setSearchResult(null);
      });
  };

  const noFeatures = !loading && !error && data.stats.branches === 0;

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Toolbar — search, layer toggles, refresh */}
      <div className="shrink-0 border-b border-white/5 bg-bg-panel/60 px-3 py-2 space-y-2">
        <form onSubmit={onSearch} className="flex items-center gap-2">
          <Search size={12} className="text-text-muted shrink-0" />
          <input
            type="text"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="fly to — branch, merchant, customer, or region (Wall Street · BitVault Exchange · EUROPE)"
            className="flex-1 min-w-0 bg-transparent text-[11px] font-mono text-text-primary placeholder:text-text-muted focus:outline-none"
          />
          <button
            type="submit"
            className="text-[10px] px-2 py-0.5 rounded border border-white/10 text-text-secondary hover:text-text-primary hover:border-accent-skill/40"
          >
            fly
          </button>
          <button
            type="button"
            onClick={fetchWorld}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-white/5"
            title="refresh world data"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </form>

        <div className="flex items-center gap-2 flex-wrap">
          {Object.entries(layers).map(([k, v]) => {
            const Icon = KIND_ICON[k] || Building2;
            return (
              <button
                key={k}
                onClick={() => setLayers((s) => ({ ...s, [k]: !s[k] }))}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-mono ${
                  v
                    ? "border-white/10 bg-white/[0.05] text-text-primary"
                    : "border-white/5 text-text-muted hover:text-text-secondary"
                } ${pulseLayers.has(k) ? "data-explorer-pulse-read" : ""}`}
                title={`toggle ${k} layer`}
              >
                <Icon size={10} style={{ color: LAYER_COLORS[k] || "#888" }} />
                {k === "suspicious_activity" ? "flagged" : k}
              </button>
            );
          })}
          <button
            onClick={onToggleAutoFollow}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-mono ${
              autoFollow
                ? "border-accent-skill/40 bg-accent-skill/10 text-accent-skill"
                : "border-white/5 text-text-muted hover:text-text-secondary"
            }`}
            title={
              autoFollow
                ? "auto-follow on — the globe flies to the regions the agent queries"
                : "auto-follow off — only explicit focus_world calls move the globe"
            }
          >
            <Crosshair size={10} />
            auto-follow {autoFollow ? "on" : "off"}
          </button>
          <span className="ml-auto text-[10px] text-text-muted font-mono">
            {data.stats.branches} br · {data.stats.merchants} merch ·{" "}
            {data.stats.suspicious_activity + livePoints.length} flagged · {data.stats.activity_arcs} recent arcs
            {live?.counts?.total > 0 && (
              <> · <span className="text-accent-oracle">+{live.counts.total} live</span></>
            )}
          </span>
        </div>

        {(searchError || searchResult) && (
          <div className="text-[10px] font-mono">
            {searchError ? (
              <span className="text-accent-sql">{searchError}</span>
            ) : (
              <span className="text-accent-memory">
                → {searchResult.kind}: {searchResult.name || searchResult.description || searchResult.id}{" "}
                ({searchResult.lat.toFixed(2)}, {searchResult.lng.toFixed(2)})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Live data feed — new transactions streaming in */}
      {live?.enabled && liveAllowed.length > 0 && (
        <div className="shrink-0 px-3 py-1 border-b border-white/5 flex items-center gap-2 text-[10px] font-mono">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-oracle animate-pulse shrink-0" />
          <span className="text-accent-oracle shrink-0">live</span>
          {liveAllowed[0].status !== "COMPLETED" ? (
            <span className="truncate">
              <span className="text-accent-sql">
                {liveAllowed[0].status} · {liveAllowed[0].flag_reason}
              </span>
              <span className="text-text-muted">
                {" · "}
                {amountMasked ? "[REDACTED]" : `$${(liveAllowed[0].amount_cents / 100).toLocaleString()}`}
                {" · "}
                {liveAllowed[0].merchant || liveAllowed[0].origin?.branch || liveAllowed[0].region}
              </span>
            </span>
          ) : (
            <span className="truncate text-text-muted">
              txn {liveAllowed[0].txn_id} ·{" "}
              {amountMasked ? "[REDACTED]" : `$${(liveAllowed[0].amount_cents / 100).toLocaleString()}`}
              {" · "}
              {liveAllowed[0].merchant || liveAllowed[0].region}
            </span>
          )}
          <span className="ml-auto text-text-muted shrink-0">
            +{live.counts.total} · {live.counts.flagged + live.counts.blocked} AML
          </span>
        </div>
      )}

      {/* Live tool ticker — what the agent is doing right now */}
      {isThinking && liveTool && (
        <div className="shrink-0 px-3 py-1 border-b border-white/5 flex items-center gap-2 text-[10px] font-mono bg-accent-skill/[0.04]">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-skill animate-pulse shrink-0" />
          <span className="text-accent-skill shrink-0">
            {liveTool.done ? "✓" : "▶"} {liveTool.name}
          </span>
          {liveTool.tables.length > 0 && (
            <span className="text-text-muted truncate">
              {liveTool.tables.map((t) => t.split(".").pop()).join(", ")}
            </span>
          )}
          <span className="ml-auto text-text-muted shrink-0">agent working…</span>
        </div>
      )}

      {/* Live activity — what the agent is looking at right now */}
      {lastActivity && lastActivity.lat != null && (
        <div className="shrink-0 px-3 py-1 border-b border-white/5 flex items-center gap-2 text-[10px] font-mono">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
              activityFresh ? "bg-accent-skill animate-pulse" : "bg-text-muted/40"
            }`}
          />
          <span className="text-text-muted shrink-0">
            {lastActivity.source === "explicit" ? "agent" : "auto"}
          </span>
          <span className="text-text-primary truncate">
            {lastActivity.kind}: {lastActivity.label || lastActivity.target}
          </span>
          <span className="text-text-muted truncate ml-auto">
            {_fix(lastActivity.lat, 2)}, {_fix(lastActivity.lng, 2)}
          </span>
          {!autoFollow && lastActivity.source === "auto" && (
            <span className="text-text-muted/70 shrink-0">· auto-follow off</span>
          )}
        </div>
      )}

      {/* Agent-driven focus banner */}
      {agentFocus && (
        <div className="shrink-0 px-3 py-1.5 border-b border-accent-oracle/30 bg-accent-oracle/10 flex items-center gap-2 text-[11px] font-mono">
          <Globe2 size={11} className="text-accent-oracle shrink-0" />
          {agentFocus.pending ? (
            <>
              <span className="text-accent-oracle">agent is flying the globe</span>
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-oracle animate-pulse" />
              <span className="text-text-muted truncate">
                {agentFocus.kind}: {agentFocus.target || "…"}
              </span>
            </>
          ) : (
            <>
              <span className="text-accent-oracle shrink-0">agent flew the globe →</span>
              <span className="text-text-primary truncate">{agentFocus.label || agentFocus.target}</span>
              <span className="text-text-muted truncate">
                ({agentFocus.kind} · {_fix(agentFocus.lat, 2)}, {_fix(agentFocus.lng, 2)})
              </span>
            </>
          )}
          <button
            className="ml-auto text-[10px] text-text-muted hover:text-text-primary shrink-0"
            onClick={onDismissFocus}
            title="dismiss"
          >
            ×
          </button>
        </div>
      )}

      {/* Globe canvas */}
      <div ref={wrapRef} className="flex-1 relative overflow-hidden bg-[#000308] min-h-0">
        {noFeatures && (
          <div className="absolute inset-0 flex items-center justify-center text-text-muted text-xs">
            no geo features available — has the FINANCE seed run?
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-accent-sql text-[11px] font-mono">
            {String(error).slice(0, 200)}
          </div>
        )}
        {/* Earth textures are served from public/globe so the globe renders
            offline and over plain http:// — protocol-relative unpkg.com URLs
            resolve to http:// and die on unpkg's cross-origin https redirect. */}
        <Globe
          ref={globeRef}
          width={globeSize.w}
          height={globeSize.h}
          backgroundColor="#000308"
          globeImageUrl="/globe/earth-night.jpg"
          bumpImageUrl="/globe/earth-topology.png"
          showAtmosphere={true}
          atmosphereColor="#3b82f6"
          atmosphereAltitude={0.18}
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor="color"
          pointAltitude={(d) =>
            d.searchAnchor ? 0.06 : d.kind === "suspicious_activity" ? 0.012 : 0.008
          }
          pointRadius={(d) => d.size}
          pointLabel={(d) => buildLabel(d)}
          onPointClick={(d) => {
            if (globeRef.current) {
              globeRef.current.pointOfView({ lat: d.lat, lng: d.lng, altitude: 1.4 }, 1000);
            }
          }}
          ringsData={rings}
          ringLat="lat"
          ringLng="lng"
          ringColor={(d) => d.color}
          ringMaxRadius={4}
          ringPropagationSpeed={2.2}
          ringRepeatPeriod={800}
          ringAltitude={0.006}
          arcsData={arcs}
          arcStartLat="startLat"
          arcStartLng="startLng"
          arcEndLat="endLat"
          arcEndLng="endLng"
          arcColor={(d) => d.color}
          arcAltitudeAutoScale={0.4}
          arcStroke={0.4}
          arcDashLength={0.45}
          arcDashGap={0.15}
          arcDashAnimateTime={3500}
          arcLabel={(d) =>
            `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#f5f5f5;background:#0a0a0acc;padding:6px 8px;border:1px solid rgba(255,255,255,0.1);border-radius:4px">
               <strong>txn ${d.id}</strong> · ${d.status}<br/>
               ${d.branch} → ${d.merchant}<br/>
               <span style="color:#888">${d.flag_reason || "AML"} · ${d.region}</span>
             </div>`
          }
        />
        {/* Radar sweep — runs while the agent works so the globe reads as
            live even when the query has no single location to fly to. */}
        <div
          className="pointer-events-none absolute rounded-full"
          style={{
            width: Math.round(Math.min(globeSize.w, globeSize.h) * 0.96),
            height: Math.round(Math.min(globeSize.w, globeSize.h) * 0.96),
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%) rotate(0deg)",
            background:
              "conic-gradient(from 0deg, rgba(17,138,178,0) 0deg, rgba(17,138,178,0.30) 22deg, rgba(17,138,178,0) 46deg)",
            animation: "globe-sweep 4s linear infinite",
            opacity: isThinking ? 0.9 : 0,
            transition: "opacity 400ms ease",
          }}
        />
      </div>
    </div>
  );
}

// Pull out the value the user actually meant when they typed something like
// "branch (Wall Street)", "merchant: BitVault", or just "EUROPE". The backend's
// LIKE is wide so we mostly need to drop the descriptive label and parens.
function sanitizeQuery(raw) {
  let q = raw;
  const paren = q.match(/\(([^)]+)\)/);
  if (paren) {
    q = paren[1];
  } else {
    q = q.replace(/^\s*(branch|merchant|customer|region)s?\s*[:\-]\s*/i, "");
  }
  return q.trim();
}

// Defensive helpers: tooltips can fire on points whose payloads are sparse —
// in particular `searchAnchor` markers from the chat agent's focus_world call,
// which only carry kind/lat/lng/name/region until the world fetch completes
// and replaces them with the full record. Crashing on `undefined.toLocaleString`
// would break the whole globe canvas, so we guard every numeric/string read.
const _num = (v, fallback = "—") => {
  if (v == null || (typeof v === "number" && !Number.isFinite(v))) return fallback;
  try { return Number(v).toLocaleString(); } catch { return String(v); }
};
const _fix = (v, digits = 1, fallback = "—") => {
  const n = typeof v === "number" ? v : (v != null ? Number(v) : NaN);
  return Number.isFinite(n) ? n.toFixed(digits) : fallback;
};
const _txt = (v, fallback = "—") =>
  v == null || v === "" ? fallback : String(v);

const _usd = (cents) => {
  if (cents == null || !Number.isFinite(Number(cents))) return "—";
  return "$" + (Number(cents) / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
};

function buildLabel(d) {
  const styles =
    'font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#f5f5f5;background:#0a0a0acc;padding:6px 8px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;max-width:280px';

  if (d.searchAnchor) {
    const coord = `${_fix(d.lat, 2)}, ${_fix(d.lng, 2)}`;
    return `<div style="${styles}"><strong>${_txt(d.name || d.id)}</strong><br/>` +
           `<span style="color:#888">${_txt(d.kind, "anchor")}</span> · ${coord}` +
           (d.region ? `<br/>region: ${_txt(d.region)}` : "") +
           "</div>";
  }

  if (d.kind === "branch") {
    return `<div style="${styles}"><strong>${_txt(d.name)}</strong> (${_txt(d.branch_code)})<br/>` +
           `${_txt(d.city)}, ${_txt(d.country)} · ${_txt(d.region)}<br/>` +
           `opened: ${_txt(d.opened_year, "—")}</div>`;
  }
  if (d.kind === "merchant") {
    return `<div style="${styles}"><strong>${_txt(d.name)}</strong><br/>` +
           `MCC ${_txt(d.mcc_code)} · ${_txt(d.category)}<br/>` +
           `${_txt(d.country)} · ${_txt(d.region)}</div>`;
  }
  if (d.kind === "suspicious_activity") {
    return `<div style="${styles}"><strong>${_txt(d.flag_reason, "AML")}</strong> · ${_txt(d.status)}<br/>` +
           `${_usd(d.amount_cents)} via ${_txt(d.channel)}<br/>` +
           `merchant: ${_txt(d.merchant, "branch cash")} (${_txt(d.merchant_category, "—")})<br/>` +
           `txn #${_txt(d.txn_id)} · ${_txt(d.region)}</div>`;
  }
  if (d.kind === "customer") {
    return `<div style="${styles}"><strong>${_txt(d.name)}</strong><br/>` +
           `branch: ${_txt(d.branch)} (${_txt(d.city)})<br/>` +
           `region: ${_txt(d.region)}</div>`;
  }
  return `<div style="${styles}">${_txt(d.name || d.id)}</div>`;
}

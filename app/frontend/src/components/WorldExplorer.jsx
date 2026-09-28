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
    if (layers.branches) {
      for (const b of data.branches) {
        out.push({ ...b, size: 0.18, color: LAYER_COLORS.branch });
      }
    }
    if (layers.merchants) {
      for (const m of data.merchants) {
        out.push({ ...m, size: 0.12, color: LAYER_COLORS.merchant });
      }
    }
    if (layers.suspicious_activity) {
      for (const s of data.suspicious_activity || []) {
        out.push({ ...s, size: 0.3, color: LAYER_COLORS.suspicious_activity });
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
  }, [data, layers, searchResult]);

  const arcs = useMemo(() => {
    if (!layers.suspicious_activity) return [];
    return (data.activity_arcs || [])
      .filter((a) => a.origin && a.destination)
      .map((a) => ({
        startLat: a.origin.lat,
        startLng: a.origin.lng,
        endLat: a.destination.lat,
        endLng: a.destination.lng,
        color: FLAG_ARC_COLOR[a.flag_reason] || "#ffffff",
        ...a,
      }));
  }, [data.activity_arcs, layers.suspicious_activity]);

  // A ripple at the anchor the agent just flew to — makes the globe feel live
  // as queries land, even when the camera move is subtle.
  const rings = useMemo(() => {
    if (!searchResult || searchResult.lat == null || searchResult.lng == null) return [];
    return [{
      lat: searchResult.lat,
      lng: searchResult.lng,
      color: LAYER_COLORS[searchResult.kind] || "#ffd166",
    }];
  }, [searchResult]);

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
                }`}
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
            {data.stats.suspicious_activity} flagged · {data.stats.activity_arcs} arcs
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

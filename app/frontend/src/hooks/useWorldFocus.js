import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Listens for the agent's globe-driving events and exposes them as state.
 *
 * Lives at the Layout level (always mounted) rather than inside WorldExplorer,
 * so a `focus_world` call still lands when the World tab is not the active one:
 * Layout switches to World on `agentFocus`, and WorldExplorer flies the camera
 * when `focusTarget` changes.
 *
 *   tool_started {name:"focus_world"}  → agentFocus {pending:true}  (banner)
 *   focus_world  {lat,lng,label,...}   → agentFocus + focusTarget   (banner + fly)
 */
export function useWorldFocus(socket) {
  const [agentFocus, setAgentFocus] = useState(null);
  const [focusTarget, setFocusTarget] = useState(null);
  const clearTimer = useRef(null);

  const dismiss = useCallback(() => {
    if (clearTimer.current) window.clearTimeout(clearTimer.current);
    setAgentFocus(null);
  }, []);

  useEffect(() => {
    if (!socket) return;

    const onToolStarted = (p) => {
      if (p && p.name === "focus_world") {
        const args = p.args || {};
        setAgentFocus({
          kind: args.target_kind || "—",
          target: args.target || "",
          label: `resolving ${args.target_kind || ""} ${args.target || ""}…`.trim(),
          lat: 0,
          lng: 0,
          altitude: args.altitude,
          pending: true,
        });
      }
    };

    const onFocus = (p) => {
      setAgentFocus(p);
      setFocusTarget({ ...p, _seq: Date.now() });
      if (clearTimer.current) window.clearTimeout(clearTimer.current);
      clearTimer.current = window.setTimeout(() => setAgentFocus(null), 6000);
    };

    socket.on("tool_started", onToolStarted);
    socket.on("focus_world", onFocus);
    return () => {
      socket.off("tool_started", onToolStarted);
      socket.off("focus_world", onFocus);
      if (clearTimer.current) window.clearTimeout(clearTimer.current);
    };
  }, [socket]);

  return { agentFocus, focusTarget, dismiss };
}

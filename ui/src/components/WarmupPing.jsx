import React, { useEffect } from "react";

export default function WarmupPing() {
  useEffect(() => {
    // Fire-and-forget warmup. Don’t block UI.
    fetch("/api/health", { headers: { Accept: "application/json" } }).catch(
      () => {}
    );
  }, []);

  // ✅ Render a zero-size, non-interactive node (belt + suspenders for iOS)
  return (
    <span
      aria-hidden="true"
      style={{
        position: "absolute",
        width: 0,
        height: 0,
        overflow: "hidden",
        pointerEvents: "none",
      }}
    />
  );
}
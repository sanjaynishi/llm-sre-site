import React, { useEffect } from "react";

export default function WarmupPing() {
  useEffect(() => {
    // Fire-and-forget warmup. Don’t block UI.
    fetch("/api/health", { headers: { Accept: "application/json" } }).catch(() => {});
  }, []);

  return null;
}
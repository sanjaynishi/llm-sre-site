import { useEffect, useState } from "react";

export default function LocalTime() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const formatted = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }).format(now);

  return (
    <div
      style={{
        fontSize: "0.85rem",
        color: "#6b7280", // tailwind gray-500
        whiteSpace: "nowrap",
      }}
      title="Local system time"
    >
      🕒 {formatted} (Local)
    </div>
  );
}
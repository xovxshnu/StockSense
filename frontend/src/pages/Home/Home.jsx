import { useEffect, useState } from "react";
import { API_BASE_URL, getHealth } from "../../services/api.js";

// Placeholder page proving frontend -> backend wiring. Replace/remove per feature.
export default function Home() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    getHealth()
      .then((d) => setStatus(d.status))
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>StockSense</h1>
      <p>API: {API_BASE_URL || "(not configured)"}</p>
      <p>Backend status: {status}</p>
    </main>
  );
}

import { useEffect, useState } from "react";

import { healthLabel, type HealthState } from "./health";

type HealthResponse = {
  status: string;
  service: string;
  version: string;
};

const stages = [
  ["Bronze", "Immutable source observations"],
  ["Silver", "Normalized entities and ingestion runs"],
  ["Gold", "Reproducible metric interfaces"],
] as const;

export function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [version, setVersion] = useState("—");

  useEffect(() => {
    const controller = new AbortController();
    const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";
    fetch(`${baseUrl}/health`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Health request failed");
        return (await response.json()) as HealthResponse;
      })
      .then((body) => {
        setHealth(body.status === "healthy" ? "healthy" : "unavailable");
        setVersion(body.version);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setHealth("unavailable");
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Long-horizon technology signals</p>
        <h1>Signal Observatory</h1>
        <p className="lede">
          A durable data foundation for tracing how technology moves from
          research to developers, communities, and public attention.
        </p>
        <div className={`status status--${health}`}>
          <span aria-hidden="true" />
          {healthLabel(health)} · API {version}
        </div>
      </header>

      <section aria-labelledby="foundation-title">
        <div className="section-heading">
          <p>Data architecture</p>
          <h2 id="foundation-title">Built to be traced and recalculated</h2>
        </div>
        <div className="stages">
          {stages.map(([name, description], index) => (
            <article key={name}>
              <span>0{index + 1}</span>
              <h3>{name}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <footer>E00 / E01 foundation · No external collectors enabled</footer>
    </main>
  );
}

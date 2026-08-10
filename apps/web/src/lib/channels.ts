import type { SourceMapping } from "../types/api";

export type SignalChannelKey =
  "research" | "developer" | "community" | "public";

export type SignalChannelState =
  | "not_configured"
  | "configured"
  | "not_collecting"
  | "live"
  | "degraded"
  | "error";

export type SignalChannel = {
  key: SignalChannelKey;
  label: string;
  source: string;
  sourceLabel: string;
  futureSignalLabel: string;
};

export const signalChannels: SignalChannel[] = [
  {
    key: "research",
    label: "Research",
    source: "arxiv",
    sourceLabel: "arXiv",
    futureSignalLabel: "Research signal",
  },
  {
    key: "developer",
    label: "Developer",
    source: "github",
    sourceLabel: "GitHub",
    futureSignalLabel: "Developer signal",
  },
  {
    key: "community",
    label: "Community",
    source: "hacker_news",
    sourceLabel: "Hacker News",
    futureSignalLabel: "Community signal",
  },
  {
    key: "public",
    label: "Public",
    source: "wikipedia",
    sourceLabel: "Wikipedia",
    futureSignalLabel: "Public signal",
  },
];

export function mappingForChannel(
  mappings: SourceMapping[],
  channel: SignalChannel,
): SourceMapping | undefined {
  return mappings.find(
    (mapping) => mapping.source === channel.source && mapping.enabled,
  );
}

export function signalStateLabel(state: SignalChannelState): string {
  switch (state) {
    case "not_configured":
      return "Not configured";
    case "configured":
      return "Configured";
    case "not_collecting":
      return "Not collecting yet";
    case "live":
      return "Live";
    case "degraded":
      return "Degraded";
    case "error":
      return "Unavailable";
  }
}

const configurationLabels: Record<string, string> = {
  search_terms: "Configured search terms",
  search_queries: "Configured queries",
  terms: "Configured terms",
  page_titles: "Configured pages",
};

export type MappingDetail = {
  label: string;
  values: string[];
};

export function mappingDetails(mapping: SourceMapping): MappingDetail[] {
  const details: MappingDetail[] = [];
  for (const [key, value] of Object.entries(mapping.configuration)) {
    if (!Array.isArray(value)) continue;
    const values = value.filter(
      (item): item is string => typeof item === "string",
    );
    if (values.length === 0) continue;
    details.push({
      label: configurationLabels[key] ?? "Configured values",
      values,
    });
  }
  if (details.length === 0 && mapping.query) {
    details.push({ label: "Configured query", values: [mapping.query] });
  }
  if (details.length === 0 && mapping.external_identifier) {
    details.push({
      label: "Configured identifier",
      values: [mapping.external_identifier],
    });
  }
  return details;
}

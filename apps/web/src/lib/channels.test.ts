import { describe, expect, it } from "vitest";

import type { SourceMapping } from "../types/api";
import { mappingForChannel, signalChannels } from "./channels";

const arxivChannel = signalChannels.find(
  (channel) => channel.source === "arxiv",
);

if (!arxivChannel) {
  throw new Error("arXiv signal channel fixture is missing");
}

function mapping(enabled: boolean): SourceMapping {
  return {
    source: "arxiv",
    enabled,
    mapping_type: "registry",
    external_identifier: null,
    query: '"model context protocol"',
    configuration: { search_terms: ["model context protocol"] },
  };
}

describe("mappingForChannel", () => {
  it("returns only an enabled source mapping as configured", () => {
    expect(mappingForChannel([mapping(false)], arxivChannel)).toBeUndefined();
    expect(mappingForChannel([mapping(true)], arxivChannel)).toEqual(
      mapping(true),
    );
  });

  it("does not let a disabled mapping shadow an enabled mapping", () => {
    expect(
      mappingForChannel([mapping(false), mapping(true)], arxivChannel),
    ).toEqual(mapping(true));
  });
});

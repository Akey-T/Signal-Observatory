import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getArxivStatus,
  getDevelopment,
  getCoverage,
  getGithubStatus,
  getOperations,
  getRegistryStatus,
  getResearch,
  getTopicCoverage,
  getTopics,
} from "./client";
import {
  arxivStatus,
  coverageList,
  githubStatus,
  makeTopic,
  operationsOverview,
  registryStatus,
  topicResearch,
  topicCoverage,
  topicDevelopment,
} from "../test/fixtures";

function responseWith(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe("registry API client", () => {
  it("parses Registry Status from the central API layer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseWith(registryStatus));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getRegistryStatus()).resolves.toEqual(registryStatus);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/topic-registry/status",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("encodes Topic search, filters and pagination", async () => {
    const body = { items: [makeTopic(1)], total: 1, limit: 24, offset: 24 };
    const fetchMock = vi.fn().mockResolvedValue(responseWith(body));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getTopics({
        search: "MCP server",
        category: "ai-systems",
        status: "active",
        limit: 24,
        offset: 24,
      }),
    ).resolves.toEqual(body);
    const requestedUrl = String(fetchMock.mock.calls[0]?.[0]);
    expect(requestedUrl).toContain("search=MCP+server");
    expect(requestedUrl).toContain("category=ai-systems");
    expect(requestedUrl).toContain("status=active");
    expect(requestedUrl).toContain("limit=24");
    expect(requestedUrl).toContain("offset=24");
  });

  it("surfaces an explicit API failure without fallback data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseWith({}, 503)));
    await expect(getRegistryStatus()).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
    });
  });

  it("loads persisted Research observations for an encoded Topic slug", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseWith(topicResearch));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getResearch("model context/protocol")).resolves.toEqual(
      topicResearch,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/topics/model%20context%2Fprotocol/research",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("loads the arXiv collector status without inventing a live state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseWith(arxivStatus));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getArxivStatus()).resolves.toEqual(arxivStatus);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sources/arxiv/status",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("loads persisted Developer observations for an encoded Topic slug", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseWith(topicDevelopment));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getDevelopment("model context/protocol")).resolves.toEqual(
      topicDevelopment,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/topics/model%20context%2Fprotocol/development",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("loads GitHub collector status without exposing a credential", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseWith(githubStatus));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getGithubStatus()).resolves.toEqual(githubStatus);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sources/github/status",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
    expect(githubStatus).not.toHaveProperty("token");
  });

  it("loads Operations and encodes Coverage Ledger filters", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(responseWith(operationsOverview))
      .mockResolvedValueOnce(responseWith(coverageList))
      .mockResolvedValueOnce(responseWith(topicCoverage));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getOperations()).resolves.toEqual(operationsOverview);
    await expect(
      getCoverage({
        source: "arxiv",
        status: "partial",
        topic: "model context protocol",
      }),
    ).resolves.toEqual(coverageList);
    await expect(getTopicCoverage("model context/protocol")).resolves.toEqual(
      topicCoverage,
    );

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/operations");
    const coverageUrl = String(fetchMock.mock.calls[1]?.[0]);
    expect(coverageUrl).toContain("source=arxiv");
    expect(coverageUrl).toContain("status=partial");
    expect(coverageUrl).toContain("topic=model+context+protocol");
    expect(String(fetchMock.mock.calls[2]?.[0])).toBe(
      "/api/topics/model%20context%2Fprotocol/coverage",
    );
  });
});

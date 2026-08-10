import { afterEach, describe, expect, it, vi } from "vitest";

import { getRegistryStatus, getTopics } from "./client";
import { makeTopic, registryStatus } from "../test/fixtures";

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
});

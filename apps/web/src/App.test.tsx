import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
  ApiError,
  getArxivStatus,
  getCategories,
  getDevelopment,
  getGithubStatus,
  getResearch,
  getRegistryStatus,
  getTopic,
  getTopics,
} from "./api/client";
import {
  categories,
  arxivStatus,
  liveTopicResearch,
  githubStatus,
  liveTopicDevelopment,
  makeTopic,
  modelContextProtocol,
  registryStatus,
  topicResearch,
  topicDevelopment,
} from "./test/fixtures";
import type { TopicListResponse, TopicsQuery } from "./types/api";

vi.mock("./api/client", () => {
  class MockApiError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }
  return {
    ApiError: MockApiError,
    getCategories: vi.fn(),
    getArxivStatus: vi.fn(),
    getDevelopment: vi.fn(),
    getGithubStatus: vi.fn(),
    getResearch: vi.fn(),
    getRegistryStatus: vi.fn(),
    getTopic: vi.fn(),
    getTopics: vi.fn(),
  };
});

const mockedGetCategories = vi.mocked(getCategories);
const mockedGetArxivStatus = vi.mocked(getArxivStatus);
const mockedGetDevelopment = vi.mocked(getDevelopment);
const mockedGetGithubStatus = vi.mocked(getGithubStatus);
const mockedGetResearch = vi.mocked(getResearch);
const mockedGetRegistryStatus = vi.mocked(getRegistryStatus);
const mockedGetTopic = vi.mocked(getTopic);
const mockedGetTopics = vi.mocked(getTopics);

function topicResponse(
  items = Array.from({ length: 36 }, (_, index) => makeTopic(index + 1)),
  total = items.length,
  query: TopicsQuery = {},
): TopicListResponse {
  return {
    items,
    total,
    limit: query.limit ?? 500,
    offset: query.offset ?? 0,
  };
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("scrollTo", vi.fn());
  mockedGetCategories.mockResolvedValue(categories);
  mockedGetArxivStatus.mockResolvedValue(arxivStatus);
  mockedGetDevelopment.mockResolvedValue(topicDevelopment);
  mockedGetGithubStatus.mockResolvedValue(githubStatus);
  mockedGetResearch.mockResolvedValue(topicResearch);
  mockedGetRegistryStatus.mockResolvedValue(registryStatus);
  mockedGetTopic.mockResolvedValue(modelContextProtocol);
  mockedGetTopics.mockResolvedValue(
    topicResponse(
      [
        modelContextProtocol,
        ...Array.from({ length: 35 }, (_, index) => makeTopic(index + 1)),
      ],
      101,
    ),
  );
});

describe("Overview", () => {
  it("shows dynamic stats, three Featured Topics and thirty Supporting Topics", async () => {
    const { container } = renderApp("/");

    expect(
      await screen.findByText("Three editorially prioritized topics."),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("featured-topic")).toHaveLength(3);
    expect(container.querySelectorAll(".compact-topic")).toHaveLength(30);
    expect(screen.getByText("Explore all 101 topics")).toBeInTheDocument();
    expect(
      screen.getByText("Five domains. One curated registry."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Registry health, not collector health."),
    ).toBeInTheDocument();
    expect(screen.getByText("Not initialized")).toBeInTheDocument();
    expect(
      screen.getByText(
        "arXiv + GitHub interfaces implemented · 2 channels pending",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/External collectors have not started/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /trending/i }),
    ).not.toBeInTheDocument();
  });

  it("marks Research live only after a successful healthy arXiv run", async () => {
    mockedGetArxivStatus.mockResolvedValue({
      ...arxivStatus,
      collector_state: "healthy",
      last_run_at: "2026-08-09T06:30:00Z",
      last_successful_run_at: "2026-08-09T06:30:00Z",
      last_run_status: "succeeded",
    });
    renderApp("/");

    expect(await screen.findByText("arXiv · Live")).toBeInTheDocument();
    expect(screen.getByText("GitHub · Not live")).toBeInTheDocument();
    expect(screen.getAllByText("Configured / ready")).toHaveLength(2);
    expect(
      screen.getByText(
        "Topic Registry ready · Research collector live · Developer collector not live",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Research collector")).toBeInTheDocument();
  });

  it("marks Developer live only after a successful healthy GitHub snapshot", async () => {
    mockedGetGithubStatus.mockResolvedValue({
      ...githubStatus,
      auth_configured: true,
      collector_state: "healthy",
      last_run_at: "2026-08-11T03:01:00Z",
      last_run_status: "succeeded",
      last_snapshot_at: "2026-08-11T03:00:00Z",
      last_successful_snapshot_at: "2026-08-11T03:01:00Z",
    });
    renderApp("/");

    expect(await screen.findByText("GitHub · Live")).toBeInTheDocument();
    expect(screen.getByText("Developer collector")).toBeInTheDocument();
  });
});

describe("Topic Explorer", () => {
  it("uses API search, category and status filters", async () => {
    mockedGetTopics.mockImplementation(async (query = {}) => {
      if (query.search === "MCP")
        return topicResponse([modelContextProtocol], 1, query);
      return topicResponse(
        Array.from({ length: 24 }, (_, index) => makeTopic(index + 1)),
        50,
        query,
      );
    });
    const user = userEvent.setup();
    renderApp("/topics");
    await screen.findByText("Registry results");

    await user.type(screen.getByLabelText("Search topics or aliases"), "MCP");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(mockedGetTopics).toHaveBeenCalledWith(
        expect.objectContaining({ search: "MCP" }),
        expect.any(AbortSignal),
      ),
    );
    expect(
      await screen.findByText("Model Context Protocol"),
    ).toBeInTheDocument();

    await user.selectOptions(
      screen.getByLabelText("Category"),
      "software-development",
    );
    await waitFor(() =>
      expect(mockedGetTopics).toHaveBeenCalledWith(
        expect.objectContaining({ category: "software-development" }),
        expect.any(AbortSignal),
      ),
    );

    await user.selectOptions(screen.getByLabelText("Status"), "active");
    await waitFor(() =>
      expect(mockedGetTopics).toHaveBeenCalledWith(
        expect.objectContaining({ status: "active" }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("paginates with the API and resets page state through the URL", async () => {
    mockedGetTopics.mockImplementation(async (query = {}) =>
      topicResponse(
        Array.from({ length: 24 }, (_, index) =>
          makeTopic((query.offset ?? 0) + index + 1),
        ),
        50,
        query,
      ),
    );
    const user = userEvent.setup();
    renderApp("/topics");

    expect(await screen.findByText(/1–24/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() =>
      expect(mockedGetTopics).toHaveBeenCalledWith(
        expect.objectContaining({ limit: 24, offset: 24 }),
        expect.any(AbortSignal),
      ),
    );
    expect(await screen.findByText(/25–48/)).toBeInTheDocument();
  });

  it("shows a useful empty state and clears filters", async () => {
    mockedGetTopics.mockResolvedValue(topicResponse([], 0));
    const user = userEvent.setup();
    renderApp("/topics?search=not-present");

    expect(
      await screen.findByText("No monitored topics match these filters."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByLabelText("Search topics or aliases")).toHaveValue("");
  });

  it("shows a retryable API error without displaying zero topics", async () => {
    mockedGetTopics.mockRejectedValue(new Error("offline"));
    renderApp("/topics");

    expect(
      await screen.findByText("Topic Registry could not be loaded."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText("0 monitored topics")).not.toBeInTheDocument();
  });
});

describe("Topic Detail", () => {
  it("shows configured Research as not collecting before its first successful run", async () => {
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByRole("heading", { name: "Model Context Protocol" }),
    ).toBeInTheDocument();
    expect(screen.getByText("MCP")).toBeInTheDocument();
    expect(screen.getByText("MCP server")).toBeInTheDocument();
    expect(screen.getByText("Monitoring Channels")).toBeInTheDocument();
    expect(screen.getAllByText("Configured")).toHaveLength(4);
    expect(screen.getAllByText("Not collecting yet")).toHaveLength(4);
    expect(
      screen.getByText(/no successful arXiv collection yet/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/It is not popularity or trend strength/),
    ).toBeInTheDocument();
  });

  it("shows live Research counts and the latest persisted paper", async () => {
    mockedGetResearch.mockResolvedValue(liveTopicResearch);
    renderApp("/topics/model-context-protocol");

    expect(await screen.findByText("Live")).toBeInTheDocument();
    expect(screen.getAllByText("Not collecting yet")).toHaveLength(3);
    expect(screen.getByText("Papers · 7 days")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Papers · 30 days")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Authors · 30 days")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("Latest Research")).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Reliable Context Exchange for Agentic Systems",
      }),
    ).toHaveAttribute("href", "https://arxiv.org/abs/2608.01234");
  });

  it("shows live Developer counts, snapshot deltas and match evidence", async () => {
    mockedGetDevelopment.mockResolvedValue(liveTopicDevelopment);
    renderApp("/topics/model-context-protocol");

    expect(await screen.findByText("Tracked Repositories")).toBeInTheDocument();
    expect(screen.getByText("Repositories")).toBeInTheDocument();
    expect(screen.getByText("12,500")).toBeInTheDocument();
    expect(
      screen.getByText(/Snapshot change: \+42 stars · \+7 forks/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "modelcontextprotocol/servers" }),
    ).toHaveAttribute(
      "href",
      "https://github.com/modelcontextprotocol/servers",
    );
    expect(screen.getByText("Match evidence")).toBeInTheDocument();
  });

  it("shows a truthful live zero-repository Developer state", async () => {
    mockedGetDevelopment.mockResolvedValue({
      ...topicDevelopment,
      state: "live",
    });
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByText(
        "Collector live; no repositories matched this Topic.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /zero count is a valid result for the curated GitHub mapping/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows a truthful live zero-paper state", async () => {
    mockedGetResearch.mockResolvedValue({ ...topicResearch, state: "live" });
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByText(
        "Collector live; no matched papers observed yet.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/zero count is a valid result/i),
    ).toBeInTheDocument();
  });

  it("keeps historical papers visible while Research is degraded", async () => {
    mockedGetResearch.mockResolvedValue({
      ...liveTopicResearch,
      state: "degraded",
      collector_error: "upstream unavailable",
    });
    renderApp("/topics/model-context-protocol");

    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    expect(
      screen.getByText(/persisted history remains available below/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reliable Context Exchange for Agentic Systems"),
    ).toBeInTheDocument();
  });

  it("contains a Research API failure to the Research surface", async () => {
    mockedGetResearch.mockRejectedValue(new Error("research offline"));
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByText(
        "Research observations are temporarily unavailable.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Not collecting yet")).toHaveLength(3);
    expect(
      screen.getByRole("heading", { name: "Model Context Protocol" }),
    ).toBeInTheDocument();
  });

  it("contains a Developer API failure to the Developer surface", async () => {
    mockedGetDevelopment.mockRejectedValue(new Error("github offline"));
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByText(
        "Developer observations are temporarily unavailable.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry Developer" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Model Context Protocol" }),
    ).toBeInTheDocument();
  });

  it("shows a clear 404 Topic state", async () => {
    mockedGetTopic.mockRejectedValue(new ApiError("not found", 404));
    renderApp("/topics/not-present");

    expect(
      await screen.findByText("This monitored topic was not found."),
    ).toBeInTheDocument();
    expect(screen.getByText("Return to Topic Explorer")).toBeInTheDocument();
  });
});

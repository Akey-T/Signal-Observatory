import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
  ApiError,
  getCategories,
  getRegistryStatus,
  getTopic,
  getTopics,
} from "./api/client";
import {
  categories,
  makeTopic,
  modelContextProtocol,
  registryStatus,
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
    getRegistryStatus: vi.fn(),
    getTopic: vi.fn(),
    getTopics: vi.fn(),
  };
});

const mockedGetCategories = vi.mocked(getCategories);
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
    expect(
      screen.queryByRole("heading", { name: /trending/i }),
    ).not.toBeInTheDocument();
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
  it("shows canonical data, aliases, mappings and truthful observation placeholders", async () => {
    renderApp("/topics/model-context-protocol");

    expect(
      await screen.findByRole("heading", { name: "Model Context Protocol" }),
    ).toBeInTheDocument();
    expect(screen.getByText("MCP")).toBeInTheDocument();
    expect(screen.getByText("MCP server")).toBeInTheDocument();
    expect(screen.getByText("Monitoring Channels")).toBeInTheDocument();
    expect(screen.getAllByText("Configured")).toHaveLength(4);
    expect(
      screen.getByText(/No external observations yet/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Not collecting yet")).toHaveLength(4);
    expect(
      screen.getByText(/It is not popularity or trend strength/),
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

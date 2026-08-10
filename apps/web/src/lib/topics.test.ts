import { describe, expect, it } from "vitest";

import { categories, makeTopic } from "../test/fixtures";
import { selectFeaturedTopics } from "./topics";

describe("selectFeaturedTopics", () => {
  const candidates = [
    makeTopic(1, { category: "ai-systems", monitoring_priority: 100 }),
    makeTopic(2, { category: "ai-systems", monitoring_priority: 99 }),
    makeTopic(3, { category: "software-development", monitoring_priority: 96 }),
    makeTopic(4, { category: "data-systems", monitoring_priority: 94 }),
    makeTopic(5, { category: "data-systems", monitoring_priority: 93 }),
  ];

  it("returns exactly three active topics with root-category diversity", () => {
    const selected = selectFeaturedTopics(candidates, categories);
    expect(selected).toHaveLength(3);
    expect(selected.map((topic) => topic.category)).toEqual([
      "ai-systems",
      "software-development",
      "data-systems",
    ]);
  });

  it("is deterministic for the same logical Registry input", () => {
    const forward = selectFeaturedTopics(candidates, categories).map(
      (topic) => topic.slug,
    );
    const reversed = selectFeaturedTopics(
      [...candidates].reverse(),
      categories,
    ).map((topic) => topic.slug);
    expect(reversed).toEqual(forward);
  });

  it("excludes paused and deprecated topics", () => {
    const inactive = [
      makeTopic(10, { status: "paused", monitoring_priority: 100 }),
      makeTopic(11, { status: "deprecated", monitoring_priority: 100 }),
      ...candidates,
    ];
    expect(selectFeaturedTopics(inactive, categories)).not.toContainEqual(
      expect.objectContaining({ status: "paused" }),
    );
    expect(selectFeaturedTopics(inactive, categories)).not.toContainEqual(
      expect.objectContaining({ status: "deprecated" }),
    );
  });
});

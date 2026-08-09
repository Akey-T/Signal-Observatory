import { describe, expect, it } from "vitest";

import { healthLabel } from "./health";

describe("healthLabel", () => {
  it("maps the healthy state to a useful status", () => {
    expect(healthLabel("healthy")).toBe("Foundation online");
  });
});

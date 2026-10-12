import { describe, expect, it } from "vitest";
import { CLASS_META, fmtBytes, prettify, sourceLabel } from "./format";

describe("format helpers", () => {
  it("formats byte sizes", () => {
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(2048)).toBe("2.0 KB");
    expect(fmtBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("labels sources by file name, then URL host/path, then id", () => {
    expect(sourceLabel({ id: "DS-1", file_name: "a.jpg", source_url: null })).toBe("a.jpg");
    expect(sourceLabel({ id: "DS-1", file_name: null, source_url: "https://ex.com/p/x.png" })).toBe("ex.com/p/x.png");
    expect(sourceLabel({ id: "DS-1", file_name: null, source_url: null })).toBe("DS-1");
  });

  it("defines all four risk levels with the spec labels", () => {
    expect(Object.keys(CLASS_META)).toEqual(["likely_authentic", "uncertain", "potentially_manipulated", "high_risk"]);
    expect(CLASS_META.high_risk.label).toBe("High Risk — Possible Deepfake");
  });

  it("prettifies snake case", () => expect(prettify("ai_generated_declared")).toBe("ai generated declared"));
});

import { describe, expect, it } from "vitest";

import { assertSafeSegment, buildUpstreamUrl, upstreamSegments } from "../../apps/web/src/lib/bff";

describe("BFF 上游地址", () => {
  it("拼接路径和查询串，并去掉基址末尾斜杠", () => {
    expect(buildUpstreamUrl("http://api:8000/", ["api", "meta"], "?x=1")).toBe(
      "http://api:8000/api/meta?x=1",
    );
  });

  it("把业务接口补回 /api 前缀，并拒绝版本段", () => {
    expect(upstreamSegments(["meta"])).toEqual(["api", "meta"]);
    expect(upstreamSegments(["healthz"])).toEqual(["healthz"]);
    expect(() => upstreamSegments(["v1", "meta"])).toThrow(/版本前缀/);
    expect(buildUpstreamUrl("http://127.0.0.1:8000", upstreamSegments(["meta"]), "")).toBe(
      "http://127.0.0.1:8000/api/meta",
    );
  });

  it("拒绝路径穿越", () => {
    expect(() => assertSafeSegment("..")).toThrow(/非法路径/);
    expect(() => assertSafeSegment("a/b")).toThrow(/非法路径/);
    expect(() => buildUpstreamUrl("http://api:8000", [".."], "")).toThrow(/非法路径/);
  });
});

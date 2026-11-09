const UNSAFE_SEGMENT = /[\\/]/;

export function assertSafeSegment(segment: string): void {
  if (
    segment.length === 0 ||
    segment === "." ||
    segment === ".." ||
    UNSAFE_SEGMENT.test(segment)
  ) {
    throw new Error("Invalid path");
  }
}

const DIRECT_PROBES = new Set(["healthz", "readyz"]);

export function upstreamSegments(segments: string[]): string[] {
  if (segments.some((segment) => segment.toLowerCase() === "v1")) {
    throw new Error("Path must not include a version prefix");
  }
  if (segments.length === 1 && DIRECT_PROBES.has(segments[0])) {
    return segments;
  }
  return ["api", ...segments];
}

export function buildUpstreamUrl(base: string, segments: string[], search: string): string {
  segments.forEach(assertSafeSegment);
  const trimmed = base.replace(/\/$/, "");
  const path = segments.map((segment) => encodeURIComponent(segment)).join("/");
  const query = search && !search.startsWith("?") ? `?${search}` : search;
  return `${trimmed}/${path}${query}`;
}

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type ApiModule = typeof import("../api");

let mod: ApiModule;

beforeEach(async () => {
  vi.resetModules();
  window.localStorage.clear();
  mod = await import("../api");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

function headerOf(init: RequestInit | undefined, name: string): string | null {
  return new Headers(init?.headers ?? undefined).get(name);
}

describe("apiGet query building (buildUrl)", () => {
  it("serializes scalars, arrays; skips undefined/null/empty-string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await mod.apiGet("/api/v1/market/stocks", {
      limit: 10,
      tags: ["x", "y"],
      empty: "",
      missing: undefined,
      nil: null,
      zero: 0,
    });

    const parsed = new URL(fetchMock.mock.calls[0][0] as string);
    expect(parsed.searchParams.get("limit")).toBe("10");
    expect(parsed.searchParams.getAll("tags")).toEqual(["x", "y"]);
    expect(parsed.searchParams.has("empty")).toBe(false);
    expect(parsed.searchParams.has("missing")).toBe(false);
    expect(parsed.searchParams.has("nil")).toBe(false);
    expect(parsed.searchParams.get("zero")).toBe("0");
  });
});

describe("ApiError", () => {
  it("throws ApiError with detail message and status on non-ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "scanner offline" }, 503))
    );

    const err = await mod.apiGet("/api/v1/scanner/presets").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(mod.ApiError);
    expect(err).toMatchObject({
      name: "ApiError",
      message: "scanner offline",
      status: 503,
      path: "/api/v1/scanner/presets",
    });
  });
});

describe("session token flow", () => {
  it("401 triggers session fetch + retry once with fresh token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "missing session token" }, 401))
      .mockResolvedValueOnce(jsonResponse({ token: "fresh-token", expires_in: 86400 }))
      .mockResolvedValueOnce(jsonResponse({ rows: [1, 2] }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await mod.apiGet<{ rows: number[] }>("/api/v1/backtest/jobs");

    expect(result).toEqual({ rows: [1, 2] });
    expect(fetchMock).toHaveBeenCalledTimes(3);

    expect(headerOf(fetchMock.mock.calls[0][1] as RequestInit, "X-Session-Token")).toBeNull();

    expect(String(fetchMock.mock.calls[1][0])).toContain("/api/v1/auth/session");
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe("POST");
    expect(headerOf(fetchMock.mock.calls[1][1] as RequestInit, "X-Session-Token")).toBeNull();

    expect(headerOf(fetchMock.mock.calls[2][1] as RequestInit, "X-Session-Token")).toBe(
      "fresh-token"
    );
    expect(window.localStorage.getItem("mi_session")).toBe("fresh-token");
  });

  it("retries exactly once; second 401 throws ApiError", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "missing session token" }, 401))
      .mockResolvedValueOnce(jsonResponse({ token: "t2", expires_in: 86400 }))
      .mockResolvedValueOnce(jsonResponse({ detail: "still unauthorized" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    const err = await mod.apiGet("/api/v1/risk/exposure").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(mod.ApiError);
    expect(err).toMatchObject({ status: 401, message: "still unauthorized" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("session POST itself sends no token header and does not retry", async () => {
    window.localStorage.setItem("mi_session", "stale-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ token: "new-token", expires_in: 86400 }));
    vi.stubGlobal("fetch", fetchMock);

    const body = await mod.apiPost<{ token: string }>("/api/v1/auth/session");

    expect(body).toEqual({ token: "new-token", expires_in: 86400 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/auth/session");
    expect((init as RequestInit).method).toBe("POST");
    expect(headerOf(init as RequestInit, "X-Session-Token")).toBeNull();
  });

  it("apiPost attaches stored token to normal routes", async () => {
    window.localStorage.setItem("mi_session", "stored-token");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "order-1" }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await mod.apiPost<{ id: string }>("/api/v1/paper/orders", {
      symbol: "TCS",
    });

    expect(res).toEqual({ id: "order-1" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(headerOf(init, "X-Session-Token")).toBe("stored-token");
    expect(headerOf(init, "Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ symbol: "TCS" }));
  });
});

import { ApiError, api } from "@/lib/api/client";

function mockFetch(status: number, body: unknown) {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
}

describe("api client", () => {
  it("unwraps the {data, meta} envelope and sends credentials", async () => {
    const spy = mockFetch(200, { data: { id: "1" }, meta: {} });
    const result = await api.get<{ id: string }>("/users/me");
    expect(result).toEqual({ id: "1" });
    const [url, init] = spy.mock.calls[0]!;
    expect(url).toBe("/api/v1/users/me");
    expect(init?.credentials).toBe("include");
  });

  it("serialises JSON bodies with the right content type", async () => {
    const spy = mockFetch(201, { data: { ok: true }, meta: {} });
    await api.post("/auth/login", { email: "a@b.co", password: "x" });
    const init = spy.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ email: "a@b.co", password: "x" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("throws a typed ApiError carrying code and field details", async () => {
    mockFetch(422, {
      error: { code: "VALIDATION_ERROR", message: "Some fields are invalid.", details: { fields: { email: ["bad"] } } },
    });
    const err = await api.get("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.code).toBe("VALIDATION_ERROR");
    expect(apiErr.fieldErrors).toEqual({ email: ["bad"] });
  });

  it("falls back to a generic error for non-JSON failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>", { status: 502 }));
    const err = (await api.get("/x").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("HTTP_ERROR");
    expect(err.status).toBe(502);
  });
});

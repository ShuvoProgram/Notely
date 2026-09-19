import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LoginForm } from "@/features/auth/components/login-form";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("LoginForm", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/providers")) return jsonResponse(200, { data: [], meta: {} });
      if (url.endsWith("/auth/login")) {
        return jsonResponse(401, {
          error: { code: "INVALID_CREDENTIALS", message: "Incorrect email or password.", details: {} },
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
  });

  it("validates client-side before submitting", async () => {
    const user = userEvent.setup();
    renderWithClient(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.endsWith("/auth/login"))).toBe(false);
  });

  it("shows a friendly message for invalid credentials", async () => {
    const user = userEvent.setup();
    renderWithClient(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/incorrect email or password/i));
  });

  it("surfaces an OAuth error passed from the callback redirect", () => {
    renderWithClient(<LoginForm initialError="oauth_denied" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/cancelled/i);
  });

  it("does not render provider buttons when none are configured", async () => {
    renderWithClient(<LoginForm />);
    await waitFor(() => expect(screen.queryByText(/continue with/i)).not.toBeInTheDocument());
  });
});

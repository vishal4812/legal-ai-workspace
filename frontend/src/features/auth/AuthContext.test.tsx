import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { LoginPage } from "../../pages/LoginPage";
import { RegisterPage } from "../../pages/RegisterPage";
import { authApi } from "./authApi";
import { AuthProvider, useAuth } from "./AuthContext";
import type { User } from "./types";

vi.mock("./authApi", () => ({
  authApi: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock("../../services/apiClient", () => ({
  setAccessToken: vi.fn(),
  setAuthFailureHandler: vi.fn(),
}));

const user: User = {
  id: "c1be32c3-826a-4d6a-b4c8-37b286defa04",
  email: "lawyer@example.com",
  first_name: "Avery",
  last_name: "Counsel",
  is_active: true,
  is_verified: false,
  created_at: "2026-08-08T00:00:00Z",
  last_login_at: "2026-08-08T01:00:00Z",
};

function TestProviders({ children }: PropsWithChildren) {
  return (
    <MemoryRouter>
      <AuthProvider>{children}</AuthProvider>
    </MemoryRouter>
  );
}

function AuthHarness() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.isLoading ? "loading" : auth.user?.email ?? "anonymous"}</span>
      <button onClick={() => void auth.login({ email: user.email, password: "secure-password" })}>Log in</button>
      <button onClick={() => void auth.logout()}>Log out</button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(authApi.restoreSession).mockReturnValue(new Promise(() => undefined));
});

describe("authentication pages", () => {
  test("login page renders", () => {
    render(<LoginPage />, { wrapper: TestProviders });

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  test("registration page renders", () => {
    render(<RegisterPage />, { wrapper: TestProviders });

    expect(screen.getByRole("heading", { name: "Create account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "8");
  });

  test("failed login displays a safe error", async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error("Could not validate credentials"));
    render(<LoginPage />, { wrapper: TestProviders });

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: user.email } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not validate credentials");
  });
});

describe("authentication state", () => {
  test("successful login updates the current user", async () => {
    vi.mocked(authApi.restoreSession).mockRejectedValue(new Error("No session"));
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "access-token",
      token_type: "bearer",
      expires_in: 1800,
    });
    vi.mocked(authApi.me).mockResolvedValue(user);
    render(<AuthHarness />, { wrapper: TestProviders });
    await screen.findByText("anonymous");

    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText(user.email)).toBeInTheDocument();
  });

  test("logout clears authentication state", async () => {
    vi.mocked(authApi.restoreSession).mockResolvedValue(user);
    vi.mocked(authApi.logout).mockResolvedValue();
    render(<AuthHarness />, { wrapper: TestProviders });
    await screen.findByText(user.email);

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
    expect(authApi.logout).toHaveBeenCalledOnce();
  });
});

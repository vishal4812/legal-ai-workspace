import { render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

import { App } from "./App";

vi.mock("../features/auth/authApi", () => ({
  authApi: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock("../services/apiClient", () => ({
  setAccessToken: vi.fn(),
  setAuthFailureHandler: vi.fn(),
}));

import { authApi } from "../features/auth/authApi";

beforeEach(() => {
  vi.mocked(authApi.restoreSession).mockRejectedValue(new Error("No session"));
});

test("renders the unauthenticated application shell", async () => {
  render(<App />);

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

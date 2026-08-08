import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { DashboardPage } from "../../pages/DashboardPage";
import { AuthContext, type AuthContextValue } from "./AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";
import type { User } from "./types";

const user: User = {
  id: "c1be32c3-826a-4d6a-b4c8-37b286defa04",
  email: "lawyer@example.com",
  first_name: "Avery",
  last_name: "Counsel",
  is_active: true,
  is_verified: false,
  created_at: "2026-08-08T00:00:00Z",
  last_login_at: null,
};

function renderProtected(currentUser: User | null) {
  const value: AuthContextValue = {
    user: currentUser,
    isLoading: false,
    error: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  };

  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<DashboardPage />} />
          </Route>
          <Route path="/login" element={<h1>Sign in</h1>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

test("protected route redirects an unauthenticated user", () => {
  renderProtected(null);

  expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("protected route allows an authenticated user", () => {
  renderProtected(user);

  expect(screen.getByRole("heading", { name: "Welcome to LEGAL MASTER" })).toBeInTheDocument();
  expect(screen.getByText(user.email)).toBeInTheDocument();
});

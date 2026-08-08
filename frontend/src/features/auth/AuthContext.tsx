import { isAxiosError } from "axios";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { setAccessToken, setAuthFailureHandler } from "../../services/apiClient";
import { authApi } from "./authApi";
import type { LoginInput, RegistrationInput, User } from "./types";

export interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegistrationInput) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

function authenticationMessage(error: unknown): string {
  if (isAxiosError<{ detail?: string }>(error)) {
    return error.response?.data?.detail ?? "Authentication request failed";
  }
  return error instanceof Error ? error.message : "Authentication request failed";
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setAuthFailureHandler(clearSession);
    let active = true;

    void authApi
      .restoreSession()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch(() => {
        if (active) clearSession();
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
      setAuthFailureHandler(null);
    };
  }, [clearSession]);

  const login = useCallback(async (input: LoginInput) => {
    setError(null);
    try {
      const tokens = await authApi.login(input);
      setAccessToken(tokens.access_token);
      setUser(await authApi.me());
    } catch (requestError) {
      const message = authenticationMessage(requestError);
      setError(message);
      throw new Error(message);
    }
  }, []);

  const register = useCallback(
    async (input: RegistrationInput) => {
      setError(null);
      try {
        await authApi.register(input);
        await login({ email: input.email, password: input.password });
      } catch (requestError) {
        const message = authenticationMessage(requestError);
        setError(message);
        throw new Error(message);
      }
    },
    [login],
  );

  const logout = useCallback(async () => {
    setError(null);
    try {
      await authApi.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      error,
      login,
      register,
      logout,
      clearError: () => setError(null),
    }),
    [error, isLoading, login, logout, register, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

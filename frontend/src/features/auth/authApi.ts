import { apiClient, refreshAccessToken } from "../../services/apiClient";
import type { LoginInput, RegistrationInput, TokenResponse, User } from "./types";

export const authApi = {
  async register(input: RegistrationInput): Promise<User> {
    const { data } = await apiClient.post<User>("/api/v1/auth/register", input);
    return data;
  },

  async login(input: LoginInput): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>("/api/v1/auth/login", input);
    return data;
  },

  async me(): Promise<User> {
    const { data } = await apiClient.get<User>("/api/v1/auth/me");
    return data;
  },

  async restoreSession(): Promise<User> {
    await refreshAccessToken();
    return this.me();
  },

  async logout(): Promise<void> {
    await apiClient.post("/api/v1/auth/logout");
  },
};

import { apiPost, clearToken, setToken } from "./api";

export type Role = "admin" | "agent";

export interface User {
  id: number;
  username: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function login(username: string, password: string): Promise<User> {
  const data = await apiPost<TokenResponse>("/api/auth/login", { username, password });
  setToken(data.access_token);
  return data.user;
}

export function logout() {
  clearToken();
}

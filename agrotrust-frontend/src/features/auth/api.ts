import { apiRequest } from "@/lib/api/client";
import type { AuthTokens, Role, User } from "@/types/api";

export interface RegisterPayload {
  phone: string;
  password: string;
  full_name: string;
  role: Role;
  email?: string;
}

export function register(payload: RegisterPayload): Promise<User> {
  return apiRequest<User>("/api/v1/auth/register", {
    method: "POST",
    body: payload,
    skipAuth: true,
  });
}

export function login(phone: string, password: string): Promise<AuthTokens> {
  return apiRequest<AuthTokens>("/api/v1/auth/login", {
    method: "POST",
    body: { phone, password },
    skipAuth: true,
  });
}

export function fetchProfile(): Promise<User> {
  return apiRequest<User>("/api/v1/me");
}

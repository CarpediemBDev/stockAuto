import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  username: string | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  setAuth: (token: string, username: string) => void;
  clearAuth: () => void;
  setInitialized: (val: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  username: null,
  isAuthenticated: false,
  isInitialized: false,
  setAuth: (token, username) => set({
    accessToken: token,
    username: username,
    isAuthenticated: true,
  }),
  clearAuth: () => set({
    accessToken: null,
    username: null,
    isAuthenticated: false,
  }),
  setInitialized: (val) => set({
    isInitialized: val,
  }),
}));

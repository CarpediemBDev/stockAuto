import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  username: string | null;
  role: string | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  setAuth: (token: string, username: string, role: string) => void;
  clearAuth: () => void;
  setInitialized: (val: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  username: null,
  role: null,
  isAuthenticated: false,
  isInitialized: false,
  setAuth: (token, username, role) => {
    set({
      accessToken: token,
      username: username,
      role,
      isAuthenticated: true,
    });
  },
  clearAuth: () => {
    set({
      accessToken: null,
      username: null,
      role: null,
      isAuthenticated: false,
    });
  },
  setInitialized: (val) => set({
    isInitialized: val,
  }),
}));

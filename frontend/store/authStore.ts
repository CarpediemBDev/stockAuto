import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  username: string | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  setAuth: (token: string, username: string, refreshToken?: string) => void;
  clearAuth: () => void;
  setInitialized: (val: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  username: null,
  isAuthenticated: false,
  isInitialized: false,
  setAuth: (token, username, refreshToken) => {
    if (typeof window !== 'undefined' && refreshToken) {
      localStorage.setItem('refresh_token', refreshToken);
    }
    set({
      accessToken: token,
      username: username,
      isAuthenticated: true,
    });
  },
  clearAuth: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('refresh_token');
    }
    set({
      accessToken: null,
      username: null,
      isAuthenticated: false,
    });
  },
  setInitialized: (val) => set({
    isInitialized: val,
  }),
}));

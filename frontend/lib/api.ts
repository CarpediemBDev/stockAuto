import axios, { AxiosRequestConfig, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';

declare module 'axios' {
  export interface AxiosResponse {
    serverMessage?: string;
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  withCredentials: true, // HttpOnly 쿠키 통신을 위한 필수 설정
});

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

interface ApiErrorPayload {
  error?: { message?: string };
  detail?: string;
}

export interface AuthSession {
  accessToken: string;
  username: string;
  role: string;
}

let refreshSessionPromise: Promise<AuthSession> | null = null;
const AUTH_REQUESTS_WITHOUT_REFRESH = [
  '/auth/login',
  '/auth/signup',
  '/auth/refresh',
] as const;

const shouldSkipAuthRefresh = (url?: string): boolean => {
  const requestPath = url?.split('?', 1)[0];
  return AUTH_REQUESTS_WITHOUT_REFRESH.some((path) => requestPath?.endsWith(path));
};

const parseAuthSession = (payload: {
  data?: {
    access_token?: string;
    username?: string;
    role?: string;
  };
  access_token?: string;
  username?: string;
  role?: string;
}): AuthSession => {
  const data = payload.data ?? payload;
  if (!data.access_token || !data.username || !data.role) {
    throw new Error("인증 갱신 응답 형식이 올바르지 않습니다.");
  }
  return {
    accessToken: data.access_token,
    username: data.username,
    role: data.role,
  };
};

export const refreshAuthSession = (): Promise<AuthSession> => {
  if (!refreshSessionPromise) {
    refreshSessionPromise = axios
      .post(`${API_BASE}/auth/refresh`, undefined, {
        timeout: 15000,
        withCredentials: true,
      })
      .then((response) => {
        const session = parseAuthSession(response.data);
        useAuthStore.getState().setAuth(
          session.accessToken,
          session.username,
          session.role,
        );
        return session;
      })
      .finally(() => {
        refreshSessionPromise = null;
      });
  }
  return refreshSessionPromise;
};

// Request Interceptor: Zustand 메모리에서 토큰 주입
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response Interceptor: 만료 처리 및 Silent Refresh
api.interceptors.response.use(
  (response) => {
    if (response.data && response.data.code === 'SUCCESS') {
      const serverMessage = response.data.message;
      response.data = response.data.data;
      response.serverMessage = serverMessage;
      return response;
    }
    return response;
  },
  async (error: unknown) => {
    if (axios.isCancel(error)) {
        return Promise.reject(error);
    }
    if (!axios.isAxiosError<ApiErrorPayload>(error)) {
      return Promise.reject(error);
    }

    const axiosError = error as AxiosError<ApiErrorPayload>;
    const originalRequest = axiosError.config as RetryableRequestConfig | undefined;

    // 401 에러이고, 아직 재시도하지 않은 요청이며, /auth/refresh 로 가는 요청이 아닐 때
    if (
      axiosError.response?.status === 401
      && originalRequest
      && !originalRequest._retry
      && !shouldSkipAuthRefresh(originalRequest.url)
    ) {
      const currentAccessToken = useAuthStore.getState().accessToken;
      const requestAuthorization = originalRequest.headers.Authorization;

      // 다른 401 요청이 이미 토큰을 갱신했다면 refresh를 반복하지 않고 새 토큰으로 재시도합니다.
      if (
        currentAccessToken
        && requestAuthorization !== `Bearer ${currentAccessToken}`
      ) {
        originalRequest._retry = true;
        originalRequest.headers.Authorization = `Bearer ${currentAccessToken}`;
        return api(originalRequest);
      }

      originalRequest._retry = true;

      try {
        const session = await refreshAuthSession();
        originalRequest.headers.Authorization = `Bearer ${session.accessToken}`;
        return api(originalRequest);
      } catch (refreshError: unknown) {
        useAuthStore.getState().clearAuth();
        if (typeof window !== 'undefined') {
          if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/signup')) {
            window.location.href = '/login';
          }
        }
        return Promise.reject(refreshError);
      }
    }

    if (axiosError.response?.data?.error?.message) {
      axiosError.message = axiosError.response.data.error.message;
    } else if (axiosError.response?.data?.detail) {
      axiosError.message = axiosError.response.data.detail;
    }
    return Promise.reject(axiosError);
  }
);

export const authAPI = {
  signup: (username: string, password: string) => api.post('/auth/signup', { username, password }),
  login: (username: string, password: string) => api.post('/auth/login', { username, password }),
  refresh: refreshAuthSession,
  logout: () => api.post('/auth/logout'),
  changePassword: (oldPassword: string, newPassword: string) => api.post(
    '/auth/change-password',
    { old_password: oldPassword, new_password: newPassword },
  ),
  getMe: (config?: AxiosRequestConfig) => api.get('/auth/me', config),
};

export const botAPI = {
  getStatus: (config?: AxiosRequestConfig) => api.get('/bot/status', config),
  start: () => api.post('/bot/start'),
  stop: () => api.post('/bot/stop'),
};

export const tradeAPI = {
  getLogs: (config?: AxiosRequestConfig) => api.get('/trades', config),
  getActions: (config?: AxiosRequestConfig) => api.get('/trades/actions', config),
};

export const accountAPI = {
  getBalance: (config?: AxiosRequestConfig) => api.get('/account/balance', config),
  getHoldings: (config?: AxiosRequestConfig) => api.get('/account/holdings', config),
};

export const scannerAPI = {
  getLatest: (config?: AxiosRequestConfig) => api.get('/scanner/latest', config),
  runOverseasScan: (config?: AxiosRequestConfig) => api.post('/scanner/overseas', {}, { timeout: 120000, ...config }),
  getSwingPredict: (config?: AxiosRequestConfig) => api.get('/scanner/swing-predict', config),
  refreshSwingPredict: (config?: AxiosRequestConfig) => api.post('/scanner/swing-predict/refresh', {}, { timeout: 120000, ...config }),
};

export const marketAPI = {
  getOverview: (config?: AxiosRequestConfig) => api.get('/market/overview', { timeout: 10000, ...config }),
};

export const watchlistAPI = {
  getAll: (config?: AxiosRequestConfig) => api.get('/watchlist', config),
  add: (ticker: string, name: string) => api.post('/watchlist', { ticker, ticker_name: name }),
  delete: (id: number) => api.delete(`/watchlist/${id}`),
};

export const translationAPI = {
  getAll: (config?: AxiosRequestConfig) => api.get('/translations', config),
  save: (ticker: string, nameKo: string) => api.post('/translations', { ticker, name_ko: nameKo }),
  update: (id: number, nameKo: string) => api.put(`/translations/${id}`, { name_ko: nameKo }),
  delete: (id: number) => api.delete(`/translations/${id}`),
};

export const reportAPI = {
  getStats: (config?: AxiosRequestConfig) => api.get('/report/stats', config),
  triggerManualReport: () => api.post('/report/trigger-manual-report'),
  triggerGlobalReport: () => api.post('/report/trigger-global-report'),
  triggerPersonalReport: () => api.post('/report/trigger-personal-report'),
};

export const adminAPI = {
  getSystemLogs: (config?: AxiosRequestConfig) => api.get('/admin/system-logs', config),
  getBacktestTournament: (config?: AxiosRequestConfig) => api.get('/admin/backtest/tournament', { timeout: 120000, ...config }),
};

export const isCancel = axios.isCancel;

export const fetcher = (url: string) => api.get(url).then(res => res.data);

export default api;

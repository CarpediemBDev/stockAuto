import axios, { AxiosRequestConfig, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  withCredentials: true, // HttpOnly 쿠키 통신을 위한 필수 설정
});

let isRefreshing = false;
interface PendingRequest {
  resolve: (token: string | null) => void;
  reject: (reason: unknown) => void;
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

interface ApiErrorPayload {
  error?: { message?: string };
  detail?: string;
}

let failedQueue: PendingRequest[] = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
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
      return { ...response, data: response.data.data };
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
      && !originalRequest.url?.includes('/auth/refresh')
    ) {
      if (isRefreshing) {
        return new Promise<string | null>(function(resolve, reject) {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          if (token) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return api(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // 인터셉터를 타지 않는 axios 인스턴스로 refresh 호출 (무한루프 방지)
        const refreshResponse = await axios.post(`${API_BASE}/auth/refresh`, {}, { withCredentials: true });
        const newToken = refreshResponse.data.data ? refreshResponse.data.data.access_token : refreshResponse.data.access_token;
        const newUsername = refreshResponse.data.data ? refreshResponse.data.data.username : refreshResponse.data.username;

        // Zustand 업데이트
        useAuthStore.getState().setAuth(newToken, newUsername);

        processQueue(null, newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError: unknown) {
        processQueue(refreshError, null);
        useAuthStore.getState().clearAuth();
        if (typeof window !== 'undefined') {
          if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/signup')) {
            window.location.href = '/login';
          }
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
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
  refresh: () => api.post('/auth/refresh'),
  logout: () => api.post('/auth/logout'),
  getMe: (config?: AxiosRequestConfig) => api.get('/auth/me', config),
};

export const botAPI = {
  getStatus: (config?: AxiosRequestConfig) => api.get('/bot/status', config),
  start: () => api.post('/bot/start'),
  stop: () => api.post('/bot/stop'),
  toggleReal: () => api.post('/bot/toggle-real'),
};

export const tradeAPI = {
  getLogs: (config?: AxiosRequestConfig) => api.get('/trades/', config),
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
  getAll: (config?: AxiosRequestConfig) => api.get('/watchlist/', config),
  add: (ticker: string, name: string) => api.post('/watchlist/', { ticker, ticker_name: name }),
  delete: (id: number) => api.delete(`/watchlist/${id}`),
};

export const translationAPI = {
  getAll: (config?: AxiosRequestConfig) => api.get('/translations/', config),
  save: (ticker: string, nameKo: string) => api.post('/translations/', { ticker, name_ko: nameKo }),
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
  getBacktestTournament: (config?: AxiosRequestConfig) => api.get('/admin/backtest/tournament', config),
};

export const isCancel = axios.isCancel;

export default api;

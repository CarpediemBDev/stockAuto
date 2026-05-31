import axios, { AxiosRequestConfig } from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

// Request Interceptor: JWT 토큰 자동 바인딩 (로컬스토리지 토큰 주입)
api.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('stockauto_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response Interceptor: 데이터 추출 및 에러 메시지 통일
api.interceptors.response.use(
  (response) => {
    // 성공 시 data 필드만 반환 (FastAPI APIResponse 구조 분해)
    if (response.data && response.data.code === 'SUCCESS') {
      return { ...response, data: response.data.data };
    }
    return response;
  },
  (error) => {
    if (axios.isCancel(error)) {
        return Promise.reject(error);
    }
    
    // 401 Unauthorized 에러 감지 시 로컬스토리지 정리 및 로그인 이동
    if (error.response && error.response.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('stockauto_token');
        localStorage.removeItem('stockauto_username');
        // 현재 로그인 페이지가 아니라면 리다이렉트
        if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/signup')) {
          window.location.href = '/login';
        }
      }
    }

    if (error.response && error.response.data && error.response.data.error) {
      error.message = error.response.data.error.message;
    } else if (error.response && error.response.data && error.response.data.detail) {
      error.message = error.response.data.detail;
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  signup: (username: string, password: string) => api.post('/auth/signup', { username, password }),
  login: (username: string, password: string) => api.post('/auth/login', { username, password }),
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
  getSwingPredict: (config?: AxiosRequestConfig) => api.get('/scanner/swing-predict', config),
};

export const marketAPI = {
  getOverview: (config?: AxiosRequestConfig) => api.get('/market/overview', config),
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
};

export const adminAPI = {
  getSystemLogs: (config?: AxiosRequestConfig) => api.get('/admin/system-logs', config),
  getBacktestTournament: (config?: AxiosRequestConfig) => api.get('/admin/backtest/tournament', config),
};

export const isCancel = axios.isCancel;

export default api;

import axios, { AxiosRequestConfig } from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// Response Interceptor: 데이터 추출 및 에러 메시지 통일
api.interceptors.response.use(
  (response) => {
    // 성공 시 data 필드만 반환
    if (response.data && response.data.code === 'SUCCESS') {
      return { ...response, data: response.data.data };
    }
    return response;
  },
  (error) => {
    // 요청 취소(Abort)인 경우는 에러 메시지를 띄우지 않음
    if (axios.isCancel(error)) {
        return Promise.reject(error);
    }
    // 에러 발생 시 규격화된 메시지 추출
    if (error.response && error.response.data && error.response.data.error) {
      error.message = error.response.data.error.message;
    }
    return Promise.reject(error);
  }
);

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

export const isCancel = axios.isCancel;

export default api;

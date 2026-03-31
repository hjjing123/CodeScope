import axios from 'axios';
import { message } from 'antd';
import { useAuthStore } from '../store/useAuthStore';
import { getAuthToken } from './authToken';
import { refreshAuthSession } from './authSession';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipErrorToast?: boolean;
    skipAuthRefresh?: boolean;
    skipUnauthorizedHandler?: boolean;
    _retryAfterRefresh?: boolean;
  }

  interface InternalAxiosRequestConfig {
    skipErrorToast?: boolean;
    skipAuthRefresh?: boolean;
    skipUnauthorizedHandler?: boolean;
    _retryAfterRefresh?: boolean;
  }
}

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

request.interceptors.request.use(
  (config) => {
    const token = getAuthToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

request.interceptors.response.use(
  (response) => {
    return response.data;
  },
  async (error) => {
    const { response, config } = error;
    const skipErrorToast = Boolean(config?.skipErrorToast);
    const skipUnauthorizedHandler = Boolean(config?.skipUnauthorizedHandler);

    const handleUnauthorized = () => {
      useAuthStore.getState().clearSession();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    };

    if (response) {
      const { status, data } = response;
      if (status === 401 && config && !config.skipAuthRefresh && !config._retryAfterRefresh) {
        try {
          await refreshAuthSession();
          useAuthStore.getState().syncFromStorage();

          config._retryAfterRefresh = true;
          const token = getAuthToken();
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
          return request(config);
        } catch (refreshError) {
          if (!skipUnauthorizedHandler) {
            handleUnauthorized();
          }
          if (!skipErrorToast) {
            message.error(data?.error?.message || data?.message || '登录已过期，请重新登录');
          }
          return Promise.reject(refreshError);
        }
      }

      if (status === 401 && !skipUnauthorizedHandler) {
        handleUnauthorized();
      }

      if (!skipErrorToast) {
        message.error(data?.error?.message || data?.message || 'Request failed');
      }
    } else if (!skipErrorToast) {
      message.error('Network error');
    }
    return Promise.reject(error);
  }
);

export default request;

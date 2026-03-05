import axios from 'axios';
import { message } from 'antd';
import { clearAuthToken, getAuthToken } from './authToken';

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
  (error) => {
    const { response } = error;
    if (response) {
      const { status, data } = response;
      if (status === 401) {
        // Handle unauthorized access (e.g., clear token and redirect to login)
        clearAuthToken();
        // Ideally, we should redirect or dispatch logout action here
        // simpler approach:
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
      }
      message.error(data?.error?.message || data?.message || 'Request failed');
    } else {
      message.error('Network error');
    }
    return Promise.reject(error);
  }
);

export default request;

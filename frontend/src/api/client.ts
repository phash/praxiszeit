import axios from 'axios';

// Create axios instance
// withCredentials: true ensures the HttpOnly refresh-token cookie is sent
// on cross-origin requests and on the /api/auth/refresh call.
const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor: Add JWT access token to Authorization header
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: Handle 401 errors with automatic token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Don't intercept auth endpoint errors (login / refresh themselves)
    // to avoid masking TOTP-required responses or refresh failures.
    const url: string = originalRequest?.url || '';
    if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
      return Promise.reject(error);
    }

    // If 401 and we haven't retried yet, try to refresh the access token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // F-010: refresh token is in the HttpOnly cookie – no body needed
        const response = await axios.post('/api/auth/refresh', null, {
          withCredentials: true,
        });

        const { access_token } = response.data;
        localStorage.setItem('access_token', access_token);

        // Retry the original request with the new access token
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed (expired or revoked) – redirect to login
        localStorage.clear();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;

import axios from 'axios'
import type { TripFormData, TripPlanResponse } from '@/types'

// 默认使用同源(baseURL="")，让 Vite dev server 的 /api 代理生效。
// 注意：当页面运行在 HTTPS 域名(例如 trycloudflare) 下，如果仍强制使用
// `http://localhost:8000` 会触发浏览器 Mixed Content，从而表现为 Network Error。
let API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || ''

if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
  const isLocalHttp =
    API_BASE_URL.startsWith('http://localhost') ||
    API_BASE_URL.startsWith('http://127.0.0.1') ||
    API_BASE_URL.startsWith('http://0.0.0.0')
  if (isLocalHttp) {
    console.warn(
      '[api] Detected HTTPS origin with HTTP localhost API baseURL; falling back to same-origin /api proxy to avoid Mixed Content.'
    )
    API_BASE_URL = ''
  }
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000, // 3分钟超时（兼容 Render 冷启动与外部工具调用延迟）
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient


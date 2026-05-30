import { defineStore } from 'pinia'
import http from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    username: localStorage.getItem('username') || '',
    role: localStorage.getItem('role') || '',
    tenantId: localStorage.getItem('tenantId') ? Number(localStorage.getItem('tenantId')) : null,
    tenantName: localStorage.getItem('tenantName') || '',
    tenantExpireAt: localStorage.getItem('tenantExpireAt') || '',
    platformId: localStorage.getItem('platformId') ? Number(localStorage.getItem('platformId')) : null,
    platformIds: JSON.parse(localStorage.getItem('platformIds') || '[]'),
    moduleKeys: JSON.parse(localStorage.getItem('moduleKeys') || '[]'),
  }),
  actions: {
    async syncProfile() {
      if (!this.token) return
      const { data } = await http.get('/auth/me')
      this.role = data.role || this.role
      this.tenantId = data.tenant_id ?? null
      this.tenantName = data.tenant_name || ''
      this.tenantExpireAt = data.tenant_expire_at || ''
      this.platformId = data.platform_id ?? null
      this.platformIds = data.platform_ids || []
      this.moduleKeys = data.module_keys || []
      localStorage.setItem('role', this.role || '')
      if (this.tenantId === null || this.tenantId === undefined) {
        localStorage.removeItem('tenantId')
      } else {
        localStorage.setItem('tenantId', String(this.tenantId))
      }
      localStorage.setItem('tenantName', this.tenantName || '')
      localStorage.setItem('tenantExpireAt', this.tenantExpireAt || '')
      if (this.platformId === null || this.platformId === undefined) {
        localStorage.removeItem('platformId')
      } else {
        localStorage.setItem('platformId', String(this.platformId))
      }
      localStorage.setItem('platformIds', JSON.stringify(this.platformIds))
      localStorage.setItem('moduleKeys', JSON.stringify(this.moduleKeys))
    },
    async login(payload) {
      const { data } = await http.post('/auth/login', payload)
      this.token = data.access_token
      this.username = payload.username
      this.role = data.role
      this.tenantId = data.tenant_id ?? null
      this.tenantName = data.tenant_name || ''
      this.tenantExpireAt = data.tenant_expire_at || ''
      this.platformId = data.platform_id
      this.platformIds = data.platform_ids || (data.platform_id ? [data.platform_id] : [])
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('username', payload.username)
      localStorage.setItem('role', data.role)
      if (this.tenantId === null || this.tenantId === undefined) {
        localStorage.removeItem('tenantId')
      } else {
        localStorage.setItem('tenantId', String(this.tenantId))
      }
      localStorage.setItem('tenantName', this.tenantName || '')
      localStorage.setItem('tenantExpireAt', this.tenantExpireAt || '')
      if (data.platform_id === null || data.platform_id === undefined) {
        localStorage.removeItem('platformId')
      } else {
        localStorage.setItem('platformId', String(data.platform_id))
      }
      localStorage.setItem('platformIds', JSON.stringify(this.platformIds))
      await this.syncProfile()
    },
    logout() {
      this.token = ''
      this.username = ''
      this.role = ''
      this.tenantId = null
      this.tenantName = ''
      this.tenantExpireAt = ''
      this.platformId = null
      this.platformIds = []
      this.moduleKeys = []
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('role')
      localStorage.removeItem('tenantId')
      localStorage.removeItem('tenantName')
      localStorage.removeItem('tenantExpireAt')
      localStorage.removeItem('platformId')
      localStorage.removeItem('platformIds')
      localStorage.removeItem('moduleKeys')
    },
  },
})

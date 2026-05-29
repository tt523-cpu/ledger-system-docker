import { defineStore } from 'pinia'
import http from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    username: localStorage.getItem('username') || '',
    role: localStorage.getItem('role') || '',
    platformId: localStorage.getItem('platformId') ? Number(localStorage.getItem('platformId')) : null,
    moduleKeys: JSON.parse(localStorage.getItem('moduleKeys') || '[]'),
  }),
  actions: {
    async login(payload) {
      const { data } = await http.post('/auth/login', payload)
      this.token = data.access_token
      this.username = payload.username
      this.role = data.role
      this.platformId = data.platform_id
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('username', payload.username)
      localStorage.setItem('role', data.role)
      if (data.platform_id === null || data.platform_id === undefined) {
        localStorage.removeItem('platformId')
      } else {
        localStorage.setItem('platformId', String(data.platform_id))
      }
      const me = await http.get('/auth/me')
      this.moduleKeys = me.data.module_keys || []
      localStorage.setItem('moduleKeys', JSON.stringify(this.moduleKeys))
    },
    logout() {
      this.token = ''
      this.username = ''
      this.role = ''
      this.platformId = null
      this.moduleKeys = []
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('role')
      localStorage.removeItem('platformId')
      localStorage.removeItem('moduleKeys')
    },
  },
})

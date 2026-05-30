<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const menus = [
  { path: '/super/tenants', label: '租户管理', moduleKey: 'master.tenants' },
  { path: '/super/reports', label: '平台报表', moduleKey: 'reports.query' },
  { path: '/super/balances', label: '平台余额', moduleKey: 'reports.balances' },
  { path: '/super/users', label: '后台用户', moduleKey: 'super.users' },
  { path: '/super/logs', label: '平台日志', moduleKey: 'logs' },
  { path: '/super/system-tools', label: '平台工具', moduleKey: 'system.tools' },
]

const visibleMenus = computed(() => menus.filter((m) => auth.moduleKeys.includes(m.moduleKey)))
const roleLabel = computed(() => (auth.role === 'platform_viewer' ? '平台查看员' : '超级管理员'))

function logout() {
  auth.logout()
  router.push('/login')
}

async function changePassword() {
  const ret = await ElMessageBox.prompt('请输入新密码（至少6位）', '修改密码', {
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputType: 'password',
    inputPattern: /^.{6,}$/,
    inputErrorMessage: '密码至少6位',
  }).catch(() => null)
  if (!ret) return
  const me = await http.get('/auth/me')
  await http.put(`/master/users/${me.data.id}/password`, null, { params: { new_password: ret.value } })
  ElMessage.success('密码已修改')
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <h2>超管后台</h2>
      <el-menu router :default-active="$route.path">
        <el-menu-item v-for="m in visibleMenus" :key="m.path" :index="m.path">{{ m.label }}</el-menu-item>
      </el-menu>
    </aside>
    <main class="main">
      <div class="topbar">
        <span>当前用户：{{ auth.username }} ｜ {{ roleLabel }}</span>
        <el-button size="small" @click="changePassword">修改密码</el-button>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
      <router-view />
    </main>
  </div>
</template>

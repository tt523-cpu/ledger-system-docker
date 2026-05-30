<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const menus = [
  { path: '/', label: '首页仪表盘', moduleKey: 'dashboard' },
  { path: '/transactions/entry', label: '流水录入', moduleKey: 'transactions.entry' },
  { path: '/transactions/list', label: '流水查询', moduleKey: 'transactions.list' },
  { path: '/reports/query', label: '报表查询', moduleKey: 'reports.query' },
  { path: '/reports/balances', label: '账户余额', moduleKey: 'reports.balances' },
  { path: '/reports/monthly', label: '月度汇总', moduleKey: 'reports.monthly' },
  { path: '/reports/charts', label: '图表分析', moduleKey: 'reports.charts' },
  { path: '/master/platforms', label: '平台管理', moduleKey: 'master.platforms' },
  { path: '/master/payment-methods', label: '账户管理', moduleKey: 'master.payment_methods' },
  { path: '/master/categories', label: '项目管理', moduleKey: 'master.categories' },
  { path: '/master/entry-types', label: '类型管理', moduleKey: 'master.entry_types' },
  { path: '/master/shifts', label: '班次管理', moduleKey: 'master.shifts' },
  { path: '/master/users', label: '用户管理', moduleKey: 'master.users' },
  { path: '/logs', label: '修改日志', moduleKey: 'logs' },
  { path: '/system/tools', label: '系统工具', moduleKey: 'system.tools' },
]

const visibleMenus = menus.filter((m) => auth.moduleKeys.includes(m.moduleKey))

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <h2>鲨鱼记帐</h2>
      <el-menu router :default-active="$route.path">
        <el-menu-item v-for="m in visibleMenus" :index="m.path" :key="m.path">{{ m.label }}</el-menu-item>
      </el-menu>
    </aside>
    <main class="main">
      <div class="topbar">
        <span>当前用户：{{ auth.username }}</span>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
      <router-view />
    </main>
  </div>
</template>

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  {
    path: '/super',
    component: () => import('../views/SuperLayoutView.vue'),
    children: [
      { path: '', redirect: '/super/tenants' },
      { path: 'tenants', component: () => import('../views/master/TenantsView.vue'), meta: { moduleKey: 'master.tenants' } },
      { path: 'reports', component: () => import('../views/SuperTenantReportView.vue'), meta: { moduleKey: 'reports.query' } },
      { path: 'balances', component: () => import('../views/SuperTenantBalancesView.vue'), meta: { moduleKey: 'reports.balances' } },
      { path: 'users', component: () => import('../views/SuperUsersView.vue'), meta: { moduleKey: 'super.users' } },
      { path: 'logs', component: () => import('../views/LogCenterView.vue'), meta: { moduleKey: 'logs' } },
      { path: 'system-tools', component: () => import('../views/SystemToolsView.vue'), meta: { moduleKey: 'system.tools' } },
    ],
  },
  {
    path: '/',
    component: () => import('../views/LayoutView.vue'),
    children: [
      { path: '', component: () => import('../views/DashboardView.vue'), meta: { moduleKey: 'dashboard' } },
      { path: 'transactions/entry', component: () => import('../views/TransactionEntryView.vue'), meta: { moduleKey: 'transactions.entry' } },
      { path: 'transactions/list', component: () => import('../views/TransactionListView.vue'), meta: { moduleKey: 'transactions.list' } },
      { path: 'reports/query', component: () => import('../views/ReportQueryView.vue'), meta: { moduleKey: 'reports.query' } },
      { path: 'reports/balances', component: () => import('../views/BalanceView.vue'), meta: { moduleKey: 'reports.balances' } },
      { path: 'reports/monthly', component: () => import('../views/MonthlyReportView.vue'), meta: { moduleKey: 'reports.monthly' } },
      { path: 'reports/charts', component: () => import('../views/ChartsView.vue'), meta: { moduleKey: 'reports.charts' } },
      { path: 'master/platforms', component: () => import('../views/master/PlatformsView.vue'), meta: { moduleKey: 'master.platforms' } },
      { path: 'master/categories', component: () => import('../views/master/CategoriesView.vue'), meta: { moduleKey: 'master.categories' } },
      { path: 'master/entry-types', component: () => import('../views/master/EntryTypesView.vue'), meta: { moduleKey: 'master.entry_types' } },
      { path: 'master/shifts', component: () => import('../views/master/ShiftsView.vue'), meta: { moduleKey: 'master.shifts' } },
      { path: 'master/payment-methods', component: () => import('../views/master/PaymentMethodsView.vue'), meta: { moduleKey: 'master.payment_methods' } },
      { path: 'master/users', component: () => import('../views/master/UsersView.vue'), meta: { moduleKey: 'master.users' } },
      { path: 'master/tenants', component: () => import('../views/master/TenantsView.vue'), meta: { moduleKey: 'master.tenants' } },
      { path: 'log-center', component: () => import('../views/LogCenterView.vue'), meta: { moduleKey: 'logs' } },
      { path: 'logs', component: () => import('../views/LogsView.vue'), meta: { moduleKey: 'logs' } },
      { path: 'operation-logs', component: () => import('../views/OperationLogsView.vue'), meta: { moduleKey: 'operation.logs' } },
      { path: 'system/tools', component: () => import('../views/SystemToolsView.vue'), meta: { moduleKey: 'system.tools' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const fallbackMap = {
  dashboard: '/',
  'transactions.entry': '/transactions/entry',
  'transactions.list': '/transactions/list',
  'reports.query': '/reports/query',
  'reports.balances': '/reports/balances',
  'reports.monthly': '/reports/monthly',
  'reports.charts': '/reports/charts',
  'master.platforms': '/master/platforms',
  'master.payment_methods': '/master/payment-methods',
  'master.categories': '/master/categories',
  'master.entry_types': '/master/entry-types',
  'master.shifts': '/master/shifts',
  'master.users': '/master/users',
  'master.tenants': '/master/tenants',
  'super.users': '/super/users',
  logs: '/log-center',
  'operation.logs': '/operation-logs',
  'system.tools': '/system/tools',
}

const superFallbackMap = {
  'master.tenants': '/super/tenants',
  'reports.query': '/super/reports',
  'reports.monthly': '/super/reports',
  'reports.charts': '/super/reports',
  'reports.balances': '/super/balances',
  'super.users': '/super/users',
  logs: '/super/logs',
  'operation.logs': '/super/logs',
  'system.tools': '/super/system-tools',
}

function getFirstAllowedPath(moduleKeys) {
  const firstAllowed = (moduleKeys || []).map((k) => fallbackMap[k]).find(Boolean)
  return firstAllowed || '/transactions/entry'
}

function getFirstAllowedSuperPath(moduleKeys) {
  const firstAllowed = (moduleKeys || []).map((k) => superFallbackMap[k]).find(Boolean)
  return firstAllowed || '/super/reports'
}

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const moduleKeys = JSON.parse(localStorage.getItem('moduleKeys') || '[]')
  const role = localStorage.getItem('role') || ''
  if (to.path !== '/login' && !token) {
    next('/login')
    return
  }
  if (to.path === '/login' && token) {
    next((role === 'super_admin' || role === 'platform_viewer') ? getFirstAllowedSuperPath(moduleKeys) : '/')
    return
  }
  if (token && (role === 'super_admin' || role === 'platform_viewer') && to.path === '/super') {
    next(getFirstAllowedSuperPath(moduleKeys))
    return
  }
  if (token && (role === 'super_admin' || role === 'platform_viewer') && !to.path.startsWith('/super')) {
    next(getFirstAllowedSuperPath(moduleKeys))
    return
  }
  if (token && role !== 'super_admin' && role !== 'platform_viewer' && to.path.startsWith('/super')) {
    next('/login')
    return
  }
  if (token && role !== 'super_admin' && to.path.startsWith('/master/tenants')) {
    next('/')
    return
  }
  const moduleKey = to.meta?.moduleKey
  if (token && moduleKey && moduleKeys.length > 0 && !moduleKeys.includes(moduleKey)) {
    next((role === 'super_admin' || role === 'platform_viewer') ? getFirstAllowedSuperPath(moduleKeys) : getFirstAllowedPath(moduleKeys))
    return
  }
  next()
})

export default router

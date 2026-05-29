import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
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
      { path: 'logs', component: () => import('../views/LogsView.vue'), meta: { moduleKey: 'logs' } },
      { path: 'system/tools', component: () => import('../views/SystemToolsView.vue'), meta: { moduleKey: 'system.tools' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const moduleKeys = JSON.parse(localStorage.getItem('moduleKeys') || '[]')
  if (to.path !== '/login' && !token) {
    next('/login')
    return
  }
  if (to.path === '/login' && token) {
    next('/')
    return
  }
  const moduleKey = to.meta?.moduleKey
  if (token && moduleKey && moduleKeys.length > 0 && !moduleKeys.includes(moduleKey)) {
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
      logs: '/logs',
      'system.tools': '/system/tools',
    }
    const firstAllowed = moduleKeys.map((k) => fallbackMap[k]).find(Boolean)
    next(firstAllowed || '/login')
    return
  }
  next()
})

export default router

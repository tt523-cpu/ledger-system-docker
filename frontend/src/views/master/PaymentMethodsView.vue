<template>
  <SimpleMasterTable
    title="账户管理"
    endpoint="payment-methods"
    :fields="[{ key: 'name', label: '名称' }, { key: 'initial_balance', label: '初始余额', type: 'number' }, { key: 'channel_kind', label: '通道类型' }, { key: 'sort_order', label: '排序', type: 'number' }]"
    :defaults="{ name: '', initial_balance: 0, channel_kind: 'internal', affect_balance: true, sort_order: 0, status: 'enabled', remark: '' }"
  />
</template>

<script setup>
import SimpleMasterTable from '../../components/SimpleMasterTable.vue'
</script>

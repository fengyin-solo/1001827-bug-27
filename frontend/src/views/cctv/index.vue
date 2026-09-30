<template>
  <section class="page" data-module="cctv">
    <header class="page-head">
      <div>
        <h2>内窥检测管理</h2>
        <p class="page-desc">维护检测报告，围绕检测编号、检测管段、检测设备、检测长度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测报告</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">
          {{ exporting ? '正在导出…' : '导出内窥检测清单' }}
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="exportError" class="error-text export-error">
      {{ exportError }}
      <button class="link" type="button" @click="exportRows">再试一次</button>
    </p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无内窥检测数据，可先登记检测报告</td>
        </tr>
      </tbody>
    </table>

    <section class="review-panel">
      <h3>复核清单</h3>
      <p class="page-desc">退回重检的报告会带着整改结论进入这里，等待复核。</p>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in reviewColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in reviewRows" :key="String(item.id)">
            <td v-for="column in reviewColumns" :key="column">{{ item[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td :colspan="reviewColumns.length" class="empty-state">暂无待复核的检测报告</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条内窥检测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/cctv'
const columns = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
const actions = ["安排检测", "确认出具", "退回重检"]
const statuses = ["待检测", "检测中", "已出具", "已退回"]
const stats = [{"label": "待检测管段", "value": 0}, {"label": "本月检测长度", "value": 0}, {"label": "四级缺陷段", "value": 0}]
const reviewColumns = ["检测编号", "检测管段", "检测设备", "整改结论", "检测状态"]
// 导出失败原因存在本地，页面重开后还能看得到
const EXPORT_ERROR_KEY = 'cctv:lastExportError'

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const exportError = ref('')
const exporting = ref(false)
const reviewRows = ref<Row[]>([])
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function currentQuery(): string {
  const params = new URLSearchParams()
  for (const [field, value] of Object.entries(filters.value)) {
    if (value && value.trim()) {
      params.set(field, value.trim())
    }
  }
  return params.toString()
}

async function exportRows() {
  exportError.value = ''
  exporting.value = true
  try {
    const query = currentQuery()
    const response = await request(`${ENDPOINT}/export${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/)
    const filename = match ? decodeURIComponent(match[1]) : '内窥检测清单.csv'
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    localStorage.removeItem(EXPORT_ERROR_KEY)
  } catch (error) {
    const detail = error instanceof Error ? error.message : '导出请求未送达'
    exportError.value = `内窥检测清单导出失败：${detail}，可再试一次`
    localStorage.setItem(EXPORT_ERROR_KEY, exportError.value)
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  errorMessage.value = '检测报告登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  const values: Record<string, string> = { action }
  if (action === '退回重检') {
    const conclusion = window.prompt('请填写整改结论，退回后将进入复核清单')
    if (conclusion === null) {
      return
    }
    values['整改结论'] = conclusion
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    if (!response.ok) {
      throw new Error('内窥检测动作未生效，请稍后重试')
    }
    const result = await response.json()
    if (!result.ok) {
      throw new Error(result.message || '内窥检测动作未生效，请稍后重试')
    }
    await reload()
    await reloadReview()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = currentQuery()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('检测报告列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测列表读取失败'
  }
}

async function reloadReview() {
  try {
    const response = await request(`${ENDPOINT}/review`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    reviewRows.value = payload.items ?? []
  } catch {
    reviewRows.value = []
  }
}

onMounted(() => {
  exportError.value = localStorage.getItem(EXPORT_ERROR_KEY) ?? ''
  void reload()
  void reloadReview()
})
</script>

<style scoped>
.review-panel {
  margin-top: 16px;
}
.review-panel h3 {
  margin: 0 0 4px;
  font-size: 15px;
}
.export-error {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>

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

    <div v-if="exportError" class="error-banner">
      <span class="error-text">{{ exportError }}</span>
      <button class="link" type="button" @click="exportRows">重试</button>
    </div>

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

    <footer class="page-foot">
      <span>共 {{ total }} 条内窥检测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="review-panel">
      <header class="page-head">
        <div>
          <h3>复核清单</h3>
          <p class="page-desc">整改结论按检测管段归集，同一管段后到那一份覆盖旧结论，不会重复堆积。</p>
        </div>
      </header>

      <form class="filter-bar" @submit.prevent="submitConclusion">
        <label class="filter-item">
          <span>检测报告</span>
          <select v-model="conclusionForm.entryId">
            <option value="" disabled>选择检测报告</option>
            <option v-for="row in rows" :key="String(row.id)" :value="String(row.id)">
              {{ row['检测编号'] }}（{{ row['检测管段'] }}）
            </option>
          </select>
        </label>
        <label class="filter-item">
          <span>整改结论</span>
          <input v-model="conclusionForm.conclusion" placeholder="填写整改结论" />
        </label>
        <button class="btn primary" type="submit" :disabled="submittingConclusion">
          {{ submittingConclusion ? '正在提交…' : '提交整改结论' }}
        </button>
      </form>

      <p v-if="conclusionMessage" class="ok-text">{{ conclusionMessage }}</p>
      <div v-if="conclusionError" class="error-banner">
        <span class="error-text">{{ conclusionError }}</span>
        <button class="link" type="button" @click="submitConclusion">重试</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in reviewColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in reviewRows" :key="String(row.id)">
            <td v-for="column in reviewColumns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td :colspan="reviewColumns.length" class="empty-state">复核清单暂无整改结论</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/cctv'
const columns = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
const reviewColumns = ["检测编号", "检测管段", "整改结论", "提交时间"]
const actions = ["安排检测", "确认出具", "退回重检"]
const statuses = ["待检测", "检测中", "已出具", "已退回"]
const stats = [{"label": "待检测管段", "value": 0}, {"label": "本月检测长度", "value": 0}, {"label": "四级缺陷段", "value": 0}]

// 失败原因落在 localStorage：页面重开仍能看到，并可直接重试。
const EXPORT_ERROR_KEY = 'cctv:export:lastError'
const CONCLUSION_ERROR_KEY = 'cctv:conclusion:lastError'

const rows = ref<Row[]>([])
const reviewRows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const exportError = ref(localStorage.getItem(EXPORT_ERROR_KEY) ?? '')
const conclusionError = ref(localStorage.getItem(CONCLUSION_ERROR_KEY) ?? '')
const conclusionMessage = ref('')
const exporting = ref(false)
const submittingConclusion = ref(false)
const conclusionForm = ref({ entryId: '', conclusion: '' })
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function persistError(key: string, message: string) {
  if (message) {
    localStorage.setItem(key, message)
  } else {
    localStorage.removeItem(key)
  }
}

function setExportError(message: string) {
  exportError.value = message
  persistError(EXPORT_ERROR_KEY, message)
}

function setConclusionError(message: string, { persist = true } = {}) {
  conclusionError.value = message
  persistError(CONCLUSION_ERROR_KEY, persist ? message : '')
}

function currentQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) {
      params.set(key, value)
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  if (exporting.value) {
    return
  }
  exporting.value = true
  setExportError('')
  try {
    const query = currentQuery()
    const response = await request(`${ENDPOINT}/export${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`清单导出失败（接口返回 ${response.status}）`)
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `内窥检测清单_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    const detail = error instanceof Error ? error.message : '清单导出失败'
    setExportError(`${detail}，可点击重试`)
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  errorMessage.value = '检测报告登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '内窥检测动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测操作失败'
  }
}

async function submitConclusion() {
  if (submittingConclusion.value) {
    return
  }
  conclusionMessage.value = ''
  if (!conclusionForm.value.entryId) {
    setConclusionError('请先选择检测报告，再提交整改结论', { persist: false })
    return
  }
  if (!conclusionForm.value.conclusion.trim()) {
    setConclusionError('整改结论不能为空，请补充后再提交', { persist: false })
    return
  }
  submittingConclusion.value = true
  setConclusionError('')
  try {
    const response = await request(`${ENDPOINT}/${conclusionForm.value.entryId}/conclusion`, {
      method: 'POST',
      body: JSON.stringify({ values: { 整改结论: conclusionForm.value.conclusion.trim() } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? `整改结论提交失败（接口返回 ${response.status}）`)
    }
    conclusionMessage.value = payload.message ?? '整改结论已写入复核清单'
    conclusionForm.value = { entryId: '', conclusion: '' }
    await reloadReview()
  } catch (error) {
    // 落库失败时保留表单原值，只提示可以再试一次。
    const detail = error instanceof Error ? error.message : '整改结论提交失败'
    setConclusionError(`${detail}，可点击重试`)
  } finally {
    submittingConclusion.value = false
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
      throw new Error('复核清单读取失败')
    }
    const payload = await response.json()
    reviewRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复核清单读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadReview()
})
</script>

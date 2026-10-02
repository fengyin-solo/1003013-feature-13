<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>节能项目详情</h2>
        <p class="page-desc">节电率与回收期与列表页同一套实测口径；历史结论按当初那份原样留档。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goList">返回列表</button>
        <RouterLink v-if="entry && entry.status === '评估中'" class="btn primary" :to="`/energyeff/${entryId}/accept`">
          去验收评估
        </RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <template v-if="entry">
      <article class="detail-block" :class="{ 'abnormal-block': entry['偏差超限'] }">
        <h3>
          实测结果
          <span v-if="entry.status !== '已验收'" class="tag tag-muted">待验收</span>
          <span v-else-if="entry['偏差超限']" class="tag tag-warn">估算与实测偏差超限</span>
          <span v-else class="tag tag-ok">已验收</span>
        </h3>
        <dl class="metric-grid">
          <div><dt>立项预估节电率</dt><dd>{{ entry['预估节电率'] || '—' }}</dd></div>
          <div>
            <dt>实测节电率（基准期 / 观察期实测）</dt>
            <dd :class="{ 'metric-warn': entry['偏差超限'] }">
              {{ entry['实测节电率'] ?? '待验收' }}
            </dd>
          </div>
          <div>
            <dt>节电率偏差（实测−预估）</dt>
            <dd :class="{ 'metric-warn': entry['偏差超限'] }">{{ deviationText }}</dd>
          </div>
          <div><dt>投资回收期（按实际投资与实测节费重算）</dt><dd>{{ entry['投资回收期'] ?? '待验收' }}</dd></div>
        </dl>
        <dl v-if="entry.status === '已验收'" class="metric-grid">
          <div><dt>基准期日均用电</dt><dd>{{ avgText(entry['基准期日均用电']) }} 度/天</dd></div>
          <div><dt>观察期日均用电</dt><dd>{{ avgText(entry['观察期日均用电']) }} 度/天</dd></div>
          <div><dt>折年节电量</dt><dd>{{ avgText(entry['年节电量']) }} 度</dd></div>
          <div><dt>折年节省电费</dt><dd>{{ avgText(entry['年节省电费']) }} 元</dd></div>
        </dl>
        <p v-if="entry['差异说明']" class="diff-note">
          <strong>差异说明：</strong>{{ entry['差异说明'] }}
        </p>
      </article>

      <article class="detail-block">
        <h3>项目与实测原始数据</h3>
        <dl class="info-grid">
          <div><dt>项目编号</dt><dd>{{ entry['项目编号'] }}</dd></div>
          <div><dt>所属站点</dt><dd>{{ entry['所属站点'] }}</dd></div>
          <div><dt>改造内容</dt><dd>{{ entry['改造内容'] }}</dd></div>
          <div><dt>承包单位</dt><dd>{{ entry['承包单位'] || '—' }}</dd></div>
          <div><dt>立项投资金额</dt><dd>{{ valueText(entry['投资金额']) }} 元</dd></div>
          <div><dt>实际投资</dt><dd>{{ valueText(entry['实际投资']) }} 元</dd></div>
          <div><dt>基准期用电</dt><dd>{{ valueText(entry['基准期用电']) }} 度 / {{ entry['基准期天数'] ?? '—' }} 天</dd></div>
          <div><dt>连续观察期用电</dt><dd>{{ valueText(entry['观察期用电']) }} 度 / {{ entry['观察期天数'] ?? '—' }} 天</dd></div>
          <div><dt>电价</dt><dd>{{ valueText(entry['电价']) }} 元/度</dd></div>
          <div><dt>验收时间</dt><dd>{{ entry['验收时间'] ?? '—' }}</dd></div>
          <div><dt>项目状态</dt><dd>{{ entry.status }}</dd></div>
        </dl>
      </article>

      <article v-if="entry.status === '已验收'" class="detail-block">
        <h3>验收结论</h3>
        <template v-if="!editing">
          <p class="conclusion-text">{{ entry['验收结论'] }}</p>
          <button class="btn" type="button" @click="startEdit">修改验收结论</button>
        </template>
        <form v-else class="edit-form" @submit.prevent="saveConclusion">
          <textarea v-model="conclusionDraft" rows="3"></textarea>
          <p v-if="conclusionError" class="error-text">{{ conclusionError }}</p>
          <div class="form-actions">
            <button class="btn" type="button" @click="editing = false">取消</button>
            <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存并返回列表' }}</button>
          </div>
          <p class="block-hint">只改结论文字，实测节电率与重算回收期不变；本次修改会留档。</p>
        </form>
      </article>

      <article class="detail-block">
        <h3>历史验收留档（只增不改）</h3>
        <table v-if="archives.length" class="data-table">
          <thead>
            <tr><th>留档时间</th><th>来源</th><th>节电率</th><th>投资回收期</th><th>内容</th></tr>
          </thead>
          <tbody>
            <tr v-for="(record, index) in archives" :key="index">
              <td>{{ record['留档时间'] }}</td>
              <td>{{ record['来源'] }}</td>
              <td>{{ record['实测节电率'] ?? '—' }}</td>
              <td>{{ record['投资回收期'] ?? '—' }}</td>
              <td class="archive-content">
                <template v-if="record['来源'] === '验收结论修改'">
                  原结论：{{ record['原结论'] }}<br />新结论：{{ record['新结论'] }}
                </template>
                <template v-else>
                  {{ record['验收结论'] }}{{ record['说明'] ? `（${record['说明']}）` : '' }}
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted-text">该项目尚未验收，暂无留档记录。</p>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Archive = Record<string, string>
type Entry = Record<string, string | number | boolean | Archive[] | null>

const route = useRoute()
const router = useRouter()
const entryId = String(route.params.id)

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const editing = ref(false)
const saving = ref(false)
const conclusionDraft = ref('')
const conclusionError = ref('')

const archives = computed<Archive[]>(() => {
  const value = entry.value?.['验收档案']
  return Array.isArray(value) ? (value as Archive[]) : []
})

const deviationText = computed(() => {
  if (!entry.value || entry.value['节电率偏差'] == null) return '待验收'
  const value = Number(entry.value['节电率偏差'])
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)} 个百分点`
})

function valueText(value: unknown): string {
  if (value == null || value === '') return '—'
  return String(value)
}

function avgText(value: unknown): string {
  if (value == null || value === '') return '—'
  return Number(value).toFixed(1)
}

function goList() {
  void router.push({ path: '/energyeff' })
}

function startEdit() {
  conclusionDraft.value = String(entry.value?.['验收结论'] ?? '')
  conclusionError.value = ''
  editing.value = true
}

async function saveConclusion() {
  conclusionError.value = ''
  if (!conclusionDraft.value.trim()) {
    conclusionError.value = '验收结论不能为空'
    return
  }
  saving.value = true
  try {
    const response = await request(`/api/energyeff/${entryId}/conclusion`, {
      method: 'PATCH',
      body: JSON.stringify({ values: { 验收结论: conclusionDraft.value } }),
    })
    const result = await response.json()
    if (!result.ok) {
      conclusionError.value = result.message ?? '验收结论保存失败'
      return
    }
    // 验收结论改完再返回这一页（列表页）。
    goList()
  } catch (error) {
    conclusionError.value = error instanceof Error ? error.message : '验收结论保存失败'
  } finally {
    saving.value = false
  }
}

async function load() {
  try {
    const response = await request(`/api/energyeff/${entryId}`)
    if (!response.ok) {
      const result = await response.json().catch(() => null)
      throw new Error(result?.detail ?? '节能项目读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '节能项目读取失败'
  }
}

onMounted(load)
</script>

<style scoped>
.error-banner {
  background: #fef3f2;
  border: 1px solid #fecdca;
  color: #b42318;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
}
.detail-block {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.detail-block h3 {
  margin: 0 0 10px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.abnormal-block {
  border-color: #fecdca;
}
.tag {
  font-size: 12px;
  border-radius: 999px;
  padding: 2px 10px;
}
.tag-ok {
  background: #ecfdf3;
  color: #027a48;
}
.tag-warn {
  background: #fef3f2;
  color: #b42318;
}
.tag-muted {
  background: #f1f5f9;
  color: var(--muted);
}
.metric-grid,
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 20px;
  margin: 0 0 8px;
}
.metric-grid dt,
.info-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.metric-grid dd,
.info-grid dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.metric-warn {
  color: #b42318;
  font-weight: 600;
}
.diff-note {
  background: #fffaeb;
  border: 1px solid #fedf89;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  margin: 8px 0 0;
}
.conclusion-text {
  font-size: 13px;
  margin: 0 0 8px;
}
.edit-form textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  font-size: 13px;
  font-family: inherit;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.block-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 6px 0 0;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
.archive-content {
  font-size: 12px;
  color: #334155;
}
</style>

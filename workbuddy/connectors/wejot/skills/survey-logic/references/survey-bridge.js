/**
 * Survey Runtime - 问卷运行时环境（合并版）
 * 包含：数据层(survey-core) + 组件加载器(survey-runtime)
 *
 * 数据层职责：自动绑定题目事件、自动收集答案、提交数据、生成快照、文件上传
 * 组件加载器职责：自动加载组件 JS，设置平台环境
 *
 * 版本:
 * 20260530-1（矩阵列title 取显示文本并与数字分值分离，rows/columns 用 rowTitle/columnTitle）
 * 20260602-2（修复上传题上传成功后答案缓存未同步到 file input dataset，导致必填校验通过 SurveyApp.getAnswer 读取时误判为空；保留矩阵列title 显示文本与数字分值分离）
 * 20260608-2（基于 20260608-1：collectSurveyData 增加 survey.title/description 收集，仅读 data-title="survey" / data-desc="description"）
 * 20260610-1（上传题支持多文件追加上传）
 * 20260616-1（修复多选/单选 getOptionLabelText 未剥离 .cb/.rd/.ci 装饰节点，避免 ✓ 混入选项文案）
 * 20260616-2（sanitizeSubmitRows：UPLOAD 提交体若含 blob: URL，从 SurveyAnswerState / input dataset 替换为 OSS 链接）
 * 20260706-1（submitAndStay/submit 透传 evalResult 展示字符串；自动读 __WJ_EVAL_RESULT__ / 标准 eval DOM）
 * 20260728-1（允许 SurveyRuntime.setLogicAnswer 显式标记的隐藏派生答案进入提交数据）
 * 20260729-2（配套新版 SurveyRuntime 结构化逻辑写入与统一动态题项契约）
 * 20260730-1（矩阵答案在 DOM fallback 与缓存命中时统一返回 value 行数组）
 * 20260730-2（支持宿主清空预览草稿，并将预览大纲定位转交分页运行时）
 * 20260823-1（支持宿主 postMessage 注入回答端 UI 文案 i18n）
 */

// ===== 本地化（宿主 postMessage 注入） =====
var sbI18n = window.__SURVEY_I18N__ || {};
window.addEventListener('message', function(e) {
  if (e.data && e.data.action === 'setSurveyI18n' && e.data.map) {
    window.__SURVEY_I18N__ = Object.assign({}, window.__SURVEY_I18N__ || {}, e.data.map);
    sbI18n = window.__SURVEY_I18N__;
  }
});
function sbT(key, fallback) {
  return (sbI18n && sbI18n[key] != null) ? sbI18n[key] : fallback;
}
function _sf(key, fallback, params) {
  let msg = sbT(key, fallback);
  if (params) {
    Object.keys(params).forEach(function(k) {
      msg = msg.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
    });
  }
  return msg;
}

// ===== 常量 =====
const QUESTION_TYPES = {
  TEXTAREA: 1,
  RADIO: 8,
  CHECKBOX: 9,
  SCALE: 10,
  UPLOAD: 15,
  MATRIX_SCALE: 28,
  GENERIC: 39,
}

// 量表：兼容旧 DOM（data-option）与新骨架（仅 data-scale-value）
const SEL_SCALE_OPT_BASE = [
  '[data-survey-role="scale-group"] [data-option]',
  '[data-survey-role="scale-group"] [data-scale-value]',
]
const SEL_SCALE_OPT = SEL_SCALE_OPT_BASE.join(',')
const SEL_SCALE_ACTIVE = SEL_SCALE_OPT_BASE.flatMap(s => [
  `${s}.is-active`,
  `${s}[data-selected="true"]`,
  `${s}.sel`,
  `${s}.active`,
  `${s}.selected`,
]).join(', ')
// 矩阵选项选择器：优先标准结构，fallback 兼容 LLM 自定义 class（如 .sc）
const SEL_MATRIX_OPT_BASE = [
  '[data-survey-role="matrix-values"] [data-option]',
  '[data-survey-role="matrix-values"] [data-scale-value]',
  '[data-survey-role="matrix-group"] [data-scale-value]',
  '[data-survey-role="matrix-row"] [data-scale-value]',
  '[data-survey-role="matrix-group"] .sc',
  '[data-survey-role="matrix-row"] .sc',
]
const SEL_MATRIX_OPT = SEL_MATRIX_OPT_BASE.join(',')
const SEL_MATRIX_ACTIVE = SEL_MATRIX_OPT_BASE.flatMap(s => [
  `${s}.is-active`,
  `${s}[data-selected="true"]`,
  `${s}.sel`,
  `${s}.active`,
  `${s}.selected`,
]).join(', ')

function getCanonicalOptionLabel(option) {
  if (!option) return ''
  return String(option.getAttribute('data-option-schema-label') || getOptionLabelText(option) || '').trim()
}

function readQuestionItemCatalog(question, expectedSlot) {
  if (!question) return []
  const raw = question.getAttribute('data-question-item-catalog')
  if (!raw) return []
  try {
    const catalog = JSON.parse(raw)
    if (!catalog || catalog.slot !== expectedSlot || !Array.isArray(catalog.items)) return []
    return catalog.items
      .map(item => ({
        value: String((item && item.value) || '').trim(),
        schemaLabel: String((item && item.schemaLabel) || '').trim(),
      }))
      .filter(item => item.value && item.schemaLabel)
  } catch (e) {
    return []
  }
}

function isDynamicMatrixQuestion(question) {
  return !!question && question.getAttribute('data-dynamic-rows') === 'true'
}

function readActiveMatrixRowTitles(question) {
  if (!isDynamicMatrixQuestion(question)) return []
  const exposureRaw = question.getAttribute('data-question-item-exposure')
  if (exposureRaw) {
    try {
      const exposure = JSON.parse(exposureRaw)
      if (exposure && exposure.slot === 'matrixRows' && Array.isArray(exposure.items)) {
        const titles = exposure.items
          .map(item => String((item && (item.schemaLabel || item.label)) || '').trim())
          .filter(Boolean)
        if (titles.length > 0) return Array.from(new Set(titles))
      }
    } catch (e) {}
  }
  const titles = Array.from(
    question.querySelectorAll('[data-survey-role="matrix-group"] [data-survey-role="matrix-row"]'),
  )
    .map(row => String(row.getAttribute('data-matrix-row-label') || '').trim())
    .filter(Boolean)
  return Array.from(new Set(titles))
}

// 宿主透传的「可分享公开链接」（评测海报二维码 / 分享文案用）；由 INIT_SHARE_URL 写入，getShareUrl() 读取。
var _surveyShareUrl = ''

// ===== MessageChannel 初始化 =====
// 宿主通过 postMessage({ type: 'INIT_MESSAGE_CHANNEL' }, targetOrigin, [port2]) 传递 port2
window.addEventListener('message', async function (e) {
  if (e.data && e.data.type === 'INIT_MESSAGE_CHANNEL') {
    if (e.ports && e.ports[0]) {
      window.messagePort = e.ports[0]
      Logger.log('MessageChannel port2 已接收')

      // 在 MessageChannel 建立后，监听通过 port 发送的消息
      window.messagePort.addEventListener('message', function (event) {
        const data = event.data
        if (data && data.type === 'INIT_SAMPLE_QUESTIONS') {
          applySampleQuestionsFromParent(data)
        }
        if (data && data.type === 'INIT_UPLOAD_CONSTRAINTS') {
          applyUploadConstraintsFromParent(data)
        }
        if (data && data.type === 'INIT_SHARE_URL') {
          if (data.url) _surveyShareUrl = String(data.url)
        }
      })
      // 必须调用 start() 才能开始接收消息
      window.messagePort.start()
    }
  }
  // 跨域 iframe 无法从宿主页操作 contentDocument，由 iframe 自己加载 editor-inject.js
  if (e.data && e.data.action === 'injectEditor') {
    const existingScript = document.querySelector('script[data-editor-inject]')
    if (existingScript) existingScript.remove()
    // 优先使用宿主通过 localStorage（wj_editor_inject_url）指定的调试 URL；未设置时回退 CDN 默认。
    const injectUrl = (typeof e.data.editorInjectUrl === 'string' && e.data.editorInjectUrl.trim())
      ? e.data.editorInjectUrl
      : 'https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/editor-inject.js'
    const cb = (typeof e.data._cb === 'number') ? e.data._cb : Date.now()
    const edScript = document.createElement('script')
    edScript.src = injectUrl + (injectUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + cb
    edScript.setAttribute('data-editor-inject', 'true')
    document.head.appendChild(edScript)
    edScript.onload = function () {
      window.postMessage({ action: 'initEdit' }, '*')
    }
    edScript.onerror = function () {
      Logger.error('editor-inject.js failed to load')
    }
  }
  if (e.data && e.data.action === 'scrollTo' && e.data.selector && e.source === window.parent) {
    if (window._surveyPagination && typeof window._surveyPagination.scrollToQuestion === 'function') {
      window._surveyPagination.scrollToQuestion(e.data.selector)
    } else {
      try {
        const target = document.querySelector(e.data.selector)
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      } catch (error) {
        console.error('[survey-core] 问卷大纲定位失败', error)
      }
    }
  }
  if (e.data && e.data.action === 'resetPreview' && e.source === window.parent) {
    let clearedDraft = false
    let success = true
    try {
      if (window.SurveyRuntime && typeof window.SurveyRuntime.disableLocalDraftResume === 'function') {
        await window.SurveyRuntime.disableLocalDraftResume()
      }
      if (window.SurveyRuntime && typeof window.SurveyRuntime.clearLocalDraft === 'function') {
        await window.SurveyRuntime.clearLocalDraft()
        clearedDraft = true
      }
    } catch (error) {
      success = false
      console.error('[survey-core] 标准问卷草稿清理失败', error)
    }
    try {
      if (typeof window.clearFreeAnswerDraft === 'function') {
        await window.clearFreeAnswerDraft()
        // 自由模式的草稿保存有 120ms 防抖；等待旧任务落盘后再清一次，避免旧答案回写。
        await new Promise(resolve => setTimeout(resolve, 200))
        await window.clearFreeAnswerDraft()
        clearedDraft = true
      }
    } catch (error) {
      success = false
      console.error('[survey-core] 自由模式问卷草稿清理失败', error)
    }
    window.parent.postMessage(
      {
        action: 'resetPreviewComplete',
        requestId: e.data.requestId,
        success: success && clearedDraft,
      },
      '*',
    )
  }
})

// ===== 日志 =====
const Logger = {
  log(...args) {
    console.log('[survey-core]', ...args)
  },
  warn(...args) {
    console.warn('[survey-core]', ...args)
  },
  error(...args) {
    console.error('[survey-core]', ...args)
  },
}

function getUploadFilesFromValue(value) {
  if (!Array.isArray(value)) return []
  return value
    .map(file => {
      if (typeof file === 'string') {
        return { url: file, fileName: file.split('/').pop() || '' }
      }
      if (file && typeof file === 'object') {
        return {
          url: file.url || '',
          fileName: file.fileName || file.name || (file.url || '').split('/').pop() || '',
        }
      }
      return null
    })
    .filter(file => file && file.url)
}

function _isBlobUploadUrl(url) {
  return typeof url === 'string' && url.startsWith('blob:')
}

function _uploadSubmitFilesHaveBlob(files) {
  if (!Array.isArray(files)) return false
  return files.some(file => _isBlobUploadUrl(typeof file === 'string' ? file : file && file.url))
}

function _normalizeSubmitUploadFileEntries(files) {
  return getUploadFilesFromValue(files).map(file => ({
    url: file.url,
    fileName: file.fileName || (file.url || '').split('/').pop() || '',
  }))
}

/** 从 bridge 缓存或 DOM dataset 读取已上传的 OSS 链接（不含 blob:） */
function _resolveUploadFilesForSubmit(questionUuid, item) {
  if (questionUuid) {
    const cached = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
    const fromState = _normalizeSubmitUploadFileEntries(cached ? cached.value : [])
    const valid = fromState.filter(file => file.url && !_isBlobUploadUrl(file.url))
    if (valid.length > 0) return valid
  }

  const fileInput = item && item.querySelector('input[type="file"]')
  if (fileInput) {
    if (fileInput.dataset.uploadFiles) {
      try {
        const parsed = JSON.parse(fileInput.dataset.uploadFiles)
        const fromDataset = _normalizeSubmitUploadFileEntries(Array.isArray(parsed) ? parsed : [])
        const valid = fromDataset.filter(file => file.url && !_isBlobUploadUrl(file.url))
        if (valid.length > 0) return valid
      } catch (e) {}
    }
    if (fileInput.dataset.uploadUrl) {
      const fromUrl = fileInput.dataset.uploadUrl
        .split(',')
        .map(url => url.trim())
        .filter(url => url && !_isBlobUploadUrl(url))
      if (fromUrl.length > 0) {
        return fromUrl.map(url => ({ url, fileName: url.split('/').pop() || '' }))
      }
    }
  }

  return []
}

function syncUploadInputDataset(questionUuid, value) {
  if (!questionUuid) return
  let item = null
  try {
    item = document.querySelector(`[data-question][data-question-uuid="${CSS.escape(questionUuid)}"]`)
  } catch (e) {
    item = document.querySelector(`[data-question][data-question-uuid="${questionUuid}"]`)
  }
  const fileInput = item?.querySelector('input[type="file"]')
  if (!fileInput) return

  const files = getUploadFilesFromValue(value)
  if (files.length > 0) {
    fileInput.dataset.uploadUrl = files.map(file => file.url).join(',')
    fileInput.dataset.uploadFiles = JSON.stringify(files)
  } else {
    delete fileInput.dataset.uploadUrl
    delete fileInput.dataset.uploadFiles
  }

  // 同步渲染已上传文件列表 + 控制上传入口可见性
  if (item) renderUploadQuestionUI(item)
}

// ===== 上传题：限制读取 / 校验 / UI 渲染 =====

/**
 * 读取上传题的限制配置（来自题目根节点的 data-* 属性）
 * @param {HTMLElement} item
 * @returns {{ maxFileCount: number, maxFileSize: number, fileTypes: string[] }}
 *   - maxFileCount: 最多可上传文件数（默认 99，相当于不限制）
 *   - maxFileSize: 单文件最大体积，单位 KB（默认 10240 = 10MB）
 *   - fileTypes: 允许的扩展名数组（小写，去掉点），为空表示不限制
 */
function getUploadConstraints(item) {
  const rawCount = Number(item?.getAttribute('data-max-file-count'))
  const maxFileCount = Number.isFinite(rawCount) && rawCount > 0 ? rawCount : 99
  const rawSize = Number(item?.getAttribute('data-max-file-size'))
  const maxFileSize = Number.isFinite(rawSize) && rawSize > 0 ? rawSize : 10240
  const fileTypesStr = item?.getAttribute('data-file-types') || ''
  const fileTypes = fileTypesStr
    ? fileTypesStr
        .split(',')
        .map(t => t.trim().toLowerCase().replace(/^\./, ''))
        .filter(Boolean)
    : []
  return { maxFileCount, maxFileSize, fileTypes }
}

function _getFileExtension(name) {
  if (!name || typeof name !== 'string') return ''
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

/**
 * 简易 toast，用于上传校验失败提示。复用页面 .nv-toast 容器（若存在），否则临时创建。
 */
function _uploadToast(msg) {
  if (!msg) return
  try {
    const el = document.createElement('div')
    el.textContent = msg
    el.style.cssText =
      'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.75);color:#fff;padding:10px 20px;border-radius:8px;font-size:14px;z-index:99999;transition:opacity .3s;max-width:80%;text-align:center;'
    document.body.appendChild(el)
    setTimeout(() => {
      el.style.opacity = '0'
      setTimeout(() => el.remove(), 300)
    }, 2200)
  } catch (e) {
    Logger.warn('upload toast 渲染失败:', e)
  }
}

// 上传题容器的 MutationObserver 注册表：避免对同一题反复 observe
const _uploadObservers = typeof WeakMap !== 'undefined' ? new WeakMap() : null
// 标记正在 apply 的题目：防止 _applyUploadEntryState 自身改写 .up 属性时再触发 labelObserver
const _uploadApplyingItems = typeof WeakSet !== 'undefined' ? new WeakSet() : null

/**
 * 维护上传题的「上传入口」位置与可见性。
 * 现场行为：组件渲染已上传文件时会插入 .up-card，并把上传入口 <label class="up"> 留在 .up-card 之前且隐藏。
 * 我们需要：
 *  1. 保留组件原 DOM 结构（不渲染额外文件名），保持原左对齐布局；
 *  2. 在 .qb 下建立 .up-wrap 容器（横向 flex + 8px gap），把所有 .up-card 和 .up 收纳进去，.up 永远位于末尾；
 *  3. 已上传文件数（SurveyAnswerState.answers 缓存）达到 data-max-file-count 时隐藏 .up 并禁用 input，否则强制显示；
 *  4. maxFileCount > 1 时给 input 加 multiple，允许一次选多个文件；
 *  5. 由于 .up-card 由其他组件异步插入到 .qb，使用 MutationObserver 监听 .qb，确保后续插入的 .up-card 能被搬入 .up-wrap。
 * @param {HTMLElement} item 题目根节点（data-question）
 */
function renderUploadQuestionUI(item) {
  if (!item) return
  const type = Number(item.getAttribute('data-question-type') || '0')
  if (type !== QUESTION_TYPES.UPLOAD && type !== 14) return
  const fileInput = item.querySelector('input[type="file"]')
  if (!fileInput) return

  _applyUploadEntryState(item)
  _ensureUploadObserver(item)
}

/**
 * 计算并应用 .up 入口的位置 / 可见性 / disabled 状态。
 * 同时确保 .qb 下存在 .up-wrap 容器：把所有 .up-card 和 .up 都收纳进去，横向排版、间距 8px。
 * @param {HTMLElement} item
 */
function _applyUploadEntryState(item) {
  const fileInput = item.querySelector('input[type="file"]')
  if (!fileInput) return
  const upLabel = fileInput.closest('label.up') || fileInput.closest('label')
  if (!upLabel) return
  if (_uploadApplyingItems) _uploadApplyingItems.add(item)

  // 兼容多层结构：.up 可能直接在 .qb 下，也可能已被包在 .up-wrap 里（HTML 模板或 bridge 之前的运行结果）
  let upWrap = upLabel.closest('.up-wrap')
  const qb = upWrap ? upWrap.parentElement : upLabel.parentElement
  if (!qb) return

  // 找/建 .up-wrap（横向 flex + 8px gap）
  if (!upWrap) {
    upWrap = qb.querySelector(':scope > .up-wrap')
    if (!upWrap) {
      upWrap = document.createElement('div')
      upWrap.className = 'up-wrap'
      upWrap.style.setProperty('display', 'flex', 'important')
      upWrap.style.setProperty('flex-direction', 'row', 'important')
      upWrap.style.setProperty('flex-wrap', 'wrap', 'important')
      upWrap.style.setProperty('align-items', 'flex-start', 'important')
      upWrap.style.setProperty('gap', '8px', 'important')
      qb.appendChild(upWrap)
    }
  }

  // 把 .qb 直接子节点里散落的 .up-card 全部移入 .up-wrap
  qb.querySelectorAll(':scope > .up-card').forEach(card => {
    upWrap.appendChild(card)
  })

  // 把 .up 移到 .up-wrap 末尾（位于所有 .up-card 之后）
  if (upWrap.lastElementChild !== upLabel) {
    upWrap.appendChild(upLabel)
  }

  const questionUuid = item.getAttribute('data-question-uuid') || ''
  const cached = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
  const cachedFiles = getUploadFilesFromValue(cached ? cached.value : [])
  // 以 UI 可见的 .up-card 数量为准（所见即所得，避免缓存与渲染时序错位）；
  // 若组件未渲染 .up-card，则用缓存数量兜底。
  const upCardCount = upWrap.querySelectorAll('.up-card').length
  const effectiveCount = upCardCount > 0 ? upCardCount : cachedFiles.length
  const { maxFileCount } = getUploadConstraints(item)
  const reachedLimit = effectiveCount >= maxFileCount

  // 已上传数达到上限：隐藏入口、禁用 input；未达上限：强制显示并可点击
  if (reachedLimit) {
    upLabel.style.setProperty('display', 'none', 'important')
  } else {
    upLabel.style.setProperty('display', 'flex', 'important')
    upLabel.style.removeProperty('visibility')
    upLabel.removeAttribute('hidden')
  }
  fileInput.disabled = reachedLimit

  if (maxFileCount > 1 && !fileInput.hasAttribute('multiple')) {
    fileInput.setAttribute('multiple', 'multiple')
  }

  Logger.log(
    '[upload]', questionUuid,
    'upCards=', upCardCount,
    'cached=', cachedFiles.length,
    'effective=', effectiveCount,
    'maxFileCount=', maxFileCount,
    'reachedLimit=', reachedLimit,
  )

  // 释放 apply 标记，让 labelObserver 重新生效（用 rAF 确保在本帧的 mutation 通知派发之后）
  if (_uploadApplyingItems) {
    const release = () => { _uploadApplyingItems.delete(item) }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(release)
    else setTimeout(release, 0)
  }
}

/**
 * 监听 .up 所在容器的子节点变化（.up-card 异步插入），插入后重新整理 .up 的位置/可见性。
 * @param {HTMLElement} item
 */
function _ensureUploadObserver(item) {
  if (!item || typeof MutationObserver === 'undefined') return
  if (_uploadObservers && _uploadObservers.has(item)) return
  const fileInput = item.querySelector('input[type="file"]')
  if (!fileInput) return
  const upLabel = fileInput.closest('label.up') || fileInput.closest('label')
  if (!upLabel || !upLabel.parentElement) return
  // 监听 .qb 与 .up-wrap：组件会把新的 .up-card 异步插入到 .qb 或 .up-wrap 直接子节点里
  const upWrap = upLabel.closest('.up-wrap')
  const qb = upWrap ? upWrap.parentElement : upLabel.parentElement
  if (!qb) return

  let scheduled = false
  const schedule = () => {
    if (scheduled) return
    scheduled = true
    const run = () => {
      scheduled = false
      _applyUploadEntryState(item)
    }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run)
    else setTimeout(run, 0)
  }

  // 1) .qb 子节点变化（组件异步插入的 .up-card）
  const containerObserver = new MutationObserver(schedule)
  containerObserver.observe(qb, { childList: true, subtree: false })

  // 2) .up-wrap 子节点变化（若组件直接往 .up-wrap 插或者删 .up）
  let wrapObserver = null
  if (upWrap) {
    wrapObserver = new MutationObserver(schedule)
    wrapObserver.observe(upWrap, { childList: true, subtree: false })
  }

  // 3) .up 自身属性变化（防止外部把 .up 改成 display:none / hidden）
  const labelObserver = new MutationObserver(() => {
    if (_uploadApplyingItems && _uploadApplyingItems.has(item)) return
    schedule()
  })
  labelObserver.observe(upLabel, { attributes: true, attributeFilter: ['style', 'hidden', 'class'] })

  if (_uploadObservers) _uploadObservers.set(item, { containerObserver, wrapObserver, labelObserver })
}

/**
 * 从答案缓存中移除某个已上传文件，并触发 UI 重渲染。
 * @param {string} questionUuid
 * @param {number} index
 */
function removeUploadFile(questionUuid, index) {
  if (!questionUuid || !Number.isInteger(index) || index < 0) return
  const entry = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
  const current = entry && Array.isArray(entry.value) ? entry.value.slice() : []
  if (index >= current.length) return
  current.splice(index, 1)
  // 推断题型：优先用 entry，否则从 DOM
  let typeNum = entry ? entry.questionType : QUESTION_TYPES.UPLOAD
  if (!typeNum) {
    let domItem = null
    try {
      domItem = document.querySelector(`[data-question][data-question-uuid="${CSS.escape(questionUuid)}"]`)
    } catch (e) {
      domItem = document.querySelector(`[data-question][data-question-uuid="${questionUuid}"]`)
    }
    if (domItem) typeNum = Number(domItem.getAttribute('data-question-type'))
  }
  saveAnswerLocal(questionUuid, typeNum || QUESTION_TYPES.UPLOAD, current)
}

// ===== 全局状态 =====
const SurveyAnswerState = {
  answers: [], // [{ questionUuid, questionType, value, timestamp }]
  isSubmitting: false,
  sampleQuestions: null, // { [questionUuid]: string[] } 样本库必选项配置
  checkboxSampleGuardTimers: {}, // { [questionUuid]: number } debounce 定时器
}

// ===== 样本库筛查 =====
function applySampleQuestionsFromParent(data) {
  let { sampleQuestions } = data || {}
  if (!sampleQuestions) return

  if (typeof sampleQuestions === 'string') {
    try {
      sampleQuestions = JSON.parse(sampleQuestions)
    } catch (err) {
      Logger.warn('sampleQuestions JSON 解析失败:', err)
      return
    }
  }

  if (!sampleQuestions || typeof sampleQuestions !== 'object' || Array.isArray(sampleQuestions)) return
  SurveyAnswerState.sampleQuestions = sampleQuestions
  Logger.log('已注入 sampleQuestions，题目数:', Object.keys(sampleQuestions).length)
}

/**
 * 接收宿主页传入的上传题限制，patch 到对应题目根节点的 data-* 属性。
 * payload 形态二选一：
 *   1. { type: 'INIT_UPLOAD_CONSTRAINTS', uploadConstraints: { [uuid]: { maxFileCount, maxFileSize, fileTypes } } }
 *   2. { type: 'INIT_UPLOAD_CONSTRAINTS', uploadQuestions: [{ uuid, maxFileCount, maxFileSize, fileTypes }, ...] }
 * 任一字段可为 JSON 字符串。
 */
function applyUploadConstraintsFromParent(data) {
  let constraints = data?.uploadConstraints
  let list = data?.uploadQuestions

  if (typeof constraints === 'string') {
    try { constraints = JSON.parse(constraints) } catch (err) { Logger.warn('uploadConstraints JSON 解析失败:', err); constraints = null }
  }
  if (typeof list === 'string') {
    try { list = JSON.parse(list) } catch (err) { Logger.warn('uploadQuestions JSON 解析失败:', err); list = null }
  }

  const map = {}
  if (Array.isArray(list)) {
    list.forEach(item => {
      const uuid = item && (item.uuid || item.questionUuid)
      if (uuid) map[uuid] = item
    })
  }
  if (constraints && typeof constraints === 'object' && !Array.isArray(constraints)) {
    Object.keys(constraints).forEach(uuid => { map[uuid] = constraints[uuid] })
  }

  const uuids = Object.keys(map)
  if (uuids.length === 0) return

  let patched = 0
  uuids.forEach(uuid => {
    let item = null
    try {
      item = document.querySelector(`[data-question][data-question-uuid="${CSS.escape(uuid)}"]`)
    } catch (e) {
      item = document.querySelector(`[data-question][data-question-uuid="${uuid}"]`)
    }
    if (!item) return
    const cfg = map[uuid] || {}
    const maxCount = Number(cfg.maxFileCount)
    if (Number.isFinite(maxCount) && maxCount > 0) {
      item.setAttribute('data-max-file-count', String(maxCount))
    }
    const maxSize = Number(cfg.maxFileSize)
    if (Number.isFinite(maxSize) && maxSize > 0) {
      item.setAttribute('data-max-file-size', String(maxSize))
    }
    if (Array.isArray(cfg.fileTypes) && cfg.fileTypes.length > 0) {
      item.setAttribute('data-file-types', cfg.fileTypes.join(','))
    } else if (typeof cfg.fileTypes === 'string' && cfg.fileTypes.trim()) {
      item.setAttribute('data-file-types', cfg.fileTypes.trim())
    }
    renderUploadQuestionUI(item)
    patched += 1
  })
  Logger.log('已注入 uploadConstraints，命中题目数:', patched, '/', uuids.length)
}

/**
 * 检查单个单选题是否满足样本要求的允许项（或关系）
 * @param {HTMLElement} questionItem
 * @returns {boolean}
 */
function _checkOneRadioQuestionSampleRequirement(questionItem) {
  const sampleQuestions = SurveyAnswerState.sampleQuestions
  if (sampleQuestions == null || !questionItem) return true
  const questionId = questionItem.getAttribute('data-question-uuid')
  if (!questionId) return true
  const sampleOptions = sampleQuestions[questionId]
  if (!Array.isArray(sampleOptions) || sampleOptions.length === 0) return true

  const input = questionItem.querySelector('input[type="radio"]:checked')
  if (!input) return true
  let opt = input.closest('[data-option]')
  if (!opt && input.parentElement && input.parentElement.hasAttribute('data-option')) {
    opt = input.parentElement
  }
  const selectedOption = opt ? getOptionLabelText(opt) : input.value
  return sampleOptions.includes(selectedOption)
}

/**
 * 批量检查指定范围内的单选题样本要求
 * @param {HTMLElement} [rootEl]
 * @returns {boolean}
 */
function _checkRadioSampleRequirements(rootEl) {
  const sampleQuestions = SurveyAnswerState.sampleQuestions
  if (sampleQuestions == null) return true
  const root = rootEl || document

  const items = root.querySelectorAll ? Array.from(root.querySelectorAll('[data-question]')) : []
  if (root.matches && root.matches('[data-question]')) items.unshift(root)

  for (const item of items) {
    const type = Number(item.getAttribute('data-question-type') || '0')
    if (type !== QUESTION_TYPES.RADIO) continue
    if (!_checkOneRadioQuestionSampleRequirement(item)) return false
  }
  return true
}

/**
 * 检查单个多选题是否满足样本要求的必选项（且关系）
 * @param {HTMLElement} questionItem
 * @returns {boolean}
 */
function _checkOneCheckboxQuestionSampleRequirement(questionItem) {
  const sampleQuestions = SurveyAnswerState.sampleQuestions
  if (sampleQuestions == null || !questionItem) return true
  const questionId = questionItem.getAttribute('data-question-uuid')
  if (!questionId) return true
  const sampleOptions = sampleQuestions[questionId]
  if (!Array.isArray(sampleOptions) || sampleOptions.length === 0) return true

  const selectedOptions = []
  questionItem.querySelectorAll('input[type="checkbox"]:checked').forEach(input => {
    const opt = input.closest('[data-option]')
    const label = opt ? getOptionLabelText(opt) : input.value
    selectedOptions.push(label)
  })
  const missingRequired = sampleOptions.some(req => !selectedOptions.includes(req))
  return !missingRequired
}

/**
 * 批量检查指定范围内的多选题样本要求
 * @param {HTMLElement} [rootEl]
 * @returns {boolean}
 */
function _checkCheckboxSampleRequirements(rootEl) {
  const sampleQuestions = SurveyAnswerState.sampleQuestions
  if (sampleQuestions == null) return true
  const root = rootEl || document

  const items = root.querySelectorAll ? Array.from(root.querySelectorAll('[data-question]')) : []
  if (root.matches && root.matches('[data-question]')) items.unshift(root)

  for (const item of items) {
    const type = Number(item.getAttribute('data-question-type') || '0')
    if (type !== QUESTION_TYPES.CHECKBOX) continue
    if (!_checkOneCheckboxQuestionSampleRequirement(item)) return false
  }
  return true
}

/**
 * 批量检查指定范围内的样本要求
 * @param {HTMLElement} [rootEl]
 * @returns {boolean}
 */
function _checkSampleRequirements(rootEl) {
  return _checkRadioSampleRequirements(rootEl) && _checkCheckboxSampleRequirements(rootEl)
}

/**
 * 调度样本缺失信号发送（debounce）
 * @param {string} questionId
 * @param {boolean} missingRequired
 * @param {number} [delayMs]
 */
function _scheduleCheckboxSampleGuard(questionId, missingRequired, delayMs) {
  if (!questionId) return
  const ms = Number.isFinite(delayMs) && delayMs >= 0 ? delayMs : 1500
  const timers = SurveyAnswerState.checkboxSampleGuardTimers
  if (timers[questionId]) {
    clearTimeout(timers[questionId])
    delete timers[questionId]
  }
  if (!missingRequired) return
  timers[questionId] = setTimeout(() => {
    const q = document.querySelector(`[data-question-uuid="${CSS.escape(questionId)}"]`)
    if (q && !_checkOneCheckboxQuestionSampleRequirement(q)) {
      API.sendNonSampleSignal()
    }
    delete timers[questionId]
  }, ms)
}

// ===== 答案读取器（按题型）=====
const AnswerReader = {
  /** 读取单选答案 */
  radio(item) {
    const checked = item.querySelector('input[type="radio"]:checked')
    if (!checked) return null
    let opt = checked.closest('[data-option]')
    // fallback：若 input 被 CSS 隐藏或脱离标准层级，尝试父元素
    if (!opt && checked.parentElement && checked.parentElement.hasAttribute('data-option')) {
      opt = checked.parentElement
    }
    const isOther = opt && opt.hasAttribute('data-option-other')
    const otherInput = isOther ? opt.querySelector('[data-other-input]') : null
    const otherText = otherInput ? otherInput.value.trim() : null
    return {
      optionValue: opt ? opt.getAttribute('data-option-value') : null,
      value: opt ? getOptionLabelText(opt) : checked.value,
      schemaLabel: opt ? getCanonicalOptionLabel(opt) : checked.value,
      otherText: otherText || null,
    }
  },

  /** 读取多选答案 */
  checkbox(item) {
    const checked = item.querySelectorAll('input[type="checkbox"]:checked')
    const optionValues = []
    const values = []
    const otherTexts = []
    const schemaLabels = []
    checked.forEach(input => {
      let opt = input.closest('[data-option]')
      if (!opt && input.parentElement && input.parentElement.hasAttribute('data-option')) {
        opt = input.parentElement
      }
      if (opt) {
        const isOther = opt.hasAttribute('data-option-other')
        const otherInput = isOther ? opt.querySelector('[data-other-input]') : null
        const otherText = otherInput ? otherInput.value.trim() : null
        optionValues.push(opt.getAttribute('data-option-value') || input.value)
        values.push(getOptionLabelText(opt) || input.value)
        schemaLabels.push(getCanonicalOptionLabel(opt) || input.value)
        otherTexts.push(otherText || null)
      } else {
        optionValues.push(input.value)
        values.push(input.value)
        schemaLabels.push(input.value)
        otherTexts.push(null)
      }
    })
    return { optionValues, value: values, schemaLabels, otherTexts }
  },

  /** 读取文本答案 */
  textarea(item) {
    const input = item.querySelector('[data-input-type="text"]')
    if (!input) return null
    if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
      return input.value
    }
    return input.textContent || ''
  },

  /** 读取量表答案 */
  scale(item) {
    const selected = item.querySelector(SEL_SCALE_ACTIVE)
    if (!selected) return null
    return parseScaleValue(selected)
  },

  /** 读取矩阵量表答案 */
  matrixScale(item) {
    // 优先标准结构，fallback 遍历 matrix-group 子元素或带 data-matrix-row-label 的元素
    let rows = item.querySelectorAll('[data-survey-role="matrix-group"] [data-survey-role="matrix-row"]')
    if (!rows.length) {
      const group = item.querySelector('[data-survey-role="matrix-group"]')
      if (group) {
        rows = group.querySelectorAll('[data-matrix-row-label]')
        if (!rows.length) rows = group.children
      }
    }
    const result = []
    rows.forEach(row => {
      const rowTitle = row.getAttribute('data-matrix-row-label') || row.getAttribute('data-matrix-row')
      if (!rowTitle) return
      const selected = row.querySelector(SEL_MATRIX_ACTIVE)
      if (!selected) return
      const score = parseScaleValue(selected)
      if (score !== null) {
        result.push({ rowTitle, score })
      }
    })
    return result
  },

  /** 读取上传文件答案 */
  upload(item) {
    // 上传题答案由 SurveyDataBridge.uploadFile 返回后手动存入
    const questionUuid = item.getAttribute('data-question-uuid')
    const existing = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
    return existing ? existing.value : []
  },

  /** 读取自定义题答案 */
  generic(item) {
    const existing = SurveyAnswerState.answers.find(a => a.questionUuid === item.getAttribute('data-question-uuid'))
    return existing ? existing.value : null
  },
}

/** 从元素解析量表分值 */
function parseScaleValue(el) {
  const raw = el.getAttribute('data-scale-value') || el.textContent.trim()
  const n = Number.parseFloat(raw)
  return Number.isNaN(n) ? null : n
}

/** 根据题型读取答案 */
function readAnswerByType(item, type) {
  const t = Number(type)
  switch (t) {
    case QUESTION_TYPES.RADIO:
      return AnswerReader.radio(item)
    case QUESTION_TYPES.CHECKBOX:
      return AnswerReader.checkbox(item)
    case QUESTION_TYPES.TEXTAREA:
      return AnswerReader.textarea(item)
    case 3:
      return AnswerReader.textarea(item) // 多行文本（旧模板兼容）
    case QUESTION_TYPES.SCALE:
      return AnswerReader.scale(item)
    case QUESTION_TYPES.MATRIX_SCALE:
      return AnswerReader.matrixScale(item)
    case QUESTION_TYPES.UPLOAD:
      return AnswerReader.upload(item)
    case 14:
      return AnswerReader.upload(item) // 图片上传（旧模板兼容）
    case QUESTION_TYPES.GENERIC:
      return AnswerReader.generic(item)
    default:
      return null
  }
}

/** 判断答案是否为空 */
function isEmptyAnswer(value) {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

// ===== 答案存储 =====
function saveAnswerLocal(questionUuid, questionType, value) {
  const idx = SurveyAnswerState.answers.findIndex(a => a.questionUuid === questionUuid)
  const entry = {
    questionUuid,
    questionType: Number(questionType),
    value,
    timestamp: Date.now(),
  }
  if (idx >= 0) {
    SurveyAnswerState.answers[idx] = entry
  } else {
    SurveyAnswerState.answers.push(entry)
  }
  if (Number(questionType) === QUESTION_TYPES.UPLOAD || Number(questionType) === 14) {
    syncUploadInputDataset(questionUuid, value)
  }

  // 通过 SurveyApp API 通知 UI 层更新状态，不直接操作 DOM
  Logger.log(
    'SurveyApp 检查:',
    typeof window.SurveyApp,
    window.SurveyApp ? typeof window.SurveyApp.setCustomValue : 'N/A',
  )
  if (typeof window.SurveyApp !== 'undefined' && window.SurveyApp.setCustomValue) {
    try {
      window.SurveyApp.setCustomValue(questionUuid, value)
      Logger.log('SurveyApp.setCustomValue 调用成功')
    } catch (e) {
      Logger.warn('SurveyApp.setCustomValue 调用失败:', e)
    }
  } else {
    Logger.warn('SurveyApp 不可用，跳过 UI 通知')
  }

  // 派发答案变化事件（供外部监听）
  // 统一 detail.value 格式。radio/checkbox 的 AnswerReader 返回 { optionValue(s), value } 对象，
  // 事件派发时提取 value 字段（字符串/数组），与 survey-ui.js 的 dispatch 格式保持一致。
  // 签名短路：同一题目值未变时不重复派发，防止 LLM 逻辑震荡。
  try {
    const sigStore = saveAnswerLocal._lastSignatures || (saveAnswerLocal._lastSignatures = {})
    let sig = value
    if (typeof value === 'object' && value !== null) {
      try {
        sig = JSON.stringify(value)
      } catch (e) {}
    }
    if (sigStore[questionUuid] === sig) {
      Logger.log('签名相同，跳过重复事件:', questionUuid)
    } else {
      sigStore[questionUuid] = sig
      let eventValue = value
      if (value && typeof value === 'object' && !Array.isArray(value) && value.value !== undefined) {
        eventValue = value.value
      }
      const detail = {
        questionUuid,
        questionType: Number(questionType),
        value: eventValue,
        rawValue: value,
      }
      // "其它"选项：附加 otherText 到事件 detail
      if (value && typeof value === 'object' && !Array.isArray(value) && value.otherText) {
        detail.otherText = value.otherText
      }
      if (value && typeof value === 'object' && Array.isArray(value.otherTexts)) {
        detail.otherTexts = value.otherTexts
      }
      document.dispatchEvent(
        new CustomEvent('surveyAnswerChanged', {
          detail: detail,
        }),
      )
    }
  } catch (e) {}

  Logger.log('答案已保存:', questionUuid, value)
}

// ===== 自动事件绑定 =====
function autoBindQuestions() {
  const container =
    document.querySelector('[data-survey-role="survey"]') || document.querySelector('.sh') || document.body
  if (!container) {
    Logger.warn('未找到问卷容器，自动绑定失败')
    return
  }

  // 单选/多选 change（比 click 更可靠，不受 survey-ui.js 拦截影响）
  container.addEventListener('change', e => {
    const input = e.target.closest('input[type="radio"], input[type="checkbox"]')
    if (!input) return
    let opt = input.closest('[data-option]')
    if (!opt && input.parentElement && input.parentElement.hasAttribute('data-option')) {
      opt = input.parentElement
    }
    if (!opt) return
    const item = opt.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))

    if (type === QUESTION_TYPES.RADIO && input.type === 'radio' && input.checked) {
      const answer = AnswerReader.radio(item)
      if (answer) saveAnswerLocal(item.getAttribute('data-question-uuid'), type, answer)
      // 样本库筛查：单选题选后立即检查
      if (!_checkOneRadioQuestionSampleRequirement(item)) {
        API.sendNonSampleSignal()
      }
    } else if (type === QUESTION_TYPES.CHECKBOX && input.type === 'checkbox') {
      const answer = AnswerReader.checkbox(item)
      if (answer) saveAnswerLocal(item.getAttribute('data-question-uuid'), type, answer)
      // 样本库筛查：多选题选后实时检查
      const questionId = item.getAttribute('data-question-uuid')
      const missingRequired = !_checkOneCheckboxQuestionSampleRequirement(item)
      _scheduleCheckboxSampleGuard(questionId, missingRequired)
    }
  })

  // 量表题点击 — 直接读被点击元素的值，不事后搜 .sel（避免与 survey-ui.js 时序竞争）
  container.addEventListener('click', e => {
    const sc = e.target.closest(SEL_SCALE_OPT)
    if (!sc) return
    const item = sc.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))
    if (type !== QUESTION_TYPES.SCALE) return

    const score = parseScaleValue(sc)
    if (score !== null) saveAnswerLocal(item.getAttribute('data-question-uuid'), type, score)
  })

  // 矩阵量表题点击 — 直接读被点击元素的值，合并已有行答案
  container.addEventListener('click', e => {
    const sc = e.target.closest(SEL_MATRIX_OPT)
    if (!sc) return
    let row = sc.closest('[data-survey-role="matrix-row"]')
    if (!row && sc.parentElement) {
      // fallback：尝试父元素链中带有 matrix-row 标记的元素
      row = sc.parentElement.closest('[data-survey-role="matrix-row"]')
    }
    if (!row) return
    const item = sc.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))
    if (type !== QUESTION_TYPES.MATRIX_SCALE) return

    const rowTitle = row.getAttribute('data-matrix-row-label') || row.getAttribute('data-matrix-row')
    if (!rowTitle) return
    const score = parseScaleValue(sc)
    if (score === null) return

    const questionUuid = item.getAttribute('data-question-uuid')
    const cached = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
    let merged = []
    if (cached && Array.isArray(cached.value)) {
      merged = cached.value.filter(r => r.rowTitle !== rowTitle)
    }
    merged.push({ rowTitle, score })
    saveAnswerLocal(questionUuid, type, merged)
  })

  // 文本输入
  container.addEventListener('input', e => {
    const input = e.target.closest('[data-input-type="text"]')
    if (!input) return
    const item = input.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))
    if (type !== QUESTION_TYPES.TEXTAREA) return

    const answer = input.value !== undefined ? input.value : input.textContent || ''
    saveAnswerLocal(item.getAttribute('data-question-uuid'), type, answer)
  })

  // "其它"选项输入框输入
  container.addEventListener('input', e => {
    const otherInput = e.target.closest('[data-other-input]')
    if (!otherInput) return
    const item = otherInput.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))

    if (type === QUESTION_TYPES.RADIO) {
      const answer = AnswerReader.radio(item)
      if (answer) saveAnswerLocal(item.getAttribute('data-question-uuid'), type, answer)
    } else if (type === QUESTION_TYPES.CHECKBOX) {
      const answer = AnswerReader.checkbox(item)
      if (answer) saveAnswerLocal(item.getAttribute('data-question-uuid'), type, answer)
    }
  })

  // 文件上传
  container.addEventListener('change', async e => {
    const fileInput = e.target.closest('input[type="file"]')
    if (!fileInput) return
    const item = fileInput.closest('[data-question]')
    if (!item) return
    const type = Number(item.getAttribute('data-question-type'))
    if (type !== QUESTION_TYPES.UPLOAD && type !== 14) return

    const questionId = item.getAttribute('data-question-uuid')
    const selected = [...(fileInput.files || [])]
    if (selected.length === 0) return

    // 读取限制并基于已有文件数判断剩余可上传配额
    const { maxFileCount, maxFileSize, fileTypes } = getUploadConstraints(item)
    const existing = SurveyAnswerState.answers.find(a => a.questionUuid === questionId)
    const current = existing && Array.isArray(existing.value) ? existing.value.slice() : []
    const remaining = Math.max(0, maxFileCount - current.length)

    // 已达上限：直接拦截
    if (remaining <= 0) {
      _uploadToast(_sf('SurveyRuntime.Upload Max Count', '最多只能上传 {count} 个文件', { count: maxFileCount }))
      fileInput.value = ''
      return
    }

    // 数量超限：截断到剩余配额，并提示
    let candidates = selected
    if (selected.length > remaining) {
      _uploadToast(_sf('SurveyRuntime.Upload Max Count Keep', '最多只能上传 {count} 个文件，仅保留前 {keep} 个', { count: maxFileCount, keep: remaining }))
      candidates = selected.slice(0, remaining)
    }

    // 类型 / 大小校验
    const valid = []
    const rejected = []
    for (const file of candidates) {
      const ext = _getFileExtension(file.name)
      if (fileTypes.length > 0 && ext && !fileTypes.includes(ext)) {
        rejected.push({ file, reason: _sf('SurveyRuntime.Upload Unsupported Type', '不支持的文件类型 .{ext}', { ext }) })
        continue
      }
      if (Number.isFinite(maxFileSize) && file.size > maxFileSize * 1024) {
        rejected.push({ file, reason: _sf('SurveyRuntime.Upload Too Large', '文件 {name} 超过 {size}KB 限制', { name: file.name, size: maxFileSize }) })
        continue
      }
      valid.push(file)
    }
    if (rejected.length > 0) {
      _uploadToast(rejected[0].reason)
    }

    if (valid.length === 0) {
      fileInput.value = ''
      return
    }

    const uploaded = []
    for (const file of valid) {
      try {
        const result = await API.uploadFiles(file, questionId)
        uploaded.push(result)
      } catch (err) {
        Logger.error('文件上传失败:', err)
        _uploadToast(_sf('SurveyRuntime.Upload File Failed', '文件 {name} 上传失败', { name: file.name }))
      }
    }

    // 重新读取最新缓存（避免并发上传期间状态被覆盖）
    const latest = SurveyAnswerState.answers.find(a => a.questionUuid === questionId)
    const latestCurrent = latest && Array.isArray(latest.value) ? latest.value.slice() : current
    const merged = latestCurrent.concat(uploaded)
    saveAnswerLocal(questionId, type, merged)

    // 重置 file input，允许再次选择相同文件名
    fileInput.value = ''
  })

  // 初始化：根据已有答案设置上传题 input 的 disabled / multiple 状态
  container.querySelectorAll('[data-question]').forEach(q => {
    const t = Number(q.getAttribute('data-question-type'))
    if (t === QUESTION_TYPES.UPLOAD || t === 14) {
      renderUploadQuestionUI(q)
    }
  })
}

/**
 * 将 File 对象转换为 Blob
 * @param {File} file
 * @returns {Promise<Blob>}
 */
async function fileToBlob(file) {
  const arrayBuffer = await file.arrayBuffer()
  return new Blob([arrayBuffer], { type: file.type })
}

// ===== API：与父页面通信 =====
const API = {
  async uploadFiles(file, questionId) {
    if (!(file instanceof File)) {
      throw new TypeError(sbT('SurveyRuntime.Upload Invalid File', '上传的不是有效 File 对象'))
    }
    if (!questionId) {
      throw new Error(sbT('SurveyRuntime.QuestionId Required', 'questionId 不能为空'))
    }

    const requestId = `upload_${Date.now()}_${Math.random().toString(36).slice(2)}`
    return new Promise((resolve, reject) => {
      const handleResponse = event => {
        const data = event.data || event
        if (data.type === 'UPLOAD_FILE_RESPONSE' && data.requestId === requestId) {
          cleanup()
          if (data.data !== null) resolve(data.data)
          else reject(new Error(data.errorMsg || sbT('SurveyRuntime.Upload Failed', '文件上传失败')))
        }
      }
      const cleanup = () => {
        if (window.messagePort) window.messagePort.removeEventListener('message', handleResponse)
        else window.removeEventListener('message', handleResponse)
      }
      if (window.messagePort) window.messagePort.addEventListener('message', handleResponse)
      else window.addEventListener('message', handleResponse)

      setTimeout(() => {
        cleanup()
        reject(new Error(sbT('SurveyRuntime.Upload Timeout', '上传超时')))
      }, 30000)

      if (window.messagePort) {
        fileToBlob(file).then(blob => {
          window.messagePort.postMessage({
            type: 'UPLOAD_FILE_REQUEST',
            requestId,
            questionId,
            file: blob,
            fileName: file.name,
          })
        })
      } else {
        const payload = { type: 'UPLOAD_FILE_REQUEST', requestId, questionId, file, fileName: file.name }
        window.parent.postMessage(payload, '*')
      }
    })
  },

  async updateAnswers(answers, originSurveyAnswer, evalResult) {
    const payload = {
      type: 'SUBMIT',
      answers,
      originSurveyAnswer: originSurveyAnswer || '',
    }
    if (evalResult != null && String(evalResult).trim()) {
      payload.evalResult = String(evalResult).trim()
    }
    if (window.messagePort) window.messagePort.postMessage(payload)
    else window.parent.postMessage(payload, '*')
  },

  /**
   * 无刷新落库：把答案持久化到后端，但不触发宿主隐藏 iframe / 跳转完成页。
   * 与 updateAnswers 的唯一区别是消息类型 'SUBMIT_NO_REDIRECT'，宿主收到后只落库、保持卷内停留。
   * 宿主若实现了回告会发回 'SUBMIT_NO_REDIRECT_RESULT'；未实现时本方法 2.5s 后按已发送处理，绝不卡死。
   * @param {Array} answers
   * @param {string} originSurveyAnswer
   * @param {string} [evalResult] 评测结果展示字符串
   * @returns {Promise<{success:boolean, pending?:boolean, err?:string}>}
   */
  persistAnswers(answers, originSurveyAnswer, evalResult) {
    const payload = {
      type: 'SUBMIT_NO_REDIRECT',
      answers,
      originSurveyAnswer: originSurveyAnswer || '',
    }
    if (evalResult != null && String(evalResult).trim()) {
      payload.evalResult = String(evalResult).trim()
    }
    return new Promise(resolve => {
      var settled = false
      function cleanup() {
        if (window.messagePort) window.messagePort.removeEventListener('message', onMsg)
        window.removeEventListener('message', onMsg)
      }
      function onMsg(ev) {
        var d = ev && ev.data
        if (d && d.type === 'SUBMIT_NO_REDIRECT_RESULT') {
          if (settled) return
          settled = true
          cleanup()
          resolve({ success: !!d.success, err: d.err })
        }
      }
      if (window.messagePort) window.messagePort.addEventListener('message', onMsg)
      window.addEventListener('message', onMsg)
      if (window.messagePort) window.messagePort.postMessage(payload)
      else window.parent.postMessage(payload, '*')
      // 宿主未实现回告时的兜底：不阻塞评测结果页渲染
      setTimeout(function () {
        if (settled) return
        settled = true
        cleanup()
        resolve({ success: true, pending: true })
      }, 2500)
    })
  },

  sendNonSampleSignal() {
    const payload = { type: 'NON_SAMPLE_SIGNAL', timestamp: Date.now() }
    if (window.messagePort) window.messagePort.postMessage(payload)
    else window.parent.postMessage(payload, '*')
    Logger.log('已发送 NON_SAMPLE_SIGNAL')
  },
}

// ===== 生成答题快照 HTML =====
function buildAnswerSnapshotHtml() {
  const rootClone = document.documentElement.cloneNode(true)

  // 1. 固化表单状态
  const origControls = document.querySelectorAll('input, textarea, select')
  const cloneControls = rootClone.querySelectorAll('input, textarea, select')
  const len = Math.min(origControls.length, cloneControls.length)
  for (let i = 0; i < len; i++) {
    const orig = origControls[i],
      clone = cloneControls[i]
    const tag = (orig.tagName || '').toLowerCase()
    if (tag === 'input') {
      const type = (orig.getAttribute('type') || '').toLowerCase()
      if (type === 'checkbox' || type === 'radio') {
        if (orig.checked) clone.setAttribute('checked', 'checked')
        else clone.removeAttribute('checked')
      } else {
        clone.setAttribute('value', orig.value ?? '')
      }
      clone.setAttribute('disabled', 'disabled')
    } else if (tag === 'textarea') {
      clone.textContent = orig.value ?? ''
      clone.setAttribute('disabled', 'disabled')
    } else if (tag === 'select') {
      const origOpts = orig.options || []
      const cloneOpts = clone.options || []
      const n = Math.min(origOpts.length, cloneOpts.length)
      for (let j = 0; j < n; j++) {
        if (origOpts[j].selected) cloneOpts[j].setAttribute('selected', 'selected')
        else cloneOpts[j].removeAttribute('selected')
      }
      clone.setAttribute('disabled', 'disabled')
    }
  }

  // 2. 展开所有分页中的题目（分页通过 style.display 控制，需显式展开）
  rootClone.querySelectorAll('[data-question]').forEach(el => {
    el.style.display = ''
  })
  rootClone.querySelectorAll('[data-page-break]').forEach(el => {
    el.style.display = ''
  })

  // 3. 隐藏导航和进度条（通过 data-snapshot-exclude 标记，不再硬编码 ID/class）
  rootClone.querySelectorAll('[data-snapshot-exclude]').forEach(el => {
    el.style.display = 'none'
  })

  // 4. 移除所有脚本
  rootClone.querySelectorAll('script').forEach(el => el.remove())

  // 5. 标记快照模式
  const body = rootClone.querySelector('body')
  if (body) body.classList.add('snapshot-mode')

  return rootClone.outerHTML
}

// ===== 题型枚举映射（数字 -> 字符串）=====
const TYPE_ENUM_MAP = {
  [QUESTION_TYPES.RADIO]: 'RADIO',
  [QUESTION_TYPES.CHECKBOX]: 'CHECKBOX',
  [QUESTION_TYPES.TEXTAREA]: 'TEXTAREA',
  [QUESTION_TYPES.SCALE]: 'SCALE',
  [QUESTION_TYPES.UPLOAD]: 'UPLOAD',
  [QUESTION_TYPES.MATRIX_SCALE]: 'MATRIX_SCALE',
  [QUESTION_TYPES.GENERIC]: 'GENERIC',
}

/** @param {*} n */
function _isValidSubmitScore(n) {
  return typeof n === 'number' && !Number.isNaN(n)
}

/** @param {Array|undefined} options */
function _optionsNeedDomFix(options) {
  if (!Array.isArray(options) || options.length === 0) return true
  return options.some(opt => {
    if (!opt || typeof opt !== 'object') return true
    const hasLabel = opt.label != null && String(opt.label).trim() !== ''
    // 后端按 label 匹配选项，label 是必需字段：只要被选中的选项缺 label，
    // 就从 DOM 兜底重读（getOptionLabelText 取 [data-option] 纯文本）。
    // 兼容旧/自由模式内联事件只写了 value 没写 label 的存量 HTML——
    // 旧卷运行时加载的是本 bridge，无需改动其 HTML 即可在提交时自动补回 label。
    return !hasLabel && opt.selected === true
  })
}

/** @param {HTMLElement} item */
function _readRadioOptionsFromDom(item) {
  const selected =
    item.querySelector('[data-option].selected') ||
    item.querySelector('[data-option].active.selected') ||
    item.querySelector('[data-option].active')
  if (!selected) return []
  return [
    {
      label: getCanonicalOptionLabel(selected),
      value: selected.getAttribute('data-option-value') || getOptionLabelText(selected),
      selected: true,
    },
  ]
}

/** @param {HTMLElement} item */
function _readCheckboxOptionsFromDom(item) {
  return Array.from(item.querySelectorAll('[data-option].selected, [data-option].active.selected')).map(o => ({
    label: getCanonicalOptionLabel(o),
    value: o.getAttribute('data-option-value') || getOptionLabelText(o),
    selected: true,
  }))
}

/**
 * 提交前归一化手写 buildAnswers 的畸形结构（自由模式 LLM 自定义 JS 常见）
 * @param {Array<{data: object}>} rows
 * @returns {Array<{data: object}>}
 */
function sanitizeSubmitRows(rows) {
  if (!Array.isArray(rows)) return []
  return rows.map(row => {
    if (!row || !row.data || typeof row.data !== 'object') return row
    const d = { ...row.data }
    const uuid = d.questionUuid
    let item = null
    if (uuid && typeof uuid === 'string') {
      try {
        item = document.querySelector(`[data-question][data-question-uuid="${CSS.escape(uuid)}"]`)
      } catch (e) {
        item = document.querySelector(`[data-question][data-question-uuid="${uuid}"]`)
      }
    }
    const qtype = d.questionType

    if (qtype === 'SCALE') {
      let score = d.score
      if (!_isValidSubmitScore(score)) {
        if (item) {
          const fromDom = AnswerReader.scale(item)
          score = fromDom != null ? fromDom : null
        } else {
          score = null
        }
        if (score == null) score = 0
      }
      d.score = score
      if (d.scaleId === undefined) d.scaleId = null
    } else if (qtype === 'MATRIX_SCALE') {
      let answers = Array.isArray(d.matrixScaleAnswers) ? d.matrixScaleAnswers : []
      answers = answers
        .filter(r => r && typeof r === 'object' && r.rowTitle && _isValidSubmitScore(Number.parseFloat(r.score)))
        .map(r => ({ rowTitle: String(r.rowTitle), score: Number.parseFloat(r.score) }))
      if (answers.length === 0 && item) {
        const fromDom = AnswerReader.matrixScale(item)
        if (Array.isArray(fromDom) && fromDom.length > 0) {
          answers = fromDom
        }
      }
      d.matrixScaleAnswers = answers
      if (isDynamicMatrixQuestion(item)) {
        const activeRowTitles = Array.isArray(d.activeRowTitles)
          ? d.activeRowTitles.map(title => String(title || '').trim()).filter(Boolean)
          : readActiveMatrixRowTitles(item)
        d.activeRowTitles = Array.from(new Set(activeRowTitles))
      } else {
        delete d.activeRowTitles
      }
    } else if (qtype === 'RADIO') {
      if (_optionsNeedDomFix(d.options) && item) {
        const fixed = _readRadioOptionsFromDom(item)
        if (fixed.length) d.options = fixed
      }
    } else if (qtype === 'CHECKBOX') {
      if (_optionsNeedDomFix(d.options) && item) {
        const fixed = _readCheckboxOptionsFromDom(item)
        if (fixed.length) d.options = fixed
      }
    } else if (qtype === 'TEXTAREA') {
      d.value = typeof d.value === 'string' ? d.value : d.value != null ? String(d.value) : ''
      if (d.textId === undefined) d.textId = null
    } else if (qtype === 'UPLOAD') {
      let files = _normalizeSubmitUploadFileEntries(Array.isArray(d.files) ? d.files : [])
      if (_uploadSubmitFilesHaveBlob(files)) {
        const resolved = _resolveUploadFilesForSubmit(uuid, item)
        d.files = resolved.length > 0 ? resolved : files.filter(file => !_isBlobUploadUrl(file.url))
      } else {
        d.files = files
      }
    }

    return { data: d }
  })
}

// ===== 构建提交数据 =====
function buildSubmitData() {
  const submitData = []
  SurveyAnswerState.answers.forEach(answer => {
    const item = document.querySelector(`[data-question][data-question-uuid="${answer.questionUuid}"]`)
    if (!item) return

    // 默认过滤逻辑隐藏题；仅允许 SurveyRuntime.setLogicAnswer 显式标记的派生答案提交。
    if (
      item.getAttribute('data-logic-visible') === 'false' &&
      item.getAttribute('data-logic-submit-answer') !== 'true'
    )
      return

    const typeNum = Number(answer.questionType)
    const typeEnum = TYPE_ENUM_MAP[typeNum] || 'GENERIC'
    const value = answer.value
    const data = {
      questionUuid: answer.questionUuid,
      questionType: typeEnum,
    }

    if (typeNum === QUESTION_TYPES.RADIO) {
      if (value && value.optionValue) {
        // "其它"选项：value 为用户输入文本，optionValue 保持原值
        const optValue = value.otherText != null ? value.otherText : value.optionValue
        data.options = [{ label: value.schemaLabel || value.value || value.optionValue, value: optValue, selected: true }]
      } else if (value && value.value) {
        // fallback：optionValue 缺失时，用 value 兜底，确保数据不丢失
        data.options = [{ label: value.value, selected: true }]
      }
    } else if (typeNum === QUESTION_TYPES.CHECKBOX) {
      if (value && Array.isArray(value.optionValues)) {
        data.options = value.optionValues.map((optVal, idx) => {
          const label = (Array.isArray(value.value) ? value.value[idx] : null) || optVal
          const schemaLabel = Array.isArray(value.schemaLabels) ? value.schemaLabels[idx] : null
          const otherText = Array.isArray(value.otherTexts) ? value.otherTexts[idx] : null
          // "其它"选项：value 为用户输入文本（空字符串也要保留，不能 fallback 到 optVal）
          const optValue = otherText != null ? otherText : optVal
          return {
            label: schemaLabel || label,
            value: optValue,
            selected: true,
          }
        })
      }
    } else if (typeNum === QUESTION_TYPES.TEXTAREA) {
      data.value = typeof value === 'string' ? value : ''
      data.textId = null
    } else if (typeNum === QUESTION_TYPES.SCALE) {
      data.scaleId = null
      data.score = Number.parseFloat(value) || null
    } else if (typeNum === QUESTION_TYPES.MATRIX_SCALE) {
      if (Array.isArray(value) && value.length > 0) {
        data.matrixScaleAnswers = value.map(item => ({
          rowTitle: item.rowTitle || '',
          score: Number.parseFloat(item.score) || null,
        }))
      }
      if (isDynamicMatrixQuestion(item)) {
        data.activeRowTitles = readActiveMatrixRowTitles(item)
      }
    } else if (typeNum === QUESTION_TYPES.UPLOAD) {
      if (Array.isArray(value) && value.length > 0) {
        data.files = value.map(file => {
          if (typeof file === 'string') {
            return { url: file, fileName: file.split('/').pop() || '' }
          }
          return {
            url: file.url || '',
            fileName: file.name || file.fileName || (file.url || '').split('/').pop() || '',
          }
        })
      }
    } else if (typeNum === QUESTION_TYPES.GENERIC) {
      data.genericId = null
      data.answerData = typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value || '{}')
    }

    submitData.push({ data })
  })
  return submitData
}

/** 从标准评测结果 DOM 兜底读取展示字符串 */
function scrapeEvalDisplayFromDom() {
  var root = document.getElementById('eval-result')
  if (!root) return null
  try {
    if (root.dataset && root.dataset.evalJson) {
      return String(root.dataset.evalJson).trim() || null
    }
  } catch (e) {}
  function txt(id) {
    var el = document.getElementById(id)
    return el ? (el.textContent || '').trim() : ''
  }
  var scoreEl = document.getElementById('eval-result-score')
  var scoreText = scoreEl ? (scoreEl.textContent || '').trim() : ''
  if (scoreText) {
    var m = scoreText.match(/-?\d+(?:\.\d+)?/)
    if (m) return m[0]
  }
  var title = txt('eval-result-title')
  return title || null
}

/** 解析评测结果展示字符串：opts.evalResult > __WJ_EVAL_RESULT__ > DOM 兜底 */
function resolveEvalDisplay(opts) {
  opts = opts || {}
  var v = opts.evalResult != null ? opts.evalResult : window.__WJ_EVAL_RESULT__
  if (v == null) v = scrapeEvalDisplayFromDom()
  if (v == null) return null
  var s = String(v).trim()
  return s || null
}

// ===== 暴露给 survey-ui.js 的全局 API =====
window.SurveyDataBridge = {
  /**
   * 上传文件
   * @param {File} file
   * @param {string} questionId
   * @returns {Promise<Object>}
   */
  uploadFile(file, questionId) {
    return API.uploadFiles(file, questionId)
  },

  /**
   * 提交前归一化答案行（调试用；submit 内部已自动调用）
   * @param {Array<{data: object}>} rows
   * @returns {Array<{data: object}>}
   */
  sanitizeSubmitRows(rows) {
    return sanitizeSubmitRows(rows)
  },

  /**
   * 提交答案
   * @param {Array} [answers] - 答案数组（可选，不传则自动收集）
   * @param {string} [originSurveyAnswer] - 快照 HTML（可选，不传则自动生成）
   */
  async submit(answers, originSurveyAnswer) {
    if (SurveyAnswerState.isSubmitting) return
    SurveyAnswerState.isSubmitting = true
    try {
      // 样本库筛查：提交前整卷校验
      if (!_checkSampleRequirements(document)) {
        API.sendNonSampleSignal()
        throw new Error(sbT('SurveyRuntime.Sample Screen Failed', '样本筛查未通过：存在未满足样本要求的题目'))
      }

      // 触发提交前事件（自定义题可在此补数）
      window.dispatchEvent(new CustomEvent('survey:before-submit'))
      await new Promise(r => setTimeout(r, 50))

      // 优先使用传入的答案（如 survey-ui.js 构建的数据），否则自动收集
      let submitData = Array.isArray(answers) && answers.length > 0 ? answers : buildSubmitData()
      submitData = sanitizeSubmitRows(submitData)
      let html = originSurveyAnswer
      if (!html) {
        window.dispatchEvent(new CustomEvent('survey:before-snapshot'))
        await new Promise(r => setTimeout(r, 50))
        html = buildAnswerSnapshotHtml()
      }
      await API.updateAnswers(submitData, html, resolveEvalDisplay({}))
    } catch (err) {
      Logger.error('提交失败:', err)
      throw err
    } finally {
      SurveyAnswerState.isSubmitting = false
    }
  },

  /**
   * 无刷新提交（评测类问卷专用）。
   *
   * 把当前答案持久化到后端，但**不会**让宿主隐藏 iframe 或跳转通用完成页——
   * 问卷脚本可以继续停留在卷内展示「评测结果页」。这是为了解决「展示评测结果时
   * 被迫绑定到提交事件、提交即被宿主跳走」的问题：评测请用本方法落库，再自行渲染结果，
   * 不要用 submit()/SurveyRuntime.submitSurvey() 去驱动结果展示。
   *
   * 与 submit() 的差异：
   *  - 发送 'SUBMIT_NO_REDIRECT'（而非 'SUBMIT'），宿主只落库、保持卷内停留；
   *  - 返回 Promise 而非 throw：永远 resolve，便于"落库后接着渲染结果"的链式写法；
   *  - 同一份答案可重复调用（幂等性由宿主/后端兜底），但建议只在"查看结果"时调一次。
   *
   * @param {Object} [opts]
   * @param {Array}  [opts.answers] 答案数组（不传则自动收集当前全部答案）
   * @param {string} [opts.originSurveyAnswer] 答题快照 HTML（不传则自动生成）
   * @param {string} [opts.evalResult] 评测结果展示字符串（不传则读 __WJ_EVAL_RESULT__ / 标准 DOM）
   * @param {boolean}[opts.snapshot=true] 是否生成答题快照（评测一般可设 false 省开销）
   * @returns {Promise<{success:boolean, pending?:boolean, err?:string}>}
   */
  async submitAndStay(opts) {
    opts = opts || {}
    if (SurveyAnswerState.isSubmitting) return { success: false, err: 'submitting' }
    SurveyAnswerState.isSubmitting = true
    try {
      // 自定义题提交前补数（与 submit 一致）
      window.dispatchEvent(new CustomEvent('survey:before-submit'))
      await new Promise(r => setTimeout(r, 50))

      let submitData = Array.isArray(opts.answers) && opts.answers.length > 0 ? opts.answers : buildSubmitData()
      submitData = sanitizeSubmitRows(submitData)

      let html = opts.originSurveyAnswer
      if (html == null && opts.snapshot !== false) {
        window.dispatchEvent(new CustomEvent('survey:before-snapshot'))
        await new Promise(r => setTimeout(r, 50))
        html = buildAnswerSnapshotHtml()
      }

      const ack = await API.persistAnswers(submitData, html || '', resolveEvalDisplay(opts))
      return ack || { success: true }
    } catch (err) {
      Logger.error('无刷新提交失败:', err)
      return { success: false, err: String((err && err.message) || err) }
    } finally {
      SurveyAnswerState.isSubmitting = false
    }
  },

  /**
   * 更新答案（实时保存，非提交）
   * @param {Array} answers
   */
  updateAnswers(answers) {
    const payload = {
      type: 'SURVEY_ANSWER_DATA_UPDATE',
      data: { answers, timestamp: Date.now() },
    }
    if (window.messagePort) window.messagePort.postMessage(payload)
    else window.parent.postMessage(payload, '*')
  },

  /**
   * 获取当前所有答案（供 survey-ui.js 读取）
   * @returns {Array}
   */
  getAnswers() {
    return SurveyAnswerState.answers
  },

  /**
   * 获取本问卷的「可分享公开链接」（宿主通过 INIT_SHARE_URL 透传）。
   * 评测海报二维码、分享文案带链接用；宿主未透传时返回空串，调用方应优雅降级。
   * @returns {string}
   */
  getShareUrl() {
    return _surveyShareUrl || ''
  },

  /**
   * 已废弃：按题号获取答案。请改用 getAnswer(uuid) 配合 resolveUuidByIndex(index)。
   * @deprecated
   */
  getAnswerByIndex(indexNum) {
    console.warn(
      '[SurveyDataBridge] getAnswerByIndex(' +
        indexNum +
        ') 已废弃。请使用 resolveUuidByIndex(' +
        indexNum +
        ') 获取 UUID，再调用 getAnswer(uuid)。',
    )
    return null
  },

  /**
   * 获取指定题答案（统一返回格式，同时提供兼容字段）
   * @param {string} questionUuid
   * @returns {Object|null} { questionUuid, questionType, value, optionValue?, optionValues?, scaleValue?, matrixScores?, matrixScoreMap?, timestamp }
   */
  getAnswer(questionUuid) {
    // 支持 UUID 或 data-code 两种输入，LLM 经常混淆二者
    let resolvedUuid = questionUuid
    const hasUuid =
      SurveyAnswerState.answers.some(a => a.questionUuid === questionUuid) ||
      document.querySelector(`[data-question-uuid="${questionUuid}"]`)
    if (!hasUuid) {
      const byCode = document.querySelector(`[data-code="${questionUuid}"]`)
      if (byCode) resolvedUuid = byCode.getAttribute('data-question-uuid')
    }

    const cached = SurveyAnswerState.answers.find(a => a.questionUuid === resolvedUuid)
    if (!cached) {
      // 缓存未命中时 fallback 读 DOM
      const domAnswer = window.SurveyApp ? window.SurveyApp.getAnswer(resolvedUuid) : null
      if (!domAnswer) return null
      const result = {
        questionUuid,
        questionType: null,
        value: domAnswer.value,
        timestamp: Date.now(),
      }
      if (domAnswer.optionValue !== undefined) result.optionValue = domAnswer.optionValue
      if (domAnswer.optionValues !== undefined) result.optionValues = domAnswer.optionValues
      if (domAnswer.scaleValue !== undefined) result.scaleValue = domAnswer.scaleValue
      if (domAnswer.matrixScores !== undefined) result.matrixScores = domAnswer.matrixScores
      if (domAnswer.matrixScoreMap !== undefined) result.matrixScoreMap = domAnswer.matrixScoreMap
      return result
    }

    // 统一包装缓存答案，同时提供兼容字段
    const result = {
      questionUuid: cached.questionUuid,
      questionType: cached.questionType,
      value: cached.value,
      timestamp: cached.timestamp,
    }

    const type = Number(cached.questionType)
    if (type === QUESTION_TYPES.RADIO && cached.value && typeof cached.value === 'object') {
      result.optionValue = cached.value.optionValue
      result.value = cached.value.value
    }
    if (type === QUESTION_TYPES.CHECKBOX && cached.value && typeof cached.value === 'object') {
      result.optionValues = cached.value.optionValues
      result.value = cached.value.value
    }
    if (type === QUESTION_TYPES.SCALE && typeof cached.value === 'number') {
      result.scaleValue = cached.value
    }
    if (type === QUESTION_TYPES.MATRIX_SCALE && Array.isArray(cached.value)) {
      result.matrixScores = cached.value
      result.matrixScoreMap = Object.fromEntries(cached.value.map(r => [r.rowTitle, r.score]))
    }

    return result
  },

  /**
   * 检查指定范围内的样本要求是否满足
   * @param {HTMLElement} [rootEl] - 检查范围，默认整篇文档
   * @returns {boolean}
   */
  checkSampleRequirements(rootEl) {
    return _checkSampleRequirements(rootEl)
  },

  /**
   * 发送非样本信号（供外部或宿主页调用）
   */
  sendNonSampleSignal() {
    API.sendNonSampleSignal()
  },
}

// ===== SurveyApp API（从 survey-ui.js 迁移到 runtime，避免 LLM 重写 survey-ui.js 时丢失基础设施） =====
window.SurveyApp = {
  _channelReady: false,

  /**
   * 读取指定题目的当前答案（直接读 DOM，与 SurveyDataBridge.getAnswer 读缓存互补）
   * @param {string} questionUuid
   * @returns {Object|null} { value, type }
   */
  getAnswer(questionUuid) {
    const q = document.querySelector(`[data-question-uuid="${questionUuid}"]`)
    if (!q) return null
    const type = Number(q.getAttribute('data-question-type'))

    // radio
    const radioChecked = q.querySelector('input[type="radio"]:checked')
    if (radioChecked) {
      const opt = radioChecked.closest('[data-option]')
      const optionValue = opt ? opt.getAttribute('data-option-value') : null
      const value = opt ? getOptionLabelText(opt) : radioChecked.value
      const isOther = opt ? opt.hasAttribute('data-option-other') : false
      const otherInput = isOther ? opt.querySelector('[data-other-input]') : null
      const otherText = otherInput ? otherInput.value.trim() : null
      return {
        optionValue,
        value,
        otherText,
        type: 'radio',
      }
    }

    // checkbox
    const cbChecked = q.querySelectorAll('input[type="checkbox"]:checked')
    if (cbChecked.length) {
      const optionValues = []
      const values = []
      const otherTexts = []
      cbChecked.forEach(c => {
        const opt = c.closest('[data-option]')
        const isOther = opt ? opt.hasAttribute('data-option-other') : false
        const otherInput = isOther ? opt.querySelector('[data-other-input]') : null
        optionValues.push(opt ? opt.getAttribute('data-option-value') : c.value)
        values.push(opt ? getOptionLabelText(opt) : c.value)
        otherTexts.push(otherInput ? otherInput.value.trim() : null)
      })
      return { optionValues, value: values, otherTexts, type: 'checkbox' }
    }

    // textarea / text input
    const textInput = q.querySelector('[data-input-type="text"]')
    if (textInput) {
      const val = textInput.value !== undefined ? textInput.value : textInput.textContent || ''
      return { value: val, type: 'text' }
    }

    // scale
    const scaleSel = q.querySelector(SEL_SCALE_ACTIVE)
    if (scaleSel) {
      const scaleValue = parseScaleValue(scaleSel)
      return { scaleValue, value: scaleValue, type: 'scale' }
    }

    // matrix-scale
    const matrixRows = q.querySelectorAll('[data-survey-role="matrix-group"] [data-survey-role="matrix-row"]')
    if (matrixRows.length) {
      const matrixScores = []
      const m = {}
      matrixRows.forEach(row => {
        const label = row.getAttribute('data-matrix-row-label') || row.textContent.trim()
        const sel = row.querySelector(SEL_MATRIX_ACTIVE)
        if (sel) {
          const score = parseScaleValue(sel)
          matrixScores.push({ rowTitle: label, score })
          m[label] = score
        }
      })
      return { matrixScores, matrixScoreMap: m, value: matrixScores, type: 'matrix-scale' }
    }

    // upload
    const fileInput = q.querySelector('input[type="file"]')
    if (fileInput) {
      const cached = SurveyAnswerState.answers.find(a => a.questionUuid === questionUuid)
      const cachedFiles = getUploadFilesFromValue(cached ? cached.value : [])
      if (cachedFiles.length > 0) {
        return {
          value: cachedFiles.map(file => file.url).join(','),
          files: cachedFiles,
          type: 'file',
        }
      }
      let datasetFiles = []
      if (fileInput.dataset.uploadFiles) {
        try {
          const parsed = JSON.parse(fileInput.dataset.uploadFiles)
          datasetFiles = getUploadFilesFromValue(Array.isArray(parsed) ? parsed : [])
        } catch (e) {}
      }
      return {
        value: fileInput.dataset.uploadUrl || '',
        files: datasetFiles,
        type: 'file',
        selectedFileNames: Array.from(fileInput.files || []).map(file => file.name),
      }
    }

    // generic (type=39)
    if (type === QUESTION_TYPES.GENERIC) {
      const customVal = q.dataset.customValue
      if (customVal) {
        try {
          return { value: JSON.parse(customVal), type: 'generic' }
        } catch (e) {
          return { value: customVal, type: 'generic' }
        }
      }
      return { value: null, type: 'generic' }
    }

    return null
  },

  /**
   * 设置题目可见性
   * @param {string} questionUuid
   * @param {boolean} visible
   */
  setVisibility(questionUuid, visible) {
    const q = document.querySelector(`[data-question-uuid="${questionUuid}"]`)
    if (!q) return
    q.style.display = visible ? '' : 'none'
    if (window._surveyPagination && typeof window._surveyPagination.refresh === 'function') {
      window._surveyPagination.refresh()
    }
  },

  /**
   * 注册答案变化回调
   * @param {Function} callback
   * @returns {Function} unsubscribe
   */
  onAnswerChange(callback) {
    function handler(e) {
      callback(e.detail)
    }
    document.addEventListener('surveyAnswerChanged', handler)
    return function () {
      document.removeEventListener('surveyAnswerChanged', handler)
    }
  },

  /**
   * 设置自定义值（供 saveAnswerLocal 回调 UI 更新）
   * @param {string} questionUuid
   * @param {*} value
   */
  setCustomValue(questionUuid, value) {
    const q = document.querySelector(`[data-question-uuid="${questionUuid}"]`)
    if (!q) {
      Logger.warn('SurveyApp.setCustomValue: question not found', questionUuid)
      return
    }
    q.dataset.customValue = typeof value === 'object' ? JSON.stringify(value) : String(value)
  },
}

/* Expose legacy-named globals for LLM compatibility */
window.getLogicAnswer = window.SurveyApp.getAnswer
window.setLogicQuestionVisibility = window.SurveyApp.setVisibility
window.onLogicAnswerChange = window.SurveyApp.onAnswerChange

// ===== 自定义题型处理器 =====
const GenericQuestionHandler = {
  init() {
    document.querySelectorAll('[data-survey-role="generic-container"]').forEach(wrapper => {
      const questionId = wrapper.closest('[data-question][data-question-uuid]')?.getAttribute('data-question-uuid')
      if (questionId) wrapper.setAttribute('data-question-uuid', questionId)
    })
  },

  saveAnswer(questionId, answers) {
    if (!answers || typeof answers !== 'object') {
      Logger.error('自定义题型答案格式错误：必须是对象类型', questionId, answers)
      return
    }
    // 允许空对象保存（非必填题允许空答案）
    const wrapper = document.querySelector(`[data-survey-role="generic-container"][data-question-uuid="${questionId}"]`)
    const scriptEl = wrapper?.querySelector('script[data-answer-keys]')
    const answerKeysStr = scriptEl?.getAttribute('data-answer-keys')
    if (!answerKeysStr || typeof answerKeysStr !== 'string' || !answerKeysStr.trim()) {
      Logger.error(
        '自定义题型 data-answer-keys 必填：答案须为 key-value 对象，且 key 必须与 data-answer-keys 中列出的键名一致',
        questionId,
      )
      return
    }
    const allowedKeys = answerKeysStr
      .split(',')
      .map(k => k.trim())
      .filter(k => k)
    const providedKeys = Object.keys(answers)
    // data-answer-keys 是允许的键名白名单，不要求所有键都必须提交（支持动态/部分表单）
    const invalidKeys = providedKeys.filter(k => !allowedKeys.includes(k))
    if (invalidKeys.length > 0) {
      Logger.error('自定义题型答案包含非法键:', questionId, '非法:', invalidKeys, '允许:', allowedKeys)
      return
    }
    saveAnswerLocal(questionId, QUESTION_TYPES.GENERIC, answers)
  },
}

// ===== 自定义题型提交入口（旧架构兼容）=====
window.submitGenericAnswer = function (questionId, answers) {
  if (!answers || typeof answers !== 'object') {
    Logger.error('自定义题型答案格式错误：必须是对象类型', questionId, answers)
    return
  }
  if (Object.keys(answers).length === 0) return

  // 如果 GenericQuestionHandler 还未初始化，延迟执行
  if (typeof GenericQuestionHandler === 'undefined') {
    Logger.warn('GenericQuestionHandler 未初始化，延迟提交答案', questionId)
    const maxRetries = 50
    let retryCount = 0
    const retrySubmit = () => {
      if (typeof GenericQuestionHandler !== 'undefined') {
        GenericQuestionHandler.saveAnswer(questionId, answers)
      } else if (retryCount < maxRetries) {
        retryCount++
        setTimeout(retrySubmit, 100)
      } else {
        Logger.error('无法提交自定义题型答案：GenericQuestionHandler 初始化超时', questionId, answers)
      }
    }
    setTimeout(retrySubmit, 100)
  } else {
    GenericQuestionHandler.saveAnswer(questionId, answers)
  }
}

/**
 * 文本归一化：去除首尾空白，将换行符替换为空格，防止布局异常。
 */
function normalizeCollectedText(text) {
  if (typeof text !== 'string') return ''
  return text.replace(/\r\n|\r|\n/g, ' ').trim()
}

/**
 * 读取选项元素的纯文本文案（替代已废弃的 data-option-label 属性）。
 * 先克隆节点并移除表单控件与装饰性节点（单选点 / 复选框 / 勾选图标 / 其它输入框），
 * 避免把 ✓、输入框内容等混入文案；兼容 .opt 与 .option-pill 两种 DOM 结构。
 * @param {Element|null} opt
 * @returns {string}
 */
function getOptionLabelText(opt) {
  if (!opt || typeof opt.cloneNode !== 'function') return ''
  const clone = opt.cloneNode(true)
  // 剥离表单控件与装饰性节点（单选圆点 / 复选框 / 勾选图标）。
  // 标准模板用空 .cb + CSS 伪元素；editor-inject 等旧 DOM 可能在 .ci 内嵌 ✓ 文本，须一并移除。
  clone.querySelectorAll('input, textarea, select, button').forEach(el => el.remove())
  clone.querySelectorAll('.cb, .rd, .ci').forEach(el => el.remove())
  return normalizeCollectedText(clone.textContent)
}

/**
 * 收集问卷级元数据（标题、描述），用于 refreshOriginSurvey 的 survey 字段。
 * 取数规则：只依赖 data-* 属性，与题目收集策略一致。
 */
function collectSurveyMeta() {
  const titleEl = document.querySelector('[data-title="survey"]')
  const descEl = document.querySelector('[data-desc="description"]')

  return {
    title: normalizeCollectedText(titleEl?.textContent),
    description: normalizeCollectedText(descEl?.textContent),
  }
}

/**
 * 收集当前 DOM 中的题目结构化数据，用于向后端 refreshOriginSurvey 提供完整题型数组。
 * 数据层职责归属 survey-bridge.js，editor-inject.js 仅调用 window.collectSurveyData()。
 * 取数规则：题目只依赖 data-* 属性；问卷标题/描述见 collectSurveyMeta()。
 */
function collectSurveyData() {
  const result = {
    survey: collectSurveyMeta(),
    radioQuestions: [],
    checkboxQuestions: [],
    textQuestions: [],
    uploadQuestions: [],
    scaleQuestions: [],
    matrixScaleQuestions: [],
    genericQuestions: [],
  }

  const isRequiredValue = value => value === 'true' || value === '1' || value === 'required'
  const uniqueElements = nodeList => Array.from(new Set(Array.from(nodeList)))
  const getMatrixHeaderColumns = q =>
    uniqueElements(
      q.querySelectorAll(
        '[data-survey-role="matrix-header"] [data-matrix-column], [data-survey-role="matrix-header"] .matrix-column, [data-survey-role="matrix-header"] .mc',
      ),
    ).filter(el => !el.classList.contains('matrix-corner'))
  const getMatrixFallbackColumns = q => {
    const firstRow = q.querySelector('[data-survey-role="matrix-group"] [data-survey-role="matrix-row"]')
    return firstRow ? uniqueElements(firstRow.querySelectorAll(SEL_MATRIX_OPT)) : []
  }

  document.querySelectorAll('[data-question]').forEach((q, index) => {
    const uuid = q.getAttribute('data-question-uuid') || ''
    const type = Number(q.getAttribute('data-question-type') || '0')
    const title = normalizeCollectedText(q.querySelector('[data-title]')?.textContent)
    const required = isRequiredValue(q.getAttribute('data-required')) ? 1 : 0

    const baseDto = {
      uuid,
      title: title || '',
      description: '',
      required,
      sort: index + 1,
    }

    switch (type) {
      case QUESTION_TYPES.RADIO: {
        const catalog = readQuestionItemCatalog(q, 'options')
        const options = catalog.length
          ? catalog.map((item, optIdx) => ({
              label: item.schemaLabel,
              value: item.schemaLabel,
              sort: optIdx + 1,
            }))
          : uniqueElements(q.querySelectorAll('[data-option]')).map((opt, optIdx) => {
              const label = getCanonicalOptionLabel(opt) || ''
              return { label, value: label, sort: optIdx + 1 }
            })
        result.radioQuestions.push({ ...baseDto, type: 'RADIO', options })
        break
      }
      case QUESTION_TYPES.CHECKBOX: {
        const catalog = readQuestionItemCatalog(q, 'options')
        const options = catalog.length
          ? catalog.map((item, optIdx) => ({
              label: item.schemaLabel,
              value: item.schemaLabel,
              sort: optIdx + 1,
            }))
          : uniqueElements(q.querySelectorAll('[data-option]')).map((opt, optIdx) => {
              const label = getCanonicalOptionLabel(opt) || ''
              return { label, value: label, sort: optIdx + 1 }
            })
        const minChoices = Number(q.getAttribute('data-min-choices') || 0)
        const maxChoices = Number(q.getAttribute('data-max-choices') || options.length || 100)
        result.checkboxQuestions.push({
          ...baseDto,
          type: 'CHECKBOX',
          options,
          maxChoices,
          minChoices,
        })
        break
      }
      case QUESTION_TYPES.TEXTAREA:
      case 3: {
        const textInput = q.querySelector('[data-input-type="text"]')
        result.textQuestions.push({
          ...baseDto,
          type: 'INPUT',
          placeholder: normalizeCollectedText(textInput?.getAttribute('placeholder')) || '',
          minLength: Number(q.getAttribute('data-min-length') || textInput?.dataset.minLength || 0),
          maxLength: Number(q.getAttribute('data-max-length') || textInput?.dataset.maxLength || 255),
          defaultValue: null,
        })
        break
      }
      case QUESTION_TYPES.SCALE: {
        const options = []
        uniqueElements(q.querySelectorAll(SEL_SCALE_OPT)).forEach((sc, scIdx) => {
          const scaleValue = normalizeCollectedText(sc.getAttribute('data-scale-value')) || String(scIdx + 1)
          // title 取刻度的可见纯文本（与 data-option-label 迁移同原则，不再读冗余的 data-scale-label）；
          // 显示文本即真相，仅文本为空时兜底分值字符串。score 单独取 data-scale-value。
          const scTitle = normalizeCollectedText(sc.textContent) || scaleValue
          options.push({
            title: scTitle,
            score: Number.parseFloat(scaleValue) || scIdx + 1,
            sort: scIdx + 1,
          })
        })
        result.scaleQuestions.push({ ...baseDto, type: 'SCALE', options })
        break
      }
      case 14:
      case QUESTION_TYPES.UPLOAD: {
        // 缺省/非法值与运行时 getUploadConstraints 对齐：缺省 99（不限制），避免“UI 允许 99 但快照上报 1”的错位
        const rawMaxFileCount = Number(q.getAttribute('data-max-file-count'))
        const maxFileCount = Number.isFinite(rawMaxFileCount) && rawMaxFileCount > 0 ? rawMaxFileCount : 99
        const maxFileSize = Number(q.getAttribute('data-max-file-size') || 10240)
        const fileTypesStr = q.getAttribute('data-file-types') || ''
        const fileTypes = fileTypesStr
          ? fileTypesStr
              .split(',')
              .map(t => t.trim())
              .filter(Boolean)
          : [
              'jpg',
              'jpeg',
              'gif',
              'png',
              'bmp',
              'zip',
              'rar',
              'mp3',
              'mp4',
              'mov',
              'doc',
              'docx',
              'xls',
              'xlsx',
              'csv',
              'ppt',
              'pptx',
              'pdf',
            ]
        result.uploadQuestions.push({
          ...baseDto,
          type: 'UPLOAD',
          maxFileCount,
          maxFileSize,
          fileTypes,
        })
        break
      }
      case QUESTION_TYPES.MATRIX_SCALE: {
        let rows = []
        const columns = []
        const catalog = readQuestionItemCatalog(q, 'matrixRows')
        if (catalog.length) {
          rows = catalog.map((item, rowIdx) => ({
            rowTitle: item.schemaLabel,
            sort: rowIdx + 1,
          }))
        } else {
          q.querySelectorAll('[data-survey-role="matrix-group"] [data-survey-role="matrix-row"]').forEach(
            (row, rowIdx) => {
              const rowLabel =
                normalizeCollectedText(row.getAttribute('data-matrix-row-label')) ||
                normalizeCollectedText(row.getAttribute('data-matrix-row')) ||
                ''
              rows.push({ rowTitle: rowLabel, sort: rowIdx + 1 })
            },
          )
        }
        const matrixColumns = getMatrixHeaderColumns(q)
        const columnEls = matrixColumns.length ? matrixColumns : getMatrixFallbackColumns(q)
        if (columnEls.length) {
          columnEls.forEach((col, colIdx) => {
            const scaleValue = normalizeCollectedText(col.getAttribute('data-scale-value')) || String(colIdx + 1)
            // 列 title 优先取统一列头；旧 DOM 回退第一行刻度格。score 单独取 data-scale-value。
            const colTitle = normalizeCollectedText(col.textContent) || scaleValue
            columns.push({
              columnTitle: colTitle,
              score: Number.parseFloat(scaleValue) || colIdx + 1,
              sort: colIdx + 1,
            })
          })
        }
        const matrixQuestion = {
          ...baseDto,
          type: 'MATRIX_SCALE',
          rows,
          columns,
        }
        if (isDynamicMatrixQuestion(q)) matrixQuestion.dynamicRows = true
        result.matrixScaleQuestions.push(matrixQuestion)
        break
      }
      case QUESTION_TYPES.GENERIC: {
        result.genericQuestions.push({ ...baseDto, type: 'GENERIC' })
        break
      }
    }
  })

  return result
}

// ===== 初始化 =====
function init() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      autoBindQuestions()
      GenericQuestionHandler.init()
      Logger.log('survey-core auto-bind initialized')
    })
  } else {
    autoBindQuestions()
    GenericQuestionHandler.init()
    Logger.log('survey-core auto-bind initialized')
  }
}
init()

// 暴露 collectSurveyData 供 editor-inject.js 调用
window.collectSurveyData = collectSurveyData

// 暴露 saveAnswerLocal 供 survey-ui.js（上传题删除按钮等 UI 交互使用）
window.saveAnswerLocal = saveAnswerLocal

// 暴露上传题 UI / 删除接口，方便外部调用
window.removeUploadFile = removeUploadFile
window.renderUploadQuestionUI = renderUploadQuestionUI

console.log('[survey-core] data bridge loaded, version=20260616-2')

// ===== 组件加载器（原 survey-runtime.js）=====
;(function () {
  'use strict'

  window.SurveyComponents = window.SurveyComponents || {}

  // 检测平台并设置 body class
  function initPlatform() {
    try {
      var urlParams = new URLSearchParams(window.location.search)
      var platform = urlParams.get('platform')
      if (platform && (platform === 'pc' || platform === 'h5')) {
        document.body.classList.add('platform-' + platform)
      }
    } catch (e) {
      console.error('Platform detection failed:', e)
    }
  }

  // 立即执行平台检测
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPlatform)
  } else {
    initPlatform()
  }

  // 组件加载状态缓存
  var loadStatus = {}
  var callbacks = {}

  // CDN 基础路径（生产环境）
  var CDN_BASE = window.SURVEY_CHARTS_BASE || 'https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/survey-components'

  // 组件路径映射（与 CDN 实际目录结构保持一致）
  var componentPaths = {
    cascade: '/cascade.js',
    region: '/region/region.js',
    datetime: '/datetime.js',
    weight: '/weight.js',
    signature: '/signature.js',
  }

  /**
   * 加载组件
   * @param {string} name - 组件名: cascade|region|datetime|weight|signature
   * @param {Function} callback - 加载完成后的回调
   */
  window.SurveyComponents.load = function (name, callback) {
    // 检查组件是否已加载
    if (window.SurveyComponents[name]) {
      callback()
      return
    }

    // 检查是否正在加载中
    if (loadStatus[name] === 'loading') {
      callbacks[name] = callbacks[name] || []
      callbacks[name].push(callback)
      return
    }

    // 开始加载
    loadStatus[name] = 'loading'
    callbacks[name] = [callback]

    var script = document.createElement('script')
    // 优先使用自定义路径（本地测试），否则使用默认路径
    var path =
      (window.SURVEY_CHARTS_PATHS && window.SURVEY_CHARTS_PATHS[name]) || componentPaths[name] || '/' + name + '.js'
    script.src = CDN_BASE + path
    script.async = true

    script.onload = function () {
      loadStatus[name] = 'loaded'
      // 执行所有等待的回调
      callbacks[name].forEach(function (cb) {
        try {
          cb()
        } catch (e) {
          console.error('组件 ' + name + ' 回调执行错误:', e)
        }
      })
      delete callbacks[name]
    }

    script.onerror = function () {
      loadStatus[name] = 'error'
      console.error('组件 ' + name + ' 加载失败:', script.src)
      // 可选：重试逻辑或执行错误回调
    }

    document.head.appendChild(script)
  }

  /**
   * 批量加载多个组件
   * @param {Array} names - 组件名数组
   * @param {Function} callback - 全部加载完成后的回调
   */
  window.SurveyComponents.loadMultiple = function (names, callback) {
    var loaded = 0
    var total = names.length

    if (total === 0) {
      callback()
      return
    }

    names.forEach(function (name) {
      window.SurveyComponents.load(name, function () {
        loaded++
        if (loaded === total) {
          callback()
        }
      })
    })
  }
})()

// ===== 滚动状态转发：将 iframe 内的滚动指标通过 postMessage 通知宿主 =====
;(function setupScrollForwarding() {
  // console.log('[survey-core][scroll-forward] installing')
  var pending = false
  var lastTarget = null

  // 检测提交/分页导航区是否被右下角 footer 遮挡
  // 遍历导航区内部可见按钮，取最靠右的元素作为代表
  function getSubmitMetrics() {
    try {
      var nav = document.querySelector('[data-survey-role="navigation"]')
      if (!nav) return null
      var viewportH = window.innerHeight || document.documentElement.clientHeight
      var viewportW = window.innerWidth || document.documentElement.clientWidth
      var children = nav.querySelectorAll('button, a, [type="submit"], [role="button"]')
      if (!children.length) return null
      var rightmost = null
      var maxRight = -Infinity
      for (var i = 0; i < children.length; i++) {
        var child = children[i]
        var r = child.getBoundingClientRect()
        if (r.width === 0 || r.height === 0) continue
        if (r.right > maxRight) {
          maxRight = r.right
          rightmost = child
        }
      }
      if (!rightmost) return null
      var rect = rightmost.getBoundingClientRect()
      // 最右元素在视口之外时不做精确检测
      if (rect.top > viewportH || rect.bottom < 0) return null
      return {
        dist: Math.round(viewportH - rect.bottom), // 垂直：最右元素底部距视口底部
        rightDist: Math.round(viewportW - rect.right), // 水平：最右元素右侧距视口右侧
        width: Math.round(rect.width),
      }
    } catch (e) {
      return null
    }
  }

  function postFor(target) {
    var scrollTop, scrollHeight, clientHeight
    if (target === window || target === document) {
      var el = document.scrollingElement || document.documentElement
      scrollTop = el.scrollTop
      scrollHeight = el.scrollHeight
      clientHeight = el.clientHeight
    } else if (target instanceof Element) {
      scrollTop = target.scrollTop
      scrollHeight = target.scrollHeight
      clientHeight = target.clientHeight
    } else {
      return
    }
    try {
      window.parent.postMessage(
        {
          type: 'SURVEY_SCROLL',
          scrollTop: scrollTop,
          scrollHeight: scrollHeight,
          clientHeight: clientHeight,
          submitMetrics: getSubmitMetrics(),
          bodyFree: !!(document.body && document.body.classList.contains('free')),
        },
        '*',
      )
    } catch (e) {
      console.warn('[survey-core][scroll-forward] postMessage failed', e)
    }
  }

  function schedule(target) {
    lastTarget = target
    if (pending) return
    pending = true
    requestAnimationFrame(function () {
      pending = false
      postFor(lastTarget)
    })
  }

  // 文档级滚动（body / html）
  window.addEventListener(
    'scroll',
    function () {
      schedule(window)
    },
    { passive: true },
  )
  // 内部容器滚动（overflow:auto/scroll）走 capture 阶段
  document.addEventListener(
    'scroll',
    function (e) {
      schedule(e.target)
    },
    { passive: true, capture: true },
  )

  // 多个时机触发初始上报，确保宿主页一定能在 mount 后拿到当前尺寸
  function fireInitial(reason) {
    var el = document.scrollingElement || document.documentElement
    if (!el) return
    postFor(window)
  }
  setTimeout(function () {
    fireInitial('timeout-0')
  }, 0)
  if (document.readyState === 'complete') {
    setTimeout(function () {
      fireInitial('readystate-complete')
    }, 0)
  } else {
    window.addEventListener('load', function () {
      fireInitial('window-load')
    })
    document.addEventListener('readystatechange', function () {
      if (document.readyState === 'complete') fireInitial('readystatechange-complete')
    })
  }

  // 监听 body 尺寸变化（题目动态加载、回显数据、组件懒加载等），保证 footer 状态跟着内容变化
  if (typeof ResizeObserver !== 'undefined') {
    function startObservingBody() {
      if (!document.body) return false
      try {
        var ro = new ResizeObserver(function () {
          schedule(window)
        })
        ro.observe(document.body)
        if (document.documentElement) ro.observe(document.documentElement)
        return true
      } catch (e) {
        return false
      }
    }
    if (!startObservingBody()) {
      document.addEventListener('DOMContentLoaded', startObservingBody)
    }
  }
})()

// ===== 运行时状态转发：free 模式与页面样式 =====
;(function setupRuntimeStateForwarding() {
  let lastSignature = ''

  function isTransparentColor(color) {
    if (!color) return true
    const normalized = String(color).trim().toLowerCase()
    if (!normalized || normalized === 'transparent') return true
    if (normalized === 'rgba(0, 0, 0, 0)') return true

    const rgbaMatch = normalized.match(/^rgba\((.+)\)$/)
    if (rgbaMatch) {
      const parts = rgbaMatch[1].split(',').map(function (part) {
        return part.trim()
      })
      const alpha = Number.parseFloat(parts[3])
      return parts.length >= 4 && !Number.isNaN(alpha) && alpha === 0
    }

    const hslaMatch = normalized.match(/^hsla\((.+)\)$/)
    if (hslaMatch) {
      const hslaParts = hslaMatch[1].split(',').map(function (part) {
        return part.trim()
      })
      const hslaAlpha = Number.parseFloat(hslaParts[3])
      return hslaParts.length >= 4 && !Number.isNaN(hslaAlpha) && hslaAlpha === 0
    }

    return false
  }

  function getEffectiveBackgroundColor() {
    const candidates = [document.body, document.documentElement].filter(Boolean)
    for (let i = 0; i < candidates.length; i++) {
      try {
        const color = window.getComputedStyle(candidates[i]).backgroundColor
        if (!isTransparentColor(color)) return color
      } catch (e) {}
    }
    return '#ffffff'
  }

  function getRuntimeStyles() {
    return {
      backgroundColor: getEffectiveBackgroundColor(),
    }
  }

  function postRuntimeState() {
    if (!document.body) return

    const hasFreeClass = document.body.classList.contains('free')
    if (!hasFreeClass) return

    const payload = {
      type: 'SURVEY_RUNTIME_STATE',
      body: {
        className: document.body.className || '',
        hasFreeClass,
      },
      styles: getRuntimeStyles(),
      timestamp: Date.now(),
    }
    const signature = JSON.stringify({
      className: payload.body.className,
      hasFreeClass: payload.body.hasFreeClass,
      styles: payload.styles,
    })
    if (signature === lastSignature) return
    lastSignature = signature

    try {
      if (window.messagePort) window.messagePort.postMessage(payload)
      else window.parent.postMessage(payload, '*')
    } catch (e) {
      console.warn('[survey-core][runtime-state] postMessage failed', e)
    }
  }

  function scheduleRuntimeStatePost() {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(postRuntimeState)
    } else {
      setTimeout(postRuntimeState, 0)
    }
  }

  function startObservingBodyClass() {
    if (!document.body) return false
    scheduleRuntimeStatePost()

    if (typeof MutationObserver !== 'undefined') {
      try {
        const mo = new MutationObserver(function (mutations) {
          for (let i = 0; i < mutations.length; i++) {
            if (mutations[i].type === 'attributes' && mutations[i].attributeName === 'class') {
              scheduleRuntimeStatePost()
              break
            }
          }
        })
        mo.observe(document.body, { attributes: true, attributeFilter: ['class'] })
      } catch (e) {}
    }

    return true
  }

  if (!startObservingBodyClass()) {
    document.addEventListener('DOMContentLoaded', startObservingBodyClass)
  }
  window.addEventListener('load', scheduleRuntimeStatePost)
})()

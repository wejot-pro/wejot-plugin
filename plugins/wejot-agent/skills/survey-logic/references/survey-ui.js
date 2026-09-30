/* Survey UI Runtime
   - UI interactions, visual feedback, pagination
   - Required validation, progress bar
   - Sample questions filtering
   - Custom question type (39) hooks
   - Data collection / submission delegated to survey-bridge.js
*/

// ===== 只读基座开始（SURVEY_UI_INFRA_BEGIN）— 由模板维护，勿在下方首个 const/function 之前插入任何业务代码 =====
// 依赖已先加载的 survey-bridge：QUESTION_TYPES, SurveyAnswerState, SurveyDataBridge 等

;(function () {
  'use strict';

  /* ===== 本地化（由 generate_standard_survey.py 按问卷语种注入） ===== */
  /*__SURVEY_UI_I18N_BEGIN__*/
  const SURVEY_UI_I18N = {
    "continue": "继续",
    "submit": "提交问卷",
    "minSelect": "第{n}题最少选{m}项",
    "maxSelect": "第{n}题最多选{m}项",
    "minInput": "第{n}题至少输入{m}字",
    "maxInput": "第{n}题最多输入{m}字",
    "completeQuestion": "请完成第{n}题",
    "completeMatrixRow": "请完成第{n}题（每行都需选择）",
    "completeAll": "请完成所有必填题",
    "uploadedFile": "已上传文件",
    "delete": "删除",
    "pagination": "分页",
    "option": "选项 {n}",
    "untitled": "无标题",
    "choicesExact": "需选 {min} 项（已选 {count}/{max}）",
    "choicesRange": "至少选 {min} 项，最多 {max} 项（已选 {count}/{optMax}）",
    "choicesAtLeast": "至少选 {min} 项（已选 {count}）",
    "choicesAtMost": "最多选 {max} 项（已选 {count}/{optMax}）",
    "otherLabels": ["其它", "其他"]
  }
  /*__SURVEY_UI_I18N_END__*/
  function _suiT(key, params) {
    let msg = (SURVEY_UI_I18N && SURVEY_UI_I18N[key] != null) ? SURVEY_UI_I18N[key] : ''
    if (params) {
      Object.keys(params).forEach(function (k) {
        msg = String(msg).replace(new RegExp('\{' + k + '\}', 'g'), params[k])
      })
    }
    return msg
  }

  let messagePort = null
  let sampleQuestionFilter = null

  /* ===== MessageChannel ===== */
  window.addEventListener('message', e => {
    if (e.data && e.data.type === 'INIT_MESSAGE_CHANNEL' && e.ports && e.ports[0]) {
      messagePort = e.ports[0]
      window.messagePort = messagePort
      messagePort.onmessage = function (ev) {
        handlePortMessage(ev.data)
      }
      if (typeof SurveyApp !== 'undefined') {
        SurveyApp._channelReady = true
      }
    }
    // 预览态下接收宿主页的 scrollTo 指令，支持跨页跳转
    if (e.data && e.data.action === 'scrollTo' && e.data.selector) {
      if (window._surveyPagination && window._surveyPagination.scrollToQuestion) {
        window._surveyPagination.scrollToQuestion(e.data.selector)
      } else {
        const el = document.querySelector(e.data.selector)
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
    // 宿主页跨域时无法直接操作 iframe DOM，由 iframe 内部执行按钮抖动
    if (e.data && e.data.action === 'shakeSubmitButton') {
      const btn = document.querySelector('[data-nav-action="submit"]') || document.querySelector('[data-nav-action="next"]')
      if (btn) {
        const start = Date.now()
        const duration = 600
        const intensity = 40
        function shakeFrame() {
          const elapsed = Date.now() - start
          if (elapsed >= duration) {
            btn.style.transform = ''
            return
          }
          const offset = Math.sin(elapsed / 15) * intensity * (1 - elapsed / duration)
          btn.style.transform = 'translateX(' + offset + 'px)'
          requestAnimationFrame(shakeFrame)
        }
        requestAnimationFrame(shakeFrame)
      }
    }
  })

  function sendToHost(data) {
    if (messagePort) {
      try {
        messagePort.postMessage(data)
      } catch (err) {
        console.error(err)
      }
    } else {
      try {
        window.parent.postMessage(data, '*')
      } catch (err) {
        console.error(err)
      }
    }
  }

  function handlePortMessage(data) {
    if (!data) return
    if (data.type === 'SAMPLE_QUESTIONS_INIT') {
      try {
        sampleQuestionFilter = JSON.parse(data.sampleQuestions || '{}')
        applySampleFilter()
      } catch (e) {
        console.error('Sample questions parse error:', e)
      }
    }
  }

  /* ===== Sample Questions Filter ===== */
  function applySampleFilter() {
    if (!sampleQuestionFilter) return
    document.querySelectorAll('.q[data-question-uuid]').forEach(q => {
      const uuid = q.getAttribute('data-question-uuid')
      if (sampleQuestionFilter[uuid] === false) {
        q.classList.add('sample-hidden')
      } else {
        q.classList.remove('sample-hidden')
      }
    })
    if (window._surveyPagination && typeof window._surveyPagination.refresh === 'function') {
      window._surveyPagination.refresh()
    }
  }

  /* ===== Progress Bar ===== */
  function isQuestionAnswered(q) {
    if (q.querySelector('input[type="radio"]:checked')) return true
    if (q.querySelector('input[type="checkbox"]:checked')) return true
    const ta = q.querySelector('textarea')
    if (ta && ta.value.trim().length > 0) return true
    const sc = q.querySelector('[data-survey-role="scale-group"]')
    if (sc && sc.querySelector('.sel')) return true
    const mx = q.querySelector('[data-survey-role="matrix-group"]')
    if (mx) {
      const rows = mx.querySelectorAll('[data-survey-role="matrix-row"]')
      if (rows.length === 0) return false
      let allAnswered = true
      rows.forEach(r => {
        if (!r.querySelector('.sel')) allAnswered = false
      })
      if (allAnswered) return true
    }
    const fileInput = q.querySelector('input[type="file"]')
    if (fileInput && fileInput.dataset.uploadUrl) return true
    const qType = q.getAttribute('data-question-type')
    if ((qType === '39' || qType === 'GENERIC') && q.dataset.customValue) return true
    return false
  }

  function updateProgress() {
    // 进度基于整份问卷的所有题目计算，而非当前分页。
    // 仅排除被逻辑隐藏（data-logic-visible="false"）的题目；
    // 分页未展示（display:none）的题目仍需计入整卷进度。
    const questions = Array.from(document.querySelectorAll('.q')).filter(
      q => q.getAttribute('data-logic-visible') !== 'false'
    )
    const total = questions.length
    if (!total) return
    let answered = 0
    questions.forEach(q => {
      if (isQuestionAnswered(q)) answered++
    })
    const percent = Math.round((answered / total) * 100)
    const fill = document.getElementById('progressFill')
    const progBar = document.getElementById('progressBar')
    if (fill) fill.style.width = percent + '%'
    if (progBar) {
      // 编辑模式下隐藏进度条，答题/预览模式下显示
      progBar.style.display = document.body.classList.contains('wj-edit-mode') ? 'none' : ''
    }
  }


  /* ===== Click handler ===== */
  function bindSurveyClick() {
    const sh = document.querySelector('.sh')
    if (!sh || sh._surveyClickBound) return
    sh._surveyClickBound = true
    sh.addEventListener('click', e => {
      if (document.body.classList.contains('wj-edit-mode'))
        return

      const q = e.target.closest('.q')
      if (q)
        q.classList.remove('question-error')

      const opt = e.target.closest('.opt')
      if (opt) {
        const input = opt.querySelector('input')
        if (input && (input.type === 'radio' || input.type === 'checkbox')) {
          updateProgress()
        }
        return
      }

      const sc = e.target.closest('[data-option]')
      if (sc) {
        const row = sc.closest('[data-survey-role="matrix-row"]')
        if (row) {
          row.querySelectorAll('[data-option]').forEach(s => {
            s.classList.remove('sel')
          })
        } else {
          sc.parentElement.querySelectorAll('[data-option]').forEach(s => {
            s.classList.remove('sel')
          })
        }
        sc.classList.add('sel')
        updateProgress()
      }
    })
  }

  function bindMatrixStickyHeaders() {
    const matrixShells = Array.from(document.querySelectorAll('.matrix-shell[data-survey-role="matrix-group"]'))
    if (!matrixShells.length) return

    const hasHostTopBar = () =>
      document.body.classList.contains('wj-edit-mode') ||
      document.body.classList.contains('platform-pc') ||
      document.body.classList.contains('platform-h5')

    const updateStickyMask = () => {
      if (!hasHostTopBar()) {
        document.body.classList.remove('matrix-sticky-mask-visible')
        return
      }
      let stickyMask = document.querySelector('.matrix-sticky-top-mask')
      if (!stickyMask) {
        stickyMask = document.createElement('div')
        stickyMask.className = 'matrix-sticky-top-mask'
        stickyMask.setAttribute('aria-hidden', 'true')
        document.body.appendChild(stickyMask)
      }
      const active = matrixShells.some(shell => {
        const headerViewport = shell.querySelector('[data-survey-role="matrix-header-scroll"]')
        if (!headerViewport) return false
        const headerRect = headerViewport.getBoundingClientRect()
        const shellRect = shell.getBoundingClientRect()
        const computedTop = parseFloat(window.getComputedStyle(headerViewport).top)
        const stickyTop = Number.isFinite(computedTop) ? computedTop : 56
        return headerRect.top <= stickyTop + 1 && shellRect.bottom > stickyTop + headerRect.height
      })
      document.body.classList.toggle('matrix-sticky-mask-visible', active)
    }

    matrixShells.forEach(shell => {
      if (shell._matrixStickyHeaderBound) return
      const headerViewport = shell.querySelector('[data-survey-role="matrix-header-scroll"]')
      const bodyScroller = shell.querySelector('[data-survey-role="matrix-scroll"]')
      const header = headerViewport && headerViewport.querySelector('[data-survey-role="matrix-header"]')
      if (!headerViewport || !bodyScroller || !header) return
      shell._matrixStickyHeaderBound = true

      const syncHeader = () => {
        header.style.transform = 'translateX(' + (-bodyScroller.scrollLeft) + 'px)'
      }
      bodyScroller.addEventListener('scroll', syncHeader, { passive: true })
      window.addEventListener('resize', syncHeader)
      syncHeader()
    })
    window.addEventListener('scroll', updateStickyMask, { passive: true })
    window.addEventListener('resize', updateStickyMask)
    updateStickyMask()
  }

  /* ===== Input ===== */
  document.addEventListener('input', e => {
    const q = e.target.closest('.q')
    if (!q) return
    if (e.target.tagName === 'TEXTAREA') {
      q.classList.remove('question-error')
      updateProgress()
    }
  })

  /* ===== Pagination (static: initialized once, never rebuilt) ===== */
  ;(function () {
    const wrap = document.querySelector('.sh')
    if (!wrap) return

    let staticPages = []
    let idx = 0
    const prev = document.getElementById('prevBtn')
    const next = document.getElementById('nextBtn')
    const fill = document.getElementById('progressFill')

    function initStaticPages() {
      staticPages = []
      let cur = []
      wrap.childNodes.forEach(n => {
        if (n.nodeType !== 1) return
        if (n.classList.contains('pb')) {
          if (cur.length) staticPages.push(cur)
          cur = []
        } else if (n.classList.contains('q')) {
          cur.push(n)
        }
      })
      if (cur.length) staticPages.push(cur)
    }

    function isQuestionLogicVisible(q) {
      return q.getAttribute('data-logic-visible') !== 'false'
    }

    function hasVisiblePageAfter(pageIndex) {
      for (let i = pageIndex + 1; i < staticPages.length; i++) {
        if (staticPages[i].some(isQuestionLogicVisible)) return true
      }
      return false
    }

    function getPrevVisiblePage(pageIndex) {
      for (let i = pageIndex - 1; i >= 0; i--) {
        if (staticPages[i].some(isQuestionLogicVisible)) return i
      }
      return -1
    }

    function getNextVisiblePage(pageIndex) {
      for (let i = pageIndex + 1; i < staticPages.length; i++) {
        if (staticPages[i].some(isQuestionLogicVisible)) return i
      }
      return -1
    }

    initStaticPages()
    if (!staticPages.length) return

    function show(i) {
      const total = staticPages.length
      if (total === 0) return
      if (i < 0) i = 0
      if (i >= total) i = total - 1

      // 如果目标页没有可见题目，向后查找；若向后没有则向前查找
      let targetPage = i
      if (!staticPages[targetPage].some(isQuestionLogicVisible)) {
        targetPage = getNextVisiblePage(targetPage)
        if (targetPage === -1) targetPage = getPrevVisiblePage(i)
        if (targetPage === -1) targetPage = i
      }

      staticPages.forEach((p, pi) => {
        p.forEach(q => {
          if (pi === targetPage && isQuestionLogicVisible(q)) {
            q.style.display = ''
          } else {
            q.style.display = 'none'
          }
        })
      })
      // 通知当前页 GENERIC 组件变为可见
      staticPages[targetPage]?.forEach(q => {
        if (isQuestionLogicVisible(q)) _notifyGenericVisible(q, true)
      })
      wrap.querySelectorAll('.pb').forEach(b => { b.style.display = 'none' })
      idx = targetPage
      if (prev) prev.style.display = targetPage === 0 ? 'none' : ''
      if (next) next.textContent = hasVisiblePageAfter(targetPage) ? _suiT('continue') : _suiT('submit')
      updateProgress()
      window.scrollTo({ top: 0, behavior: 'smooth' })
      // 页码变更通知：上一页/下一页走闭包 show，不经过 window._surveyPagination.show 的包装
      if (typeof window.__surveyNotifyPageChange === 'function') {
        try { window.__surveyNotifyPageChange(targetPage) } catch (e) {}
      }
    }

    function refreshPagination() {
      // 静态分页：只刷新按钮文字并重新显示当前页
      if (!staticPages.length) initStaticPages()
      const total = staticPages.length
      if (total === 0) return
      if (idx >= total) idx = total - 1
      if (idx < 0) idx = 0
      staticPages.forEach((p, pi) => {
        p.forEach(q => {
          if (pi === idx && isQuestionLogicVisible(q)) {
            q.style.display = ''
          } else {
            q.style.display = 'none'
          }
        })
      })
      // 通知当前页 GENERIC 组件变为可见
      staticPages[idx]?.forEach(q => {
        if (isQuestionLogicVisible(q)) _notifyGenericVisible(q, true)
      })
      if (prev) prev.style.display = idx === 0 ? 'none' : ''
      if (next) next.textContent = hasVisiblePageAfter(idx) ? _suiT('continue') : _suiT('submit')
      updateProgress()
    }

    function validate(i) {
      const missing = []
      let firstEl = null
      let msg = ''
      if (!staticPages[i]) return { nums: missing, first: firstEl, msg }
      staticPages[i].forEach(q => {
        if (!isQuestionLogicVisible(q)) return
        const isRequired = !!q.querySelector('.req')
        let answered = false

        const qType = q.getAttribute('data-question-type')
        if (q.querySelector('input[type="checkbox"]')) {
          // checkbox 的 min/max-choices 校验与是否必填解耦:
          // 只要用户勾选了任意一项,就必须落在 [min, max] 区间内
          const checked = q.querySelectorAll('input[type="checkbox"]:checked')
          answered = checked.length > 0
          if (!isRequired && !answered) {
            q.classList.remove('question-error')
            return
          }
          if (answered) {
            const minC = parseInt(q.getAttribute('data-min-choices') || '0', 10)
            let maxC = parseInt(q.getAttribute('data-max-choices') || '100', 10)
            if (maxC === 0) {
              maxC = 100
            }
            if (checked.length < minC || checked.length > maxC) {
              answered = false
              const numEl = q.querySelector('[data-q-number]')
              const numStr = numEl ? numEl.textContent.trim() : ''
              if (!msg) {
                msg = checked.length < minC
                  ? _suiT('minSelect', { n: numStr, m: minC })
                  : _suiT('maxSelect', { n: numStr, m: maxC })
              }
            }
          }
        } else if (qType === '1' || qType === '3') {
          // 文本题:非必填且未填写直接放行;已填写时在提交前(切页/提交)就校验
          // 最少/最多输入字数,给出具体提示并定位到本题,而不是等服务端返回
          const ta = q.querySelector('textarea, input[data-input-type="text"], [data-input-type="text"]')
          if (!ta) return
          const textVal = ta.value.trim()
          answered = textVal.length > 0
          if (!isRequired && !answered) {
            q.classList.remove('question-error')
            return
          }
          if (answered) {
            const numEl = q.querySelector('[data-q-number]')
            const numStr = numEl ? numEl.textContent.trim() : ''
            const minL = parseInt(q.getAttribute('data-min-length') || ta.dataset.minLength || '0', 10)
            const maxL = parseInt(q.getAttribute('data-max-length') || ta.dataset.maxLength || '0', 10)
            if (minL > 0 && textVal.length < minL) {
              answered = false
              if (!msg) msg = _suiT('minInput', { n: numStr, m: minL })
            } else if (maxL > 0 && textVal.length > maxL) {
              answered = false
              if (!msg) msg = _suiT('maxInput', { n: numStr, m: maxL })
            }
          }
        } else {
          // 非 checkbox 题沿用旧策略:非必填直接放行
          if (!isRequired) return
          if (q.querySelector('input[type="radio"]')) {
            answered = !!q.querySelector('input[type="radio"]:checked')
          } else if (q.querySelector('[data-survey-role="scale-group"]') && !q.querySelector('[data-survey-role="matrix-group"]')) {
            answered = !!q.querySelector('.sel')
          } else if (q.querySelector('[data-survey-role="matrix-group"]')) {
            answered = true
            q.querySelectorAll('[data-survey-role="matrix-row"]').forEach(r => {
              if (!r.querySelector('.sel')) answered = false
            })
          } else if (q.querySelector('input[type="file"]')) {
            answered = !!q.querySelector('input[type="file"]').dataset.uploadUrl
          } else if (qType === '39' || qType === 'GENERIC') {
            answered = !!q.dataset.customValue
          }
        }

        if (!answered) {
          const num = q.querySelector('[data-q-number]')
          missing.push(num ? num.textContent.trim() : '')
          q.classList.add('question-error')
          if (!firstEl) firstEl = q
        } else {
          q.classList.remove('question-error')
        }
      })
      return { nums: missing, first: firstEl, msg }
    }

    function toast(msg) {
      const el = document.createElement('div')
      el.textContent = msg
      el.style.cssText =
        'position:fixed;top:50px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.75);color:#fff;padding:10px 20px;border-radius:8px;font-size:14px;z-index:99999;transition:opacity .3s;'
      document.body.appendChild(el)
      setTimeout(() => {
        el.style.opacity = '0'
        setTimeout(() => {
          el.remove()
        }, 300)
      }, 2500)
    }

    // 实时拦截 checkbox 超额勾选:勾选导致 checked 数超过 data-max-choices 时
    // 立即撤销本次勾选并 toast 提示,避免用户走到下一页才发现。
    // 注册在 capture 阶段并 stopImmediatePropagation,先于 survey-bridge 的 change 监听执行,
    // 防止超额答案被 bridge 误存进 SurveyAnswerState。
    if (wrap && !wrap._surveyMaxChoicesBound) {
      wrap._surveyMaxChoicesBound = true
      wrap.addEventListener('change', e => {
        if (document.body.classList.contains('wj-edit-mode')) return
        const cb = e.target
        if (!cb || cb.type !== 'checkbox' || !cb.checked) return
        const q = cb.closest('.q')
        if (!q) return
        const exclusiveChanged = _normalizeExclusiveCheckboxSelection(q, cb)
        if (exclusiveChanged) {
          const answer = _readDynamicQuestionAnswer(q, 'checkbox')
          if (typeof window.saveAnswerLocal === 'function') {
            window.saveAnswerLocal(
              q.getAttribute('data-question-uuid'),
              Number(q.getAttribute('data-question-type')),
              answer
            )
          }
          e.stopImmediatePropagation()
          updateProgress()
        }
        let maxC = parseInt(q.getAttribute('data-max-choices') || '100', 10)
        if (maxC === 0) {
          maxC = 100
        }
        const checked = q.querySelectorAll('input[type="checkbox"]:checked')
        if (checked.length > maxC) {
          cb.checked = false
          e.stopImmediatePropagation()
          const numEl = q.querySelector('[data-q-number]')
          const numStr = numEl ? numEl.textContent.trim() : ''
          toast(_suiT('maxSelect', { n: numStr, m: maxC }))
          updateProgress()
        }
      }, true)
    }

    // 实时拦截文本题超过最多字数的输入:保留合法前缀并立即 toast 提示,
    // 避免用户一直输入到提交时才收到"最多输入N字"的报错
    if (wrap && !wrap._surveyTextMaxBound) {
      wrap._surveyTextMaxBound = true
      wrap.addEventListener('input', e => {
        if (document.body.classList.contains('wj-edit-mode')) return
        const ta = e.target
        if (!ta) return
        const isTextInput = ta.tagName === 'TEXTAREA' || (ta.tagName === 'INPUT' && ta.getAttribute('data-input-type') === 'text')
        if (!isTextInput) return
        const q = ta.closest('.q')
        if (!q) return
        const qType = q.getAttribute('data-question-type')
        if (qType !== '1' && qType !== '3') return
        if (e.isComposing) return
        const maxL = parseInt(q.getAttribute('data-max-length') || ta.dataset.maxLength || '0', 10)
        if (maxL > 0 && ta.value.length > maxL) {
          const cut = ta.value.slice(0, maxL)
          ta.value = cut
          const numEl = q.querySelector('[data-q-number]')
          const numStr = numEl ? numEl.textContent.trim() : ''
          toast(_suiT('maxInput', { n: numStr, m: maxL }))
          try {
            ta.setSelectionRange(cut.length, cut.length)
          } catch (err) {}
        }
      }, true)
    }

    if (next) {
      next.addEventListener('click', () => {
        const nextVisible = getNextVisiblePage(idx)
        if (nextVisible !== -1) {
          var v = validate(idx)
          if (v.nums.length) {
            toast(v.msg || _suiT('completeQuestion', { n: v.nums.join('、') }))
            if (v.first) v.first.scrollIntoView({ behavior: 'smooth', block: 'center' })
            return
          }
          show(nextVisible)
        } else {
          var v = validate(idx)
          if (v.nums.length) {
            toast(v.msg || _suiT('completeQuestion', { n: v.nums.join('、') }))
            if (v.first) v.first.scrollIntoView({ behavior: 'smooth', block: 'center' })
            return
          }
          submitSurvey()
        }
      })
    }

    if (prev) {
      prev.addEventListener('click', () => {
        const prevVisible = getPrevVisiblePage(idx)
        if (prevVisible !== -1) show(prevVisible)
      })
    }

    function scrollToQuestion(selector) {
      const el = document.querySelector(selector)
      if (!el) return
      if (el.style.display === 'none') {
        for (let pi = 0; pi < staticPages.length; pi++) {
          if (staticPages[pi].includes(el)) {
            show(pi)
            break
          }
        }
      }
      setTimeout(() => {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 100)
    }

    window._surveyPagination = { show, scrollToQuestion, refresh: refreshPagination }

    show(0)
  })()

  /* ===== Upload UI Renderer (moved from survey-bridge.js so LLM can customize preview styles) ===== */
  function escapeHtml(text) {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  }

  function updateUploadUI(item, files) {
    const fileInput = item.querySelector('input[type="file"]')
    if (!fileInput) return
    const upLabel = fileInput.closest('label') || fileInput.parentElement
    if (!upLabel) return

    item.querySelectorAll('[data-upload-preview]').forEach(el => el.remove())

    if (!files || files.length === 0) {
      upLabel.style.display = ''
      fileInput.disabled = false
      fileInput.value = ''
      return
    }

    upLabel.style.display = 'none'

    files.forEach((file, index) => {
      const url = typeof file === 'string' ? file : (file?.url || file?.fileUrl || '')
      const name = typeof file === 'string' ? file.split('/').pop() : (file?.fileName || file?.name || _suiT('uploadedFile'))
      if (!url) return

      const isImage = /\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(name)
      const card = document.createElement('div')
      card.className = 'up-card'
      card.dataset.uploadPreview = ''
      card.dataset.index = String(index)

      if (isImage) {
        card.innerHTML = `
          <img class="up-thumb" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" />
          <div class="up-cap">${escapeHtml(name)}</div>
          <button class="fd-btn file-delete-btn" data-upload-delete data-index="${index}" title="${_suiT('delete')}">×</button>
        `
      } else {
        card.innerHTML = `
          <div class="up-card-inner">
            <span class="up-emoji">&#128196;</span>
            <span class="up-name">${escapeHtml(name)}</span>
          </div>
          <button class="fd-btn file-delete-btn" data-upload-delete data-index="${index}" title="${_suiT('delete')}">×</button>
        `
      }
      upLabel.parentElement.appendChild(card)
    })

    if (!item._fileDeleteBound) {
      item._fileDeleteBound = true
      item.addEventListener('click', e => {
        const btn = e.target.closest('[data-upload-delete]')
        if (!btn) return
        e.preventDefault()
        e.stopPropagation()

        const q = btn.closest('[data-question]')
        if (!q) return
        const qid = q.getAttribute('data-question-uuid')
        const idx = Number(btn.dataset.index)

        const answers = (typeof window.SurveyDataBridge !== 'undefined' && window.SurveyDataBridge.getAnswers) ? window.SurveyDataBridge.getAnswers() : []
        const existing = answers.find(a => a.questionUuid === qid)
        const current = existing && Array.isArray(existing.value) ? existing.value : []
        const next = current.filter((_, i) => i !== idx)

        const type = Number(q.getAttribute('data-question-type'))
        if (typeof window.saveAnswerLocal === 'function') {
          window.saveAnswerLocal(qid, type, next)
        }
        updateUploadUI(q, next)
      })
    }
  }

  document.addEventListener('surveyAnswerChanged', e => {
    const d = e.detail
    if (d && Number(d.questionType) === 15 && d.questionUuid) {
      const item = document.querySelector(`[data-question][data-question-uuid="${d.questionUuid}"]`)
      if (item) updateUploadUI(item, d.value)
    }
    // runtime 层 SurveyApp.setCustomValue 不再调用 dispatch，
    // 进度更新统一由 surveyAnswerChanged 事件触发
    updateProgress()
  })

  /* Platform detection */
  /* ===== Outline init for preview mode ===== */
  function buildOutlineData() {
    const questions = Array.from(document.querySelectorAll('[data-question]'))
    const pageBreaks = Array.from(document.querySelectorAll('[data-page-break]'))
    const allItems = [...questions, ...pageBreaks].sort((a, b) => {
      const position = a.compareDocumentPosition(b)
      return position & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
    })

    const outline = []
    let questionIndex = 0

    allItems.forEach(el => {
      const isPageBreak = el.hasAttribute('data-page-break')

      if (isPageBreak) {
        const pageText = el.querySelector('span')?.textContent?.trim() || _suiT('pagination')
        outline.push({ type: 'pageBreak', title: pageText })
      } else {
        questionIndex++
        const titleEl = el.querySelector('[data-title]')
        let title = ''
        if (titleEl) {
          title = titleEl.textContent
            .trim()
            .replace(/^\d+[.\s]*/, '')
            .substring(0, 25)
        }
        const qType = el.getAttribute('data-question-type') || ''
        const uuid = el.getAttribute('data-question-uuid') || ''
        const optionEls = el.querySelectorAll('[data-option]')
        const options = Array.from(optionEls).map((opt, idx) => ({
          index: idx,
          text: opt.textContent?.trim()?.substring(0, 20) || _suiT('option', { n: String.fromCharCode(65 + idx) }),
        }))
        outline.push({
          type: 'question',
          index: questionIndex,
          title: title || _suiT('untitled'),
          questionType: qType,
          uuid,
          domIndex: el.getAttribute('data-editor-index') || '',
          logicVisible: el.getAttribute('data-logic-visible') !== 'false',
          options,
        })
      }
    })
    return outline
  }

  function sendOutlineInit() {
    if (document.body.classList.contains('wj-edit-mode')) return
    const outline = buildOutlineData()
    if (outline.length > 0) {
      sendToHost({ action: 'OUTLINE_INIT', outline })
    }
  }

  function initSurvey() {
    bindSurveyClick()
    bindMatrixStickyHeaders()
    document.body.classList.add('loaded')
    updateProgress()
    sendOutlineInit()
    // 延迟执行业务逻辑，确保 IIFE 外部的 registerUserLogic 已注册
    if (typeof queueMicrotask === 'function') {
      queueMicrotask(function () {
        runUserLogic()
        maybeEnableLocalDraftFromDefault()
      })
    } else {
      setTimeout(function () {
        runUserLogic()
        maybeEnableLocalDraftFromDefault()
      }, 0)
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSurvey)
  } else {
    initSurvey()
  }

  /* ===== SurveyRuntime high-level APIs ===== */
  const _userLogicRegistry = []
  const _exclusiveCheckboxOptions = new WeakMap()
  const _questionOptionStates = new WeakMap()
  const _questionItemStates = new WeakMap()
  const _matrixRowTemplates = new WeakMap()
  const _questionOptionCatalogs = new WeakMap()
  const _matrixRowCatalogs = new WeakMap()
  const _questionContentDefaults = new WeakMap()
  const _logicDiagnostics = []
  const _localDraftRestoreHandlers = []
  function registerUserLogic(fn) { if (typeof fn === 'function') _userLogicRegistry.push(fn) }
  function runUserLogic() {
    if (_userLogicRegistry.length === 0) {
      console.warn('[SurveyRuntime] 业务逻辑扩展区为空：未检测到任何 registerUserLogic 调用。如果问卷需要逻辑分支/显隐/跳转，请在 BEGIN~END 标记之间编写代码。')
    }
    _userLogicRegistry.forEach((fn, index) => {
      try {
        fn()
      } catch (e) {
        const diagnostic = {
          phase: 'logic_init',
          code: 'USER_LOGIC_EXCEPTION',
          registrationIndex: index,
          message: e && e.message ? String(e.message) : String(e),
        }
        _logicDiagnostics.push(diagnostic)
        console.error('[SurveyRuntime] logic error:', e)
      }
    })
  }

  function getLogicDiagnostics() {
    return _cloneSerializable(_logicDiagnostics) || []
  }

  function onLocalDraftRestored(handler) {
    if (typeof handler === 'function') _localDraftRestoreHandlers.push(handler)
    return () => {
      const index = _localDraftRestoreHandlers.indexOf(handler)
      if (index >= 0) _localDraftRestoreHandlers.splice(index, 1)
    }
  }

  function _notifyLocalDraftRestored(detail) {
    _localDraftRestoreHandlers.slice().forEach((handler, index) => {
      try {
        handler(detail)
      } catch (e) {
        const diagnostic = {
          phase: 'draft_restore',
          code: 'DRAFT_RESTORE_HANDLER_EXCEPTION',
          registrationIndex: index,
          message: e && e.message ? String(e.message) : String(e),
        }
        _logicDiagnostics.push(diagnostic)
        console.error('[SurveyRuntime] draft restore handler error:', e)
      }
    })
  }

  function _resolveUuid(input) {
    if (!input) return input
    const byUuid = document.querySelector(`[data-question-uuid="${input}"]`)
    if (byUuid) return input
    const byCode = document.querySelector(`[data-code="${input}"]`)
    if (byCode) return byCode.getAttribute('data-question-uuid')
    return input
  }

  function _notifyGenericVisible(q, visible) {
    if (q.getAttribute('data-question-type') !== '39') return
    const container = q.querySelector('[data-survey-role="generic-container"]')
    if (!container) return
    container.dispatchEvent(new CustomEvent('generic:visible', {
      detail: { visible, questionUuid: q.getAttribute('data-question-uuid') },
      bubbles: true
    }))
  }

  function setLogicQuestionVisibility(uuid, visible) {
    const resolved = _resolveUuid(uuid)
    const q = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!q) return
    const req = q.querySelector('.req')
    if (req) req.style.display = (visible && q.getAttribute('data-required') === 'true') ? '' : 'none'
    q.setAttribute('data-logic-visible', visible ? 'true' : 'false')
    if (visible) _notifyGenericVisible(q, true)
    updateProgress()
    if (window._surveyPagination && typeof window._surveyPagination.refresh === 'function') {
      window._surveyPagination.refresh()
    }
    sendOutlineInit()
  }

  function setQuestionContent(uuid, content) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return _logicAnswerFailure('QUESTION_NOT_FOUND', resolved, 'UNKNOWN')
    const questionType = _questionTypeName(Number(question.getAttribute('data-question-type')))
    if (!content || typeof content !== 'object' || Array.isArray(content)) {
      return _logicAnswerFailure('INVALID_QUESTION_CONTENT', resolved, questionType)
    }
    const hasTitle = Object.prototype.hasOwnProperty.call(content, 'title')
    const hasDescription = Object.prototype.hasOwnProperty.call(content, 'description')
    if (!hasTitle && !hasDescription) {
      return _logicAnswerFailure('INVALID_QUESTION_CONTENT', resolved, questionType)
    }
    if ((hasTitle && content.title !== null && typeof content.title !== 'string')
      || (hasDescription && content.description !== null && typeof content.description !== 'string')) {
      return _logicAnswerFailure('INVALID_QUESTION_CONTENT', resolved, questionType)
    }
    const header = question.querySelector('.qh')
    const titleElement = question.querySelector('[data-title]')
    if (!header || (hasTitle && !titleElement)) {
      return _logicAnswerFailure('QUESTION_CONTENT_TARGET_MISSING', resolved, questionType)
    }
    let defaults = _questionContentDefaults.get(question)
    if (!defaults) {
      const descriptionElement = question.querySelector('.qd')
      defaults = {
        title: titleElement ? String(titleElement.textContent || '') : null,
        description: descriptionElement ? String(descriptionElement.textContent || '') : null,
        hadDescription: !!descriptionElement,
      }
      _questionContentDefaults.set(question, defaults)
    }
    if (hasTitle) titleElement.textContent = content.title === null ? defaults.title : content.title
    if (hasDescription) {
      let descriptionElement = question.querySelector('.qd')
      if (content.description === null && !defaults.hadDescription) {
        if (descriptionElement) descriptionElement.remove()
      } else {
        if (!descriptionElement) {
          descriptionElement = document.createElement('div')
          descriptionElement.className = 'qd'
          header.appendChild(descriptionElement)
        }
        descriptionElement.textContent = content.description === null ? defaults.description : content.description
      }
    }
    const currentDescription = question.querySelector('.qd')
    return {
      ok: true,
      questionUuid: resolved,
      questionType,
      content: {
        title: titleElement ? String(titleElement.textContent || '') : null,
        description: currentDescription ? String(currentDescription.textContent || '') : null,
      },
    }
  }

  function onLogicAnswerChange(handler) {
    document.addEventListener('surveyAnswerChanged', e => {
      if (!e.detail) return
      const protectedDetail = new Proxy(e.detail, {
        get(target, prop) {
          if (prop === 'questionIndex') {
            console.warn('[SurveyRuntime] e.detail.questionIndex 不存在。事件 detail 只提供 questionUuid、questionType、value、rawValue。请用 questionUuid 判断：if (detail.questionUuid !== Q1_UUID) return')
          }
          return target[prop]
        }
      })
      handler(protectedDetail)
    })
  }

  function getLogicAnswer(uuid) {
    const resolved = _resolveUuid(uuid)
    if (typeof window.SurveyDataBridge !== 'undefined' && typeof window.SurveyDataBridge.getAnswer === 'function') {
      return window.SurveyDataBridge.getAnswer(resolved)
    }
    return null
  }

  function _logicOptionByValue(question, value) {
    const expected = String(value)
    return Array.from(question.querySelectorAll('[data-option]')).find(option => {
      return String(option.getAttribute('data-option-value') || '') === expected
    }) || null
  }

  function _logicOptionLabel(option) {
    const labels = Array.from(option.querySelectorAll(':scope > span')).filter(span => {
      return !span.classList.contains('rd') && !span.classList.contains('cb')
    })
    const label = labels.length ? labels[labels.length - 1].textContent : option.textContent
    return String(label || '').trim()
  }

  function _logicOptionSchemaLabel(option) {
    return String(option.getAttribute('data-option-schema-label') || _logicOptionLabel(option)).trim()
  }

  function _logicOptionSerializedAttribute(option, name) {
    const raw = option.getAttribute(name)
    if (raw == null || raw === '') return undefined
    try { return JSON.parse(raw) } catch (e) { return raw }
  }

  function getSelectedQuestionItems(uuid) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return []
    const questionType = Number(question.getAttribute('data-question-type'))
    if (questionType === 28) {
      const exposure = getQuestionItemsExposure(resolved)
      const exposedByValue = new Map(((exposure && exposure.items) || []).map(item => [String(item.value), item]))
      return Array.from(question.querySelectorAll('[data-survey-role="matrix-row"]')).reduce((items, row) => {
        const selected = row.querySelector('[data-scale-value].sel')
        const score = selected && Number(selected.getAttribute('data-scale-value'))
        if (!Number.isFinite(score)) return items
        const schemaLabel = String(row.getAttribute('data-matrix-row-label') || '').trim()
        const rowValue = String(row.getAttribute('data-matrix-row-value') || schemaLabel).trim()
        if (!rowValue || !schemaLabel) return items
        const title = row.querySelector('.matrix-row-title') || row.querySelector(':scope > span')
        const label = String((title && title.textContent) || schemaLabel).trim()
        const exposed = exposedByValue.get(rowValue)
        const source = exposed && exposed.source !== undefined
          ? _cloneSerializable(exposed.source)
          : { questionUuid: resolved, optionValue: rowValue, userEntered: false }
        const meta = Object.assign(
          {},
          exposed && exposed.meta && typeof exposed.meta === 'object' ? _cloneSerializable(exposed.meta) : {},
          { score },
        )
        items.push({ value: resolved + ':' + rowValue, sourceValue: rowValue, label, schemaLabel, source, meta })
        return items
      }, [])
    }
    const inputType = questionType === 8 ? 'radio' : questionType === 9 ? 'checkbox' : null
    if (!inputType) return []
    return Array.from(question.querySelectorAll(`input[type="${inputType}"]:checked`)).reduce((items, input) => {
      const option = input.closest('[data-option]')
      if (!option) return items
      const optionValue = String(option.getAttribute('data-option-value') || input.value || '').trim()
      if (!optionValue) return items
      const editableOther = option.hasAttribute('data-option-other')
      const source = _logicOptionSerializedAttribute(option, 'data-option-source')
      const meta = _logicOptionSerializedAttribute(option, 'data-option-meta')
      const userEntered = editableOther || !!(source && typeof source === 'object' && source.userEntered === true)
      const otherInput = editableOther ? option.querySelector('[data-other-input]') : null
      const label = editableOther
        ? String((otherInput && otherInput.value) || '').trim()
        : _logicOptionLabel(option)
      if (!label) return items
      items.push({
        value: resolved + ':' + optionValue,
        sourceValue: optionValue,
        label,
        schemaLabel: _logicOptionSchemaLabel(option),
        source: source === undefined ? { questionUuid: resolved, optionValue, userEntered } : source,
        meta: meta === undefined ? {} : meta,
      })
      return items
    }, [])
  }

  function _clearLogicQuestionUi(question, questionType) {
    if (questionType === 8) {
      question.querySelectorAll('input[type="radio"]').forEach(input => { input.checked = false })
      question.querySelectorAll('[data-other-input]').forEach(input => { input.value = '' })
    } else if (questionType === 9) {
      question.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false })
      question.querySelectorAll('[data-other-input]').forEach(input => { input.value = '' })
    } else if (questionType === 1 || questionType === 3) {
      const input = question.querySelector('textarea, input[data-input-type="text"], [data-input-type="text"]')
      if (input) {
        if ('value' in input) input.value = ''
        else input.textContent = ''
      }
    } else if (questionType === 10 || questionType === 28) {
      question.querySelectorAll('[data-option], [data-scale-value]').forEach(option => {
        option.classList.remove('sel')
      })
    } else if (questionType === 39) {
      delete question.dataset.customValue
    }
  }

  function _clearStoredQuestionAnswer(question) {
    const uuid = question.getAttribute('data-question-uuid')
    const questionType = Number(question.getAttribute('data-question-type'))
    if (typeof window.saveAnswerLocal === 'function' && window.saveAnswerLocal._lastSignatures) {
      delete window.saveAnswerLocal._lastSignatures[uuid]
    }
    if (window.SurveyDataBridge && typeof window.SurveyDataBridge.getAnswers === 'function') {
      const answers = window.SurveyDataBridge.getAnswers()
      if (Array.isArray(answers)) {
        for (let i = answers.length - 1; i >= 0; i--) {
          if (answers[i] && answers[i].questionUuid === uuid) answers.splice(i, 1)
        }
      }
    }
    document.dispatchEvent(new CustomEvent('surveyAnswerChanged', {
      detail: { questionUuid: uuid, questionType, value: null, rawValue: null }
    }))
  }

  function setLogicAnswer(uuid, value, config) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return _logicAnswerFailure('QUESTION_NOT_FOUND', resolved, 'UNKNOWN')
    const questionType = Number(question.getAttribute('data-question-type'))
    const questionTypeName = _questionTypeName(questionType)
    if (typeof window.saveAnswerLocal !== 'function') {
      return _logicAnswerFailure('ANSWER_WRITER_UNAVAILABLE', resolved, questionTypeName)
    }
    const opts = config && typeof config === 'object' ? config : {}

    if (value == null) {
      _clearLogicQuestionUi(question, questionType)
      question.removeAttribute('data-logic-submit-answer')
      _clearStoredQuestionAnswer(question)
      updateProgress()
      return _logicAnswerSuccess(resolved, questionTypeName, null, true)
    }

    let normalized = null
    let applyUi = null

    if (questionType === 8) {
      const optionValue = value && typeof value === 'object' ? value.optionValue : value
      if (optionValue == null || String(optionValue) === '') {
        return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      }
      const option = _logicOptionByValue(question, optionValue)
      const input = option && option.querySelector('input[type="radio"]')
      if (!option || !input) return _logicAnswerFailure('OPTION_NOT_FOUND', resolved, questionTypeName)
      const isOther = option.hasAttribute('data-option-other')
      const otherText = isOther && value && typeof value === 'object' && value.otherText != null
        ? String(value.otherText)
        : null
      normalized = {
        optionValue: String(optionValue),
        value: _logicOptionSchemaLabel(option),
        otherText,
      }
      applyUi = function () {
        question.querySelectorAll('input[type="radio"]').forEach(other => { other.checked = false })
        input.checked = true
        const otherInput = option.querySelector('[data-other-input]')
        if (otherInput) otherInput.value = otherText || ''
      }
    } else if (questionType === 9) {
      const optionValues = value && typeof value === 'object' && Array.isArray(value.optionValues)
        ? value.optionValues
        : value
      if (!Array.isArray(optionValues) || optionValues.length === 0) {
        return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      }
      const uniqueValues = Array.from(new Set(optionValues.map(String)))
      if (uniqueValues.length !== optionValues.length) {
        return _logicAnswerFailure('DUPLICATE_OPTION', resolved, questionTypeName)
      }
      const maxChoices = Number(question.getAttribute('data-max-choices'))
      if (Number.isFinite(maxChoices) && maxChoices > 0 && uniqueValues.length > maxChoices) {
        return _logicAnswerFailure('MAX_CHOICES_EXCEEDED', resolved, questionTypeName)
      }
      const options = uniqueValues.map(optionValue => _logicOptionByValue(question, optionValue))
      if (options.some(option => !option || !option.querySelector('input[type="checkbox"]'))) {
        return _logicAnswerFailure('OPTION_NOT_FOUND', resolved, questionTypeName)
      }
      const exclusive = _exclusiveCheckboxOptions.get(question)
      if (exclusive && uniqueValues.length > 1 && uniqueValues.some(optionValue => exclusive.has(optionValue))) {
        return _logicAnswerFailure('EXCLUSIVE_OPTION_CONFLICT', resolved, questionTypeName)
      }
      const requestedOtherTexts = value && typeof value === 'object' && Array.isArray(value.otherTexts)
        ? value.otherTexts
        : []
      const otherTexts = options.map((option, index) => {
        if (!option.hasAttribute('data-option-other')) return null
        return requestedOtherTexts[index] == null ? null : String(requestedOtherTexts[index])
      })
      normalized = {
        optionValues: uniqueValues,
        value: options.map(_logicOptionSchemaLabel),
        otherTexts,
      }
      applyUi = function () {
        question.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false })
        options.forEach((option, index) => {
          option.querySelector('input[type="checkbox"]').checked = true
          const otherInput = option.querySelector('[data-other-input]')
          if (otherInput) otherInput.value = otherTexts[index] || ''
        })
      }
    } else if (questionType === 1 || questionType === 3) {
      const text = typeof value === 'string' ? value : String(value)
      const input = question.querySelector('textarea, input[data-input-type="text"], [data-input-type="text"]')
      if (!input) return _logicAnswerFailure('ANSWER_WRITER_UNAVAILABLE', resolved, questionTypeName)
      normalized = text
      applyUi = function () {
        if ('value' in input) input.value = text
        else input.textContent = text
      }
    } else if (questionType === 10) {
      const score = Number(value)
      if (!Number.isFinite(score)) return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      const option = Array.from(question.querySelectorAll('[data-option], [data-scale-value]')).find(item => {
        const raw = item.getAttribute('data-scale-value') || item.textContent.trim()
        return Number(raw) === score
      })
      if (!option) return _logicAnswerFailure('SCALE_VALUE_NOT_FOUND', resolved, questionTypeName)
      normalized = score
      applyUi = function () {
        question.querySelectorAll('[data-option], [data-scale-value]').forEach(item => item.classList.remove('sel'))
        option.classList.add('sel')
      }
    } else if (questionType === 28) {
      if (!Array.isArray(value) || value.length === 0) {
        return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      }
      const rows = []
      const rowElements = []
      const seenRows = new Set()
      for (let i = 0; i < value.length; i++) {
        const row = value[i]
        if (!row || row.rowTitle == null || !Number.isFinite(Number(row.score))) {
          return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
        }
        const rowTitle = String(row.rowTitle)
        if (seenRows.has(rowTitle)) return _logicAnswerFailure('DUPLICATE_MATRIX_ROW', resolved, questionTypeName)
        seenRows.add(rowTitle)
        const rowElement = Array.from(question.querySelectorAll('[data-survey-role="matrix-row"], [data-matrix-row-label]')).find(item => {
          return String(item.getAttribute('data-matrix-row-label') || '') === rowTitle
        })
        if (!rowElement) return _logicAnswerFailure('MATRIX_ROW_NOT_FOUND', resolved, questionTypeName)
        const score = Number(row.score)
        const option = Array.from(rowElement.querySelectorAll('[data-option], [data-scale-value]')).find(item => {
          const raw = item.getAttribute('data-scale-value') || item.textContent.trim()
          return Number(raw) === score
        })
        if (!option) return _logicAnswerFailure('SCALE_VALUE_NOT_FOUND', resolved, questionTypeName)
        rows.push({ rowTitle, score })
        rowElements.push({ rowElement, option })
      }
      normalized = rows
      applyUi = function () {
        question.querySelectorAll('[data-survey-role="matrix-row"], [data-matrix-row-label]').forEach(row => {
          row.querySelectorAll('[data-option], [data-scale-value]').forEach(item => item.classList.remove('sel'))
        })
        rowElements.forEach(entry => entry.option.classList.add('sel'))
      }
    } else if (questionType === 39) {
      if (typeof value !== 'object') return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      normalized = _cloneSerializable(value)
      if (normalized == null) return _logicAnswerFailure('INVALID_ANSWER', resolved, questionTypeName)
      applyUi = function () {
        question.dataset.customValue = JSON.stringify(normalized)
      }
    } else {
      return _logicAnswerFailure('UNSUPPORTED_QUESTION_TYPE', resolved, questionTypeName)
    }

    applyUi()
    if (opts.submitWhenHidden === true) {
      question.setAttribute('data-logic-submit-answer', 'true')
    } else {
      question.removeAttribute('data-logic-submit-answer')
    }
    window.saveAnswerLocal(resolved, questionType, normalized)
    updateProgress()
    return _logicAnswerSuccess(resolved, questionTypeName, normalized, false)
  }

  function _checkboxOptionValue(input) {
    const option = input && input.closest ? input.closest('[data-option]') : null
    return String((option && option.getAttribute('data-option-value')) || (input && input.value) || '')
  }

  function _normalizeExclusiveCheckboxSelection(question, selected) {
    const exclusive = _exclusiveCheckboxOptions.get(question)
    if (!exclusive || !selected || !selected.checked) return false
    const selectedExclusive = exclusive.has(_checkboxOptionValue(selected))
    let changed = false
    question.querySelectorAll('input[type="checkbox"]:checked').forEach(other => {
      if (other === selected) return
      if (selectedExclusive || exclusive.has(_checkboxOptionValue(other))) {
        other.checked = false
        changed = true
      }
    })
    return changed
  }

  function setCheckboxOptionExclusivity(uuid, exclusiveValues) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question || !Array.isArray(exclusiveValues) || exclusiveValues.length === 0) return false
    const normalized = exclusiveValues.map(value => {
      if (String(value) !== '__other__') return String(value)
      const other = question.querySelector('[data-option-other]')
      return other ? String(other.getAttribute('data-option-value') || '') : ''
    }).filter(Boolean)
    if (!normalized.length) return false
    _exclusiveCheckboxOptions.set(question, new Set(normalized))
    return true
  }

  function _cloneSerializable(value) {
    if (value === undefined) return undefined
    try { return JSON.parse(JSON.stringify(value)) } catch (e) { return null }
  }

  function _logicAssignmentFailure(code, key) {
    const diagnostic = { phase: 'logic_assignment', code, key: String(key || '') }
    _logicDiagnostics.push(diagnostic)
    console.error('[SurveyRuntime] stable assignment failed:', diagnostic)
    return { ok: false, code, key: diagnostic.key }
  }

  function _logicAssignmentStorageKey() {
    return 'wejot_logic_assignments_' + _localDraftDefaultKey()
  }

  function getStableRandomAssignment(key, variants) {
    const normalizedKey = String(key || '').trim()
    const normalized = _cloneSerializable(variants)
    if (!normalizedKey || !Array.isArray(normalized) || normalized.length < 1) {
      return _logicAssignmentFailure('INVALID_ASSIGNMENT', normalizedKey)
    }
    const identities = normalized.map(value => JSON.stringify(value))
    if (identities.some(value => value === undefined) || new Set(identities).size !== normalized.length) {
      return _logicAssignmentFailure('INVALID_VARIANTS', normalizedKey)
    }
    if (normalized.length === 1) {
      return { ok: true, key: normalizedKey, index: 0, value: normalized[0] }
    }

    const signature = JSON.stringify(normalized)
    try {
      const storageKey = _logicAssignmentStorageKey()
      const raw = localStorage.getItem(storageKey)
      const records = raw ? JSON.parse(raw) : {}
      const safeRecords = records && typeof records === 'object' && !Array.isArray(records) ? records : {}
      const previous = safeRecords[normalizedKey]
      if (previous && previous.signature === signature
        && Number.isInteger(previous.index) && previous.index >= 0 && previous.index < normalized.length) {
        return { ok: true, key: normalizedKey, index: previous.index, value: normalized[previous.index] }
      }
      const index = Math.floor(Math.random() * normalized.length)
      safeRecords[normalizedKey] = { signature, index }
      localStorage.setItem(storageKey, JSON.stringify(safeRecords))
      return { ok: true, key: normalizedKey, index, value: normalized[index] }
    } catch (e) {
      return _logicAssignmentFailure('ASSIGNMENT_STORAGE_UNAVAILABLE', normalizedKey)
    }
  }

  function _normalizeQuestionOptions(options, allowMissingLabel) {
    if (!Array.isArray(options)) return null
    const seen = new Set()
    const normalized = []
    for (let i = 0; i < options.length; i++) {
      const raw = options[i]
      if (!raw || typeof raw !== 'object') return null
      const value = raw.value == null ? '' : String(raw.value).trim()
      const label = raw.label == null ? '' : String(raw.label).trim()
      if (!value || (!label && !allowMissingLabel) || seen.has(value)) return null
      seen.add(value)
      const option = { value, label }
      if (raw.source !== undefined) option.source = _cloneSerializable(raw.source)
      if (raw.meta !== undefined) option.meta = _cloneSerializable(raw.meta)
      if (raw.schemaLabel !== undefined) option.schemaLabel = String(raw.schemaLabel)
      normalized.push(option)
    }
    return normalized
  }

  function _shuffleQuestionOptions(options, random) {
    const result = options.slice()
    const nextRandom = typeof random === 'function' ? random : Math.random
    for (let i = result.length - 1; i > 0; i--) {
      const sample = Number(nextRandom())
      const bounded = Number.isFinite(sample) ? Math.max(0, Math.min(0.999999999999, sample)) : 0
      const j = Math.floor(bounded * (i + 1))
      const tmp = result[i]
      result[i] = result[j]
      result[j] = tmp
    }
    return result
  }

  // Keep a shuffled exposure stable for the same answer attempt, including a
  // local-draft reload. The cache is keyed by the candidate signature so a
  // later branch change cannot reuse an incompatible ordering.
  function _questionOptionOrderKey(uuid) {
    return 'wejot_option_order_' + _localDraftDefaultKey() + '_' + uuid
  }

  function _readPersistedQuestionOptionOrder(uuid, signature, normalized) {
    try {
      const raw = localStorage.getItem(_questionOptionOrderKey(uuid))
      if (!raw) return null
      const records = JSON.parse(raw)
      if (!Array.isArray(records)) return null
      const record = records.find(item => item && item.signature === signature)
      if (!record || !Array.isArray(record.values) || record.values.length !== normalized.length) return null
      const byValue = new Map(normalized.map(option => [option.value, option]))
      const ordered = record.values.map(value => byValue.get(value))
      return ordered.every(Boolean) && new Set(record.values).size === normalized.length ? ordered : null
    } catch (e) {
      return null
    }
  }

  function _persistQuestionOptionOrder(uuid, signature, ordered) {
    try {
      const key = _questionOptionOrderKey(uuid)
      const raw = localStorage.getItem(key)
      const records = raw ? JSON.parse(raw) : []
      const next = Array.isArray(records) ? records.filter(item => item && item.signature !== signature) : []
      next.push({ signature, values: ordered.map(option => option.value) })
      localStorage.setItem(key, JSON.stringify(next.slice(-32)))
    } catch (e) {}
  }

  function _readSelectedOptionValues(question, inputType) {
    return Array.from(question.querySelectorAll(`input[type="${inputType}"]:checked`)).map(input => {
      const option = input.closest('[data-option]')
      return String((option && option.getAttribute('data-option-value')) || input.value || '')
    })
  }

  function _readDynamicQuestionAnswer(question, inputType) {
    const selected = Array.from(question.querySelectorAll(`input[type="${inputType}"]:checked`))
    if (!selected.length) return null
    if (inputType === 'radio') {
      const input = selected[0]
      const option = input.closest('[data-option]')
      return {
        optionValue: option ? option.getAttribute('data-option-value') : input.value,
        value: option ? _logicOptionSchemaLabel(option) : input.value,
        otherText: null,
      }
    }
    return {
      optionValues: selected.map(input => {
        const option = input.closest('[data-option]')
        return option ? option.getAttribute('data-option-value') : input.value
      }),
      value: selected.map(input => {
        const option = input.closest('[data-option]')
        return option ? _logicOptionSchemaLabel(option) : input.value
      }),
      otherTexts: selected.map(() => null),
    }
  }

  function _clearDynamicQuestionAnswer(question) {
    question.removeAttribute('data-logic-submit-answer')
    _clearStoredQuestionAnswer(question)
  }

  function _syncDynamicQuestionAnswer(question, inputType, hadSelection) {
    const answer = _readDynamicQuestionAnswer(question, inputType)
    if (answer && typeof window.saveAnswerLocal === 'function') {
      window.saveAnswerLocal(
        question.getAttribute('data-question-uuid'),
        Number(question.getAttribute('data-question-type')),
        answer
      )
    } else if (!answer && hadSelection) {
      _clearDynamicQuestionAnswer(question)
    }
  }

  function _buildDynamicOption(question, inputType, inputName, option, index, selectedValues) {
    const label = document.createElement('label')
    label.className = 'opt'
    label.setAttribute('data-option', '')
    label.setAttribute('data-option-value', option.value)
    label.setAttribute('data-option-schema-label', option.schemaLabel || option.label)
    label.setAttribute('data-option-reference-index', String(index))
    if (option.source !== undefined) {
      const source = JSON.stringify(option.source)
      label.setAttribute('data-option-source', source === undefined ? String(option.source) : source)
    }
    if (option.meta !== undefined) {
      const meta = JSON.stringify(option.meta)
      label.setAttribute('data-option-meta', meta === undefined ? String(option.meta) : meta)
    }

    const input = document.createElement('input')
    input.type = inputType
    input.name = inputName
    input.value = option.value
    input.checked = selectedValues.has(option.value)

    const marker = document.createElement('span')
    marker.className = inputType === 'radio' ? 'rd' : 'cb'
    const text = document.createElement('span')
    text.textContent = option.label
    label.append(input, marker, text)
    return label
  }

  function _setQuestionOptions(uuid, options, config) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return false
    const questionType = Number(question.getAttribute('data-question-type'))
    const inputType = questionType === 8 ? 'radio' : questionType === 9 ? 'checkbox' : null
    if (!inputType) return false

    const normalized = _normalizeQuestionOptions(options)
    if (!normalized) return false
    const opts = config && typeof config === 'object' ? config : {}
    const shuffle = opts.shuffle === true
    const signature = JSON.stringify({ options: normalized, shuffle })
    const previousState = _questionOptionStates.get(question)
    if (previousState && previousState.signature === signature) {
      return _cloneSerializable(previousState.exposure)
    }

    const body = question.querySelector('.qb')
    if (!body) return false
    const existingInput = body.querySelector(`input[type="${inputType}"]`)
    const inputName = (existingInput && existingInput.name) || question.getAttribute('data-code') || resolved
    const selectedBefore = _readSelectedOptionValues(question, inputType)
    const selectedValues = new Set(selectedBefore)
    let ordered
    if (shuffle) {
      ordered = _readPersistedQuestionOptionOrder(resolved, signature, normalized)
        || _shuffleQuestionOptions(normalized, opts.random)
      _persistQuestionOptionOrder(resolved, signature, ordered)
    } else {
      ordered = normalized.slice()
    }
    const fragment = document.createDocumentFragment()
    ordered.forEach((option, index) => {
      fragment.appendChild(_buildDynamicOption(question, inputType, inputName, option, index, selectedValues))
    })
    body.replaceChildren(fragment)

    const exposure = {
      questionUuid: resolved,
      count: ordered.length,
      shuffled: shuffle,
      options: ordered.map((option, index) => {
        const exposed = { value: option.value, label: option.label, index }
        if (option.schemaLabel !== undefined) exposed.schemaLabel = option.schemaLabel
        if (option.source !== undefined) exposed.source = _cloneSerializable(option.source)
        if (option.meta !== undefined) exposed.meta = _cloneSerializable(option.meta)
        return exposed
      }),
    }
    question.setAttribute('data-option-reference', 'true')
    question.setAttribute('data-option-exposure', JSON.stringify(exposure))
    _questionOptionStates.set(question, { signature, exposure })
    _syncDynamicQuestionAnswer(question, inputType, selectedBefore.length > 0)
    updateProgress()
    return _cloneSerializable(exposure)
  }

  function _getQuestionOptionExposure(uuid) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return null
    const state = _questionOptionStates.get(question)
    if (state) return _cloneSerializable(state.exposure)
    const raw = question.getAttribute('data-option-exposure')
    if (!raw) return null
    try { return JSON.parse(raw) } catch (e) { return null }
  }

  function _questionTypeName(questionType) {
    if (questionType === 8) return 'RADIO'
    if (questionType === 9) return 'CHECKBOX'
    if (questionType === 28) return 'MATRIX_SCALE'
    if (questionType === 39) return 'GENERIC'
    if (questionType === 10) return 'SCALE'
    if (questionType === 1 || questionType === 3) return 'TEXTAREA'
    if (questionType === 15) return 'UPLOAD'
    return String(questionType || 'UNKNOWN')
  }

  function _logicAnswerFailure(code, questionUuid, questionType) {
    return { ok: false, code, questionUuid, questionType }
  }

  function _logicAnswerSuccess(questionUuid, questionType, answer, cleared) {
    return {
      ok: true,
      questionUuid,
      questionType,
      answer: _cloneSerializable(answer),
      cleared: cleared === true,
    }
  }

  function _questionItemFailure(code, resolved, targetType, slot, details) {
    const failure = { ok: false, code, questionUuid: resolved, questionType: targetType, slot }
    return Object.assign(failure, details && typeof details === 'object' ? details : {})
  }

  function _questionAnswerValue(uuid) {
    const answer = getLogicAnswer(uuid)
    if (!answer) return null
    return answer.value === undefined ? answer : answer.value
  }

  function _buildQuestionItemExposure(resolved, targetType, slot, items, shuffled) {
    return {
      questionUuid: resolved,
      questionType: targetType,
      slot,
      count: items.length,
      shuffled: shuffled === true,
      items: items.map((item, index) => {
        const exposed = { value: item.value, label: item.label, index }
        if (item.schemaLabel !== undefined) exposed.schemaLabel = item.schemaLabel
        if (item.source !== undefined) exposed.source = _cloneSerializable(item.source)
        if (item.meta !== undefined) exposed.meta = _cloneSerializable(item.meta)
        return exposed
      }),
    }
  }

  function _storeQuestionItemExposure(question, signature, exposure) {
    question.setAttribute('data-question-item-reference', 'true')
    question.setAttribute('data-question-item-exposure', JSON.stringify(exposure))
    _questionItemStates.set(question, { signature, exposure })
  }

  function _storeQuestionItemCatalog(question, slot, catalog) {
    if (question.hasAttribute('data-question-item-catalog')) return
    const items = Array.from(catalog.values()).map(item => ({
      value: item.value,
      schemaLabel: item.schemaLabel,
    }))
    question.setAttribute('data-question-item-catalog', JSON.stringify({ slot, items }))
  }

  function _isOtherSchemaLabel(label) {
    const normalized = String(label || '').trim().replace(/\s+/g, '')
    const otherLabels = (SURVEY_UI_I18N && SURVEY_UI_I18N.otherLabels) || ['其它', '其他']
    return otherLabels.some(label => normalized.indexOf(label) === 0)
  }

  function _questionOptionCatalog(question) {
    const cached = _questionOptionCatalogs.get(question)
    if (cached) return cached
    const catalog = new Map()
    question.querySelectorAll('[data-option][data-option-value]').forEach(option => {
      const value = String(option.getAttribute('data-option-value') || '').trim()
      const schemaLabel = _logicOptionSchemaLabel(option)
      if (value && schemaLabel && !catalog.has(value)) {
        catalog.set(value, {
          value,
          schemaLabel,
          isOther: option.hasAttribute('data-option-other') || _isOtherSchemaLabel(schemaLabel),
        })
      }
    })
    _storeQuestionItemCatalog(question, 'options', catalog)
    _questionOptionCatalogs.set(question, catalog)
    return catalog
  }

  function _matrixRowCatalog(question) {
    const cached = _matrixRowCatalogs.get(question)
    if (cached) return cached
    const catalog = new Map()
    question.querySelectorAll('[data-survey-role="matrix-row"]').forEach(row => {
      if (row.getAttribute('data-matrix-row-template') === 'true') return
      const schemaLabel = String(row.getAttribute('data-matrix-row-label') || '').trim()
      const value = String(row.getAttribute('data-matrix-row-value') || schemaLabel).trim()
      if (!value || !schemaLabel || schemaLabel.indexOf('__dynamic_matrix_row_template__') >= 0) return
      if (!catalog.has(value)) {
        catalog.set(value, {
          value,
          schemaLabel,
          isOther: row.hasAttribute('data-matrix-row-other') || _isOtherSchemaLabel(schemaLabel),
        })
      }
    })
    _storeQuestionItemCatalog(question, 'matrixRows', catalog)
    _matrixRowCatalogs.set(question, catalog)
    return catalog
  }

  function _applyQuestionItemCatalog(items, catalog) {
    const bySchemaLabel = new Map()
    let uniqueOther = null
    catalog.forEach(entry => {
      const label = entry.schemaLabel
      if (!bySchemaLabel.has(label)) bySchemaLabel.set(label, entry)
      else bySchemaLabel.set(label, null)
      if (entry.isOther) uniqueOther = uniqueOther === null ? entry : false
    })
    const mapped = []
    const mappedValues = new Set()
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      const catalogItem = catalog.get(item.value)
        || (item.schemaLabel ? bySchemaLabel.get(item.schemaLabel) : null)
        || (item.source && item.source.userEntered === true && uniqueOther ? uniqueOther : null)
      if (!catalogItem) return { itemValue: item.value }
      if (mappedValues.has(catalogItem.value)) {
        return { itemValue: item.value, schemaValue: catalogItem.value, collision: true }
      }
      mappedValues.add(catalogItem.value)
      mapped.push(Object.assign({}, item, {
        value: catalogItem.value,
        label: item.label || catalogItem.schemaLabel,
        schemaLabel: catalogItem.schemaLabel,
      }))
    }
    return { items: mapped }
  }

  function _matrixRowTemplate(question) {
    const cached = _matrixRowTemplates.get(question)
    if (cached) return cached
    let row = question.querySelector('[data-survey-role="matrix-row"]')
    if (!row) {
      const holder = question.querySelector('template[data-survey-role="matrix-row-template"]')
      row = holder && holder.content
        ? holder.content.querySelector('[data-survey-role="matrix-row"]')
        : null
    }
    if (!row) return null
    const template = row.cloneNode(true)
    template.removeAttribute('data-matrix-row-template')
    _matrixRowTemplates.set(question, template)
    return template
  }

  function _matrixAnswerByValue(previousAnswer, previousExposure, currentItems) {
    const labelToValue = new Map()
    if (previousExposure && Array.isArray(previousExposure.items)) {
      previousExposure.items.forEach(item => {
        labelToValue.set(String(item.schemaLabel || item.label), String(item.value))
      })
    }
    if (Array.isArray(currentItems)) {
      currentItems.forEach(item => {
        const value = String(item.value)
        if (item.schemaLabel != null) labelToValue.set(String(item.schemaLabel), value)
        if (item.label != null) labelToValue.set(String(item.label), value)
      })
    }
    const result = new Map()
    const rows = Array.isArray(previousAnswer) ? previousAnswer : []
    rows.forEach(row => {
      if (!row || row.rowTitle == null || !Number.isFinite(Number(row.score))) return
      const value = labelToValue.get(String(row.rowTitle))
      if (value) result.set(value, Number(row.score))
    })
    return result
  }

  function _matrixRowMount(group) {
    // Nested generator DOM: rows live under matrix-body (inside .mx).
    // Flat legacy DOM: rows are direct children of matrix-group (.mx).
    const body = group.querySelector('[data-survey-role="matrix-body"]')
    if (body) return body
    const existing = group.querySelector('[data-survey-role="matrix-row"]')
    if (existing && existing.parentNode) return existing.parentNode
    return group
  }

  function _setMatrixQuestionItems(question, resolved, targetType, normalized, signature) {
    const group = question.querySelector('[data-survey-role="matrix-group"]')
    const template = _matrixRowTemplate(question)
    if (!group || (!template && normalized.length > 0)) {
      return _questionItemFailure('MATRIX_ROW_TEMPLATE_MISSING', resolved, targetType, 'matrixRows')
    }
    const previousState = _questionItemStates.get(question)
    if (previousState && previousState.signature === signature) {
      return {
        ok: true, questionUuid: resolved, questionType: targetType, slot: 'matrixRows',
        exposure: _cloneSerializable(previousState.exposure), answerChanged: false,
      }
    }
    const rowMount = _matrixRowMount(group)
    const previousRows = Array.from(group.querySelectorAll('[data-survey-role="matrix-row"]')).map(row => ({
      row,
      parent: row.parentNode,
      nextSibling: row.nextSibling,
    }))
    const previousReferenceAttribute = question.getAttribute('data-question-item-reference')
    const previousExposureAttribute = question.getAttribute('data-question-item-exposure')
    const previousAnswer = _questionAnswerValue(resolved)
    const scoresByValue = _matrixAnswerByValue(
      previousAnswer,
      previousState && previousState.exposure,
      normalized,
    )
    const rows = document.createDocumentFragment()
    normalized.forEach(item => {
      const row = template.cloneNode(true)
      row.setAttribute('data-matrix-row', item.schemaLabel)
      row.setAttribute('data-matrix-row-label', item.schemaLabel)
      row.setAttribute('data-matrix-row-value', item.value)
      const title = row.querySelector('.matrix-row-title') || row.querySelector(':scope > span')
      if (title) title.textContent = item.label
      row.querySelectorAll('[data-option], [data-scale-value]').forEach(option => option.classList.remove('sel'))
      const score = scoresByValue.get(item.value)
      if (score !== undefined) {
        Array.from(row.querySelectorAll('[data-option], [data-scale-value]')).some(option => {
          if (Number(option.getAttribute('data-scale-value')) !== score) return false
          option.classList.add('sel')
          return true
        })
      }
      rows.appendChild(row)
    })
    group.querySelectorAll('[data-survey-role="matrix-row"]').forEach(row => row.remove())
    rowMount.appendChild(rows)

    const nextAnswer = normalized.reduce((answers, item) => {
      const score = scoresByValue.get(item.value)
      if (score !== undefined) answers.push({ rowTitle: item.schemaLabel, score })
      return answers
    }, [])
    const exposure = _buildQuestionItemExposure(resolved, targetType, 'matrixRows', normalized, false)
    _storeQuestionItemExposure(question, signature, exposure)
    const answerChanged = JSON.stringify(previousAnswer || null) !== JSON.stringify(nextAnswer.length ? nextAnswer : null)
    if (answerChanged) {
      const saved = nextAnswer.length
        ? setLogicAnswer(resolved, nextAnswer)
        : (previousAnswer != null ? setLogicAnswer(resolved, null) : { ok: true })
      if (!saved.ok) {
        group.querySelectorAll('[data-survey-role="matrix-row"]').forEach(row => row.remove())
        for (let i = previousRows.length - 1; i >= 0; i--) {
          const previous = previousRows[i]
          const anchor = previous.nextSibling && previous.nextSibling.parentNode === previous.parent
            ? previous.nextSibling
            : null
          previous.parent.insertBefore(previous.row, anchor)
        }
        if (previousState) _questionItemStates.set(question, previousState)
        else _questionItemStates.delete(question)
        if (previousReferenceAttribute == null) question.removeAttribute('data-question-item-reference')
        else question.setAttribute('data-question-item-reference', previousReferenceAttribute)
        if (previousExposureAttribute == null) question.removeAttribute('data-question-item-exposure')
        else question.setAttribute('data-question-item-exposure', previousExposureAttribute)
        return _questionItemFailure('QUESTION_ITEM_ANSWER_UPDATE_FAILED', resolved, targetType, 'matrixRows')
      }
    }
    updateProgress()
    return { ok: true, questionUuid: resolved, questionType: targetType, slot: 'matrixRows', exposure: _cloneSerializable(exposure), answerChanged }
  }

  function _setGenericQuestionItems(question, resolved, targetType, normalized, signature) {
    const wrapper = question.querySelector('[data-survey-role="generic-container"]')
    if (!wrapper) return _questionItemFailure('GENERIC_ITEM_ADAPTER_MISSING', resolved, targetType, 'genericItems')
    const previousState = _questionItemStates.get(question)
    if (previousState && previousState.signature === signature) {
      return {
        ok: true, questionUuid: resolved, questionType: targetType, slot: 'genericItems',
        exposure: _cloneSerializable(previousState.exposure), answerChanged: false,
      }
    }
    const exposure = _buildQuestionItemExposure(resolved, targetType, 'genericItems', normalized, false)
    const previousAnswer = _questionAnswerValue(resolved)
    let responded = false
    let accepting = true
    let response = null
    const respond = function (value) {
      if (!accepting || responded) return false
      responded = true
      response = value
      return true
    }
    wrapper.dispatchEvent(new CustomEvent('survey:question-items', {
      detail: {
        items: _cloneSerializable(normalized),
        exposure: _cloneSerializable(exposure),
        previousAnswer: _cloneSerializable(previousAnswer),
        respond,
      },
      bubbles: false,
    }))
    accepting = false
    if (!responded || !response || !Object.prototype.hasOwnProperty.call(response, 'answer')) {
      return _questionItemFailure('GENERIC_ITEM_ADAPTER_MISSING', resolved, targetType, 'genericItems')
    }
    const nextAnswer = _cloneSerializable(response.answer)
    const answerChanged = JSON.stringify(previousAnswer || null) !== JSON.stringify(nextAnswer == null ? null : nextAnswer)
    if (answerChanged) {
      const saved = setLogicAnswer(resolved, nextAnswer)
      if (!saved.ok) return _questionItemFailure('GENERIC_ITEM_ADAPTER_REJECTED', resolved, targetType, 'genericItems')
    }
    _storeQuestionItemExposure(question, signature, exposure)
    updateProgress()
    return { ok: true, questionUuid: resolved, questionType: targetType, slot: 'genericItems', exposure: _cloneSerializable(exposure), answerChanged }
  }

  function setQuestionItems(uuid, items, config) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return _questionItemFailure('QUESTION_NOT_FOUND', resolved, 'UNKNOWN', 'auto')
    const questionType = Number(question.getAttribute('data-question-type'))
    const targetType = _questionTypeName(questionType)
    const opts = config && typeof config === 'object' ? config : {}
    const requestedSlot = opts.slot || 'auto'
    const slot = requestedSlot === 'auto'
      ? (questionType === 8 || questionType === 9 ? 'options'
        : questionType === 28 ? 'matrixRows'
          : questionType === 39 ? 'genericItems' : 'auto')
      : requestedSlot
    if (slot === 'auto'
      || (slot === 'options' && questionType !== 8 && questionType !== 9)
      || (slot === 'matrixRows' && questionType !== 28)
      || (slot === 'genericItems' && questionType !== 39)) {
      return _questionItemFailure('UNSUPPORTED_ITEM_SLOT', resolved, targetType, requestedSlot)
    }
    const catalogBacked = slot === 'options' || slot === 'matrixRows'
    let normalized = _normalizeQuestionOptions(items, catalogBacked)
    if (!normalized) return _questionItemFailure('INVALID_QUESTION_ITEMS', resolved, targetType, slot)
    if (catalogBacked) {
      const catalog = slot === 'options' ? _questionOptionCatalog(question) : _matrixRowCatalog(question)
      const catalogResult = _applyQuestionItemCatalog(normalized, catalog)
      if (!catalogResult.items) {
        return _questionItemFailure(
          catalogResult.collision ? 'SCHEMA_ITEM_COLLISION' : 'SCHEMA_ITEM_NOT_DECLARED',
          resolved,
          targetType,
          slot,
          catalogResult.collision
            ? { itemValue: catalogResult.itemValue, schemaValue: catalogResult.schemaValue }
            : { itemValue: catalogResult.itemValue },
        )
      }
      normalized = catalogResult.items
    }
    const signature = JSON.stringify({ slot, items: normalized, shuffle: opts.shuffle === true })

    if (slot === 'options') {
      const previousAnswer = _questionAnswerValue(resolved)
      const optionExposure = _setQuestionOptions(resolved, normalized, opts)
      if (!optionExposure) return _questionItemFailure('QUESTION_ITEM_UPDATE_FAILED', resolved, targetType, slot)
      const exposure = _buildQuestionItemExposure(
        resolved, targetType, slot,
        optionExposure.options || [],
        optionExposure.shuffled,
      )
      _storeQuestionItemExposure(question, signature, exposure)
      const nextAnswer = _questionAnswerValue(resolved)
      return {
        ok: true, questionUuid: resolved, questionType: targetType, slot,
        exposure: _cloneSerializable(exposure),
        answerChanged: JSON.stringify(previousAnswer || null) !== JSON.stringify(nextAnswer || null),
      }
    }
    if (slot === 'matrixRows') return _setMatrixQuestionItems(question, resolved, targetType, normalized, signature)
    return _setGenericQuestionItems(question, resolved, targetType, normalized, signature)
  }

  function getQuestionItemsExposure(uuid) {
    const resolved = _resolveUuid(uuid)
    const question = document.querySelector(`[data-question-uuid="${resolved}"]`)
    if (!question) return null
    const state = _questionItemStates.get(question)
    if (state) return _cloneSerializable(state.exposure)
    const raw = question.getAttribute('data-question-item-exposure')
    if (raw) {
      try { return JSON.parse(raw) } catch (e) {}
    }
    const optionExposure = _getQuestionOptionExposure(resolved)
    if (!optionExposure) return null
    return _buildQuestionItemExposure(
      resolved,
      _questionTypeName(Number(question.getAttribute('data-question-type'))),
      'options',
      optionExposure.options || [],
      optionExposure.shuffled,
    )
  }

  function _commandResult(ok, code, state, data, details) {
    const result = { ok: ok === true, code: String(code), state: String(state) }
    if (data !== undefined) result.data = data
    if (details !== undefined) result.details = details
    return result
  }

  async function submitSurvey() {
    try {
      let bridgeResult
      if (window.SurveyDataBridge && typeof window.SurveyDataBridge.submit === 'function') {
        bridgeResult = window.SurveyDataBridge.submit()
      } else {
        bridgeResult = sendToHost({ type: 'SUBMIT', answers: [], originSurveyAnswer: '' })
      }
      if (bridgeResult && typeof bridgeResult.then === 'function') {
        bridgeResult = await bridgeResult
      }
      if (bridgeResult && typeof bridgeResult === 'object' && bridgeResult.ok === false) {
        return _commandResult(false, bridgeResult.code || 'SUBMIT_REJECTED', 'editing', undefined, bridgeResult)
      }
      return _commandResult(true, 'SURVEY_SUBMITTED', 'submitted', { bridgeResult })
    } catch (error) {
      return _commandResult(false, 'SUBMIT_FAILED', 'editing', undefined, {
        message: error && error.message ? String(error.message) : String(error),
      })
    }
  }

  async function terminateSurvey(options) {
    const opts = options || {}
    try {
      const keep = new Set((opts.keepQuestionUuids || []).map(_resolveUuid))
      document.querySelectorAll('[data-question][data-question-uuid]').forEach(question => {
        const uuid = question.getAttribute('data-question-uuid')
        if (!keep.has(uuid)) setLogicQuestionVisibility(uuid, false)
      })
      const submission = await submitSurvey()
      if (!submission.ok) {
        return _commandResult(false, 'TERMINATION_SUBMIT_FAILED', submission.state, {
          keptQuestionUuids: Array.from(keep),
          submission,
        })
      }
      return _commandResult(true, 'SURVEY_TERMINATED', 'terminated', {
        keptQuestionUuids: Array.from(keep),
        submission,
      })
    } catch (error) {
      return _commandResult(false, 'TERMINATION_FAILED', 'editing', undefined, {
        message: error && error.message ? String(error.message) : String(error),
      })
    }
  }

  /* ===== Local draft resume (same device / localStorage: answers + page) ===== */
  let _localDraftEnabled = false
  let _localDraftRestoring = false
  let _localDraftSaveTimer = null
  let _localDraftCurrentPage = 0
  let _localDraftStorageKey = null
  let _localDraftEpoch = 0

  function _localDraftDefaultKey() {
    const firstQ = document.querySelector('[data-question-uuid]')
    const id = firstQ && firstQ.getAttribute('data-question-uuid')
    return 'wejot_draft_' + (id || window.location.pathname || 'survey')
  }

  function _localDraftRead() {
    if (!_localDraftStorageKey) return null
    try {
      const raw = localStorage.getItem(_localDraftStorageKey)
      if (!raw) return null
      const data = JSON.parse(raw)
      if (!data || typeof data !== 'object') return null
      return data
    } catch (e) {
      return null
    }
  }

  function _localDraftWrite(page, answers) {
    if (!_localDraftStorageKey || _localDraftRestoring) return
    try {
      localStorage.setItem(_localDraftStorageKey, JSON.stringify({
        v: 1,
        page: page == null ? _localDraftCurrentPage : page,
        answers: answers || [],
        updatedAt: Date.now(),
      }))
    } catch (e) {}
  }

  function _localDraftCollectAnswers() {
    if (window.SurveyDataBridge && typeof window.SurveyDataBridge.getAnswers === 'function') {
      return (window.SurveyDataBridge.getAnswers() || []).map(function (a) {
        return {
          questionUuid: a.questionUuid,
          questionType: Number(a.questionType),
          value: a.value,
        }
      })
    }
    return []
  }

  function _localDraftScheduleSave(page) {
    if (!_localDraftEnabled || _localDraftRestoring) return
    if (typeof page === 'number' && !isNaN(page)) _localDraftCurrentPage = page
    if (_localDraftSaveTimer) clearTimeout(_localDraftSaveTimer)
    const epoch = _localDraftEpoch
    _localDraftSaveTimer = setTimeout(function () {
      _localDraftSaveTimer = null
      // clearLocalDraft 会抬 epoch，作废提交前已调度、提交后才落地的写盘
      if (epoch !== _localDraftEpoch || _localDraftRestoring) return
      _localDraftWrite(_localDraftCurrentPage, _localDraftCollectAnswers())
    }, 120)
  }

  function _localDraftFindQuestion(uuid) {
    try {
      return document.querySelector('[data-question][data-question-uuid="' + uuid + '"]')
    } catch (e) {
      return null
    }
  }

  function _localDraftDispatchChange(el) {
    if (!el) return
    try {
      el.dispatchEvent(new Event('change', { bubbles: true }))
    } catch (e) {}
  }

  function _localDraftApplyScale(item, value) {
    const score = typeof value === 'number' ? value : Number(value)
    if (isNaN(score)) return
    const group = item.querySelector('[data-survey-role="scale-group"]')
    if (!group) return
    let matched = null
    group.querySelectorAll('[data-option], [data-scale-value]').forEach(function (opt) {
      const raw = opt.getAttribute('data-scale-value') || opt.textContent.trim()
      if (Number(raw) === score) matched = opt
    })
    if (!matched) return
    group.querySelectorAll('[data-option], [data-scale-value]').forEach(function (s) {
      s.classList.remove('sel')
    })
    matched.classList.add('sel')
    if (typeof window.saveAnswerLocal === 'function') {
      window.saveAnswerLocal(item.getAttribute('data-question-uuid'), 10, score)
    }
  }

  function _localDraftApplyMatrix(item, value) {
    const rows = Array.isArray(value) ? value : []
    rows.forEach(function (row) {
      if (!row || row.rowTitle == null) return
      const rowEl = item.querySelector('[data-survey-role="matrix-row"][data-matrix-row-label="' + row.rowTitle + '"]')
        || item.querySelector('[data-matrix-row-label="' + row.rowTitle + '"]')
      if (!rowEl) return
      let matched = null
      rowEl.querySelectorAll('[data-option], [data-scale-value]').forEach(function (opt) {
        const raw = opt.getAttribute('data-scale-value') || opt.textContent.trim()
        if (Number(raw) === Number(row.score)) matched = opt
      })
      if (!matched) return
      rowEl.querySelectorAll('[data-option], [data-scale-value]').forEach(function (s) {
        s.classList.remove('sel')
      })
      matched.classList.add('sel')
    })
    if (typeof window.saveAnswerLocal === 'function') {
      window.saveAnswerLocal(item.getAttribute('data-question-uuid'), 28, rows)
    }
  }

  function _localDraftApplyUpload(item, value) {
    const files = Array.isArray(value) ? value : []
    const fileInput = item.querySelector('input[type="file"]')
    if (fileInput && files.length) {
      const first = files[0]
      const url = typeof first === 'string' ? first : (first && (first.url || first.fileUrl))
      if (url) fileInput.dataset.uploadUrl = url
    }
    if (typeof window.saveAnswerLocal === 'function') {
      window.saveAnswerLocal(item.getAttribute('data-question-uuid'), 15, files)
    }
    updateUploadUI(item, files)
  }

  function _localDraftApplyGeneric(item, value) {
    try {
      item.dataset.customValue = typeof value === 'string' ? value : JSON.stringify(value)
    } catch (e) {
      item.dataset.customValue = String(value)
    }
    if (typeof window.SurveyApp !== 'undefined' && window.SurveyApp.setCustomValue) {
      try {
        window.SurveyApp.setCustomValue(item.getAttribute('data-question-uuid'), value)
      } catch (e) {}
    }
    if (typeof window.saveAnswerLocal === 'function') {
      window.saveAnswerLocal(item.getAttribute('data-question-uuid'), 39, value)
    }
  }

  function _localDraftApplyAnswer(entry) {
    if (!entry || !entry.questionUuid) return
    const item = _localDraftFindQuestion(entry.questionUuid)
    if (!item) return
    const type = Number(entry.questionType || item.getAttribute('data-question-type'))
    const value = entry.value

    if (typeof window.saveAnswerLocal === 'function' && window.saveAnswerLocal._lastSignatures) {
      delete window.saveAnswerLocal._lastSignatures[entry.questionUuid]
    }

    try {
      if (type === 1) {
        const text = typeof value === 'string' ? value : (value == null ? '' : String(value))
        const ta = item.querySelector('textarea, [data-input-type="text"]')
        if (ta) {
          if (ta.tagName === 'TEXTAREA' || ta.tagName === 'INPUT') ta.value = text
          else ta.textContent = text
        }
        if (typeof window.saveAnswerLocal === 'function') {
          window.saveAnswerLocal(entry.questionUuid, type, text)
        }
        return
      }
      if (type === 8) {
        const optVal = value && typeof value === 'object' ? value.optionValue : value
        if (!optVal) return
        let matched = null
        item.querySelectorAll('[data-option]').forEach(function (opt) {
          if (opt.getAttribute('data-option-value') === String(optVal)) matched = opt
        })
        if (!matched) return
        const radio = matched.querySelector('input[type="radio"]')
        if (value && typeof value === 'object' && value.otherText != null) {
          const otherInput = matched.querySelector('[data-other-input]')
          if (otherInput) otherInput.value = value.otherText
        }
        if (radio) {
          radio.checked = true
          _localDraftDispatchChange(radio)
        }
        if (typeof window.saveAnswerLocal === 'function') {
          window.saveAnswerLocal(entry.questionUuid, type, value)
        }
        return
      }
      if (type === 9) {
        const optVals = value && typeof value === 'object' && Array.isArray(value.optionValues)
          ? value.optionValues
          : (Array.isArray(value) ? value : [])
        const otherTexts = value && typeof value === 'object' && Array.isArray(value.otherTexts)
          ? value.otherTexts
          : []
        item.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
          cb.checked = false
        })
        item.querySelectorAll('[data-other-input]').forEach(function (input) {
          input.value = ''
        })
        optVals.forEach(function (ov, index) {
          item.querySelectorAll('[data-option]').forEach(function (opt) {
            if (opt.getAttribute('data-option-value') !== String(ov)) return
            const cb = opt.querySelector('input[type="checkbox"]')
            if (cb) cb.checked = true
            const otherInput = opt.querySelector('[data-other-input]')
            if (otherInput) otherInput.value = otherTexts[index] == null ? '' : String(otherTexts[index])
          })
        })
        if (typeof window.saveAnswerLocal === 'function') {
          window.saveAnswerLocal(entry.questionUuid, type, value)
        }
        return
      }
      if (type === 10) {
        _localDraftApplyScale(item, value)
        return
      }
      if (type === 28) {
        _localDraftApplyMatrix(item, value)
        return
      }
      if (type === 15) {
        _localDraftApplyUpload(item, value)
        return
      }
      if (type === 39) {
        _localDraftApplyGeneric(item, value)
      }
    } catch (e) {
      console.warn('[SurveyRuntime] local draft apply failed:', entry.questionUuid, e)
    }
  }

  function _localDraftUnlockRestoring() {
    if (!_localDraftRestoring) return
    _localDraftRestoring = false
    document.removeEventListener('pointerdown', _localDraftUnlockRestoring, true)
    document.removeEventListener('keydown', _localDraftUnlockRestoring, true)
  }

  function _localDraftArmUnlockOnGesture() {
    document.addEventListener('pointerdown', _localDraftUnlockRestoring, true)
    document.addEventListener('keydown', _localDraftUnlockRestoring, true)
  }

  function _localDraftWrapBridgeSubmit() {
    if (!window.SurveyDataBridge) return false
    if (window.SurveyDataBridge.__localDraftSubmitWrapped) return true
    if (typeof window.SurveyDataBridge.submit === 'function') {
      const origSubmit = window.SurveyDataBridge.submit.bind(window.SurveyDataBridge)
      window.SurveyDataBridge.submit = function () {
        clearLocalDraft()
        return origSubmit.apply(this, arguments)
      }
    }
    if (typeof window.SurveyDataBridge.submitAndStay === 'function') {
      const origStay = window.SurveyDataBridge.submitAndStay.bind(window.SurveyDataBridge)
      window.SurveyDataBridge.submitAndStay = function () {
        clearLocalDraft()
        return origStay.apply(this, arguments)
      }
    }
    window.SurveyDataBridge.__localDraftSubmitWrapped = true
    return true
  }

  function _localDraftRestore() {
    const draft = _localDraftRead()
    if (!draft) return

    _localDraftRestoring = true
    try {
      if (Array.isArray(draft.answers)) {
        draft.answers.forEach(_localDraftApplyAnswer)
      }
      if (window._surveyPagination && typeof window._surveyPagination.refresh === 'function') {
        window._surveyPagination.refresh()
      }
      const page = Number(draft.page)
      if (!isNaN(page) && window._surveyPagination && window._surveyPagination.show) {
        _localDraftCurrentPage = page
        window._surveyPagination.show(page)
      }
      updateProgress()
      _notifyLocalDraftRestored({
        answers: Array.isArray(draft.answers) ? draft.answers.slice() : [],
        page: _localDraftCurrentPage,
      })
    } finally {
      // 不设超时：等用户首次真实手势再允许 submitSurvey（程序回填 ≠ 交卷意图）
      _localDraftArmUnlockOnGesture()
    }
  }

  function _localDraftWaitReadyAndRestore() {
    let tries = 0
    const wait = setInterval(function () {
      tries += 1
      const ready = window._surveyPagination && window._surveyPagination.show
        && typeof window.saveAnswerLocal === 'function'
      if (ready || tries >= 40) {
        clearInterval(wait)
        if (ready) _localDraftRestore()
      }
    }, 50)
  }

  function _localDraftBindListeners() {
    if (document.__localDraftListenersBound) return
    document.__localDraftListenersBound = true
    document.addEventListener('surveyAnswerChanged', function () {
      _localDraftScheduleSave()
    })
    document.addEventListener('input', function (e) {
      const t = e.target
      if (!t || !t.closest) return
      if (!t.closest('[data-question]')) return
      if (t.tagName === 'TEXTAREA' || t.getAttribute('data-input-type') === 'text') {
        _localDraftScheduleSave()
      }
    })
  }

  function enableLocalDraftResume(opts) {
    opts = opts || {}
    if (_localDraftEnabled) return
    _localDraftEnabled = true
    _localDraftStorageKey = opts.storageKey || _localDraftDefaultKey()
    _localDraftBindListeners()
    _localDraftWrapBridgeSubmit()
    // 闭包内 show()/上一页下一页都会走到这里，才能记下断点页
    window.__surveyNotifyPageChange = function (pageIndex) {
      _localDraftScheduleSave(pageIndex)
    }
    if (!window.SurveyDataBridge || !window.SurveyDataBridge.__localDraftSubmitWrapped) {
      const subChk = setInterval(function () {
        if (_localDraftWrapBridgeSubmit()) clearInterval(subChk)
      }, 50)
      setTimeout(function () { clearInterval(subChk) }, 8000)
    }
    setTimeout(_localDraftWaitReadyAndRestore, 200)
  }

  function disableLocalDraftResume() {
    _localDraftEnabled = false
    _localDraftUnlockRestoring()
    if (window.__surveyNotifyPageChange) {
      try { delete window.__surveyNotifyPageChange } catch (e) {
        window.__surveyNotifyPageChange = undefined
      }
    }
    if (_localDraftSaveTimer) {
      clearTimeout(_localDraftSaveTimer)
      _localDraftSaveTimer = null
    }
  }

  function clearLocalDraft() {
    // 抬 epoch + 取消未写定时器：提交时作废任何已调度、尚未落地的草稿写回
    _localDraftEpoch += 1
    if (_localDraftSaveTimer) {
      clearTimeout(_localDraftSaveTimer)
      _localDraftSaveTimer = null
    }
    if (!_localDraftStorageKey) _localDraftStorageKey = _localDraftDefaultKey()
    try {
      localStorage.removeItem(_localDraftStorageKey)
      localStorage.removeItem(_logicAssignmentStorageKey())
      document.querySelectorAll('[data-option-reference][data-question-uuid]').forEach(question => {
        localStorage.removeItem(_questionOptionOrderKey(question.getAttribute('data-question-uuid')))
      })
    } catch (e) {}
  }

  function maybeEnableLocalDraftFromDefault() {
    if (window.SURVEY_LOCAL_DRAFT_DEFAULT === false) return
    enableLocalDraftResume()
  }

  window.SurveyRuntime = {
    registerUserLogic,
    setLogicQuestionVisibility,
    onLogicAnswerChange,
    getLogicAnswer,
    setLogicAnswer,
    setQuestionContent,
    setCheckboxOptionExclusivity,
    getSelectedQuestionItems,
    setQuestionItems,
    getQuestionItemsExposure,
    getLogicDiagnostics,
    onLocalDraftRestored,
    getStableRandomAssignment,
    submitSurvey,
    terminateSurvey,
    resolveUuid: _resolveUuid,
    enableLocalDraftResume,
    disableLocalDraftResume,
    clearLocalDraft,
  }
})()

// ===== 只读基座结束（SURVEY_UI_INFRA_END）— 下方为 LLM 可编辑区 =====

// ==================== 业务逻辑扩展区 BEGIN ====================
// 强制规则：只能在此 BEGIN 与 END 标记之间编写代码，区域外禁止插入任何内容。
// 本区使用 window.SurveyRuntime.registerUserLogic() 注册业务逻辑；registerUserLogic 只登记回调，
// 基座会在初始化完成且当前脚本执行栈退出后的 microtask（不支持时为 macrotask）中统一执行。
// 常量：文件顶部已注入 Qn_UUID / Qn_OPT_n / Qn_OTHER_OPTION_VALUE / resolveUuidByIndex，直接使用，严禁重复声明。
// 主入口：window.SurveyRuntime.onLogicAnswerChange(detail => { ... })
// 读取答案：window.SurveyRuntime.getLogicAnswer(uuid) 或 window.SurveyDataBridge.getAnswer(uuid)
// 逻辑赋值：window.SurveyRuntime.setLogicAnswer(uuid, value, {submitWhenHidden?})；传 null 清除
// 动态文案：window.SurveyRuntime.setQuestionContent(uuid, {title?, description?})；字段传 null 恢复初始文案，传空字符串清空
// 显隐控制：window.SurveyRuntime.setLogicQuestionVisibility(uuid, true/false)
// 多选项互斥：window.SurveyRuntime.setCheckboxOptionExclusivity(uuid, [exclusiveOptionValue])
// 动态题项：标准 catalog 子集可传 [{value}]；GENERIC 或自定义文案传 [{value, label, schemaLabel?, source?, meta?}]
// 题项暴露：window.SurveyRuntime.getQuestionItemsExposure(uuid)
// 已选规范化项：item.value 是跨题稳定身份；item.sourceValue 是当前题原始 optionValue；矩阵分值在 item.meta.score
// 逻辑诊断：window.SurveyRuntime.getLogicDiagnostics()（初始化异常只读查询）
// 稳定随机：window.SurveyRuntime.getStableRandomAssignment(key, variants)；同一次答题刷新/重算不变
// setLogicAnswer/setQuestionItems 的返回值必须检查 ok；失败时禁止继续执行依赖该动作的逻辑。
// setQuestionItems 必须显式传 slot（options/matrixRows/genericItems），并使用目标题 catalog 中的 value 或 schemaLabel。
// 防震荡：对驱动题答案取签名，签名未变直接 return
// 禁止：禁止 cloneNode 操作 .bs / .bp 导航按钮
// 禁止：不要监听 DOMContentLoaded，基座会在初始化后自动执行业务逻辑
// 同机断点续答：基座默认关闭（localStorage 存答案+断点页）。改 true 开启。仅同设备，非跨设备。
// 勿手写 sessionStorage 伪续答；勿依赖 survey:before-submit（基座不派发）。

// 同机断点续答开关（false = 关闭）。恢复后须落在断点页，非从头翻页。
const SURVEY_LOCAL_DRAFT_DEFAULT = false
window.SURVEY_LOCAL_DRAFT_DEFAULT = SURVEY_LOCAL_DRAFT_DEFAULT

window.SurveyRuntime.registerUserLogic(function() {
  'use strict';

  // [在此行下方编写业务逻辑代码]

})
// ==================== 业务逻辑扩展区 END ====================

/**

 * ============================================================================

 * PROJECT LIBRA // PWA CLIENT APPLICATION (PHASE 10)

 * Gemini-Style Multi-Chat, Real-Time Token Telemetry, Three.js Orb & Voice

 * ============================================================================

 */

(function () {

  'use strict';

  // Intercept all fetch requests to automatically bypass ngrok free browser interstitial

  const _origFetch = window.fetch;

  window.fetch = function (url, options = {}) {

    options = options || {};

    options.headers = options.headers || {};

    if (options.headers instanceof Headers) {

      options.headers.set('ngrok-skip-browser-warning', '69420');

    } else {

      options.headers['ngrok-skip-browser-warning'] = '69420';

    }

    return _origFetch(url, options);

  };

  // --------------------------------------------------------------------------

  // 1. STATE & GLOBAL CONFIGURATION

  // --------------------------------------------------------------------------

  let authToken = localStorage.getItem('libra_token') || '';

  let activeSessionId = localStorage.getItem('libra_active_session') || 'default';

  let activeSessionTitle = 'Main Chat';

  let isRecording = false;

  let mediaRecorder = null;

  let audioChunks = [];

  let sessionsList = [];

  // Parse token from URL if present

  const urlParams = new URLSearchParams(window.location.search);

  if (urlParams.has('token')) {

    authToken = urlParams.get('token');

    localStorage.setItem('libra_token', authToken);

    document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;

    try {

      const cleanUrl = window.location.pathname;

      window.history.replaceState({}, document.title, cleanUrl);

    } catch (e) {}

  } else if (authToken) {

    document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;

  }

  // --------------------------------------------------------------------------

  // AUDIO QUEUE PLAYER (GAPLESS REAL-TIME KOKORO-82M TTS SEQUENCER)

  // --------------------------------------------------------------------------

  class AudioQueuePlayer {

    constructor(audioEl = null) {

      this.queue = [];

      this.isPlaying = false;

      this.audio = audioEl || new Audio();

      this.audio.preload = 'auto';

      this.onStateChange = null;

      this.audio.onended = () => {

        this.playNext();

      };

      this.audio.onerror = (e) => {

        console.warn('[AudioQueuePlayer] Playback error on chunk:', e);

        this.playNext();

      };

    }

    enqueue(base64Wav) {

      if (!base64Wav) return;

      this.queue.push('data:audio/wav;base64,' + base64Wav);

      if (!this.isPlaying) {

        this.playNext();

      }

    }

    playNext() {

      if (this.queue.length === 0) {

        this.isPlaying = false;

        if (this.onStateChange) this.onStateChange(false);

        return;

      }

      this.isPlaying = true;

      if (this.onStateChange) this.onStateChange(true);

      const nextSrc = this.queue.shift();

      this.audio.src = nextSrc;

      this.audio.play().catch((err) => {

        console.warn('[AudioQueuePlayer] Autoplay blocked or interrupted:', err);

        this.playNext();

      });

    }

    stop() {

      try {

        this.audio.pause();

        this.audio.src = '';

      } catch (e) {}

      this.queue = [];

      this.isPlaying = false;

      if (this.onStateChange) this.onStateChange(false);

    }

  }

  function getAuthHeaders(extraHeaders = {}) {

    const headers = { ...extraHeaders };

    if (authToken) {

      headers['Authorization'] = 'Bearer ' + authToken;

    }

    return headers;

  }

  // --------------------------------------------------------------------------

  // 2. DOM ELEMENT REFERENCES

  // --------------------------------------------------------------------------

  const drawer = document.getElementById('drawer');

  const drawerBackdrop = document.getElementById('drawer-backdrop');

  const drawerToggleBtn = document.getElementById('drawer-toggle-btn');

  const closeDrawerBtn = document.getElementById('close-drawer-btn');

  const newChatBtn = document.getElementById('new-chat-btn');

  const headerNewChatBtn = document.getElementById('header-new-chat-btn');

  const sessionListContainer = document.getElementById('session-list');

  const activeThreadTitleEl = document.getElementById('active-thread-title');

  const scrollToBottomBtn = document.getElementById('scroll-to-bottom-btn');

  let userIsScrolledUp = false;

  const deleteModal = document.getElementById('delete-modal');

  const closeDeleteModalBtn = document.getElementById('close-delete-modal');

  const cancelDeleteBtn = document.getElementById('cancel-delete-btn');

  const confirmDeleteBtn = document.getElementById('confirm-delete-btn');

  const deleteModalPrompt = document.getElementById('delete-modal-prompt');

  const renameModal = document.getElementById('rename-modal');

  const closeRenameModalBtn = document.getElementById('close-rename-modal');

  const cancelRenameBtn = document.getElementById('cancel-rename-btn');

  const confirmRenameBtn = document.getElementById('confirm-rename-btn');

  const renameInput = document.getElementById('rename-input');

  let pendingDeleteSessionId = null;

  let pendingRenameSessionId = null;

  const tokenHudBtn = document.getElementById('token-hud-btn');

  const tokenHudText = document.getElementById('token-hud-text');

  const tokenModal = document.getElementById('token-modal');

  const closeTokenModalBtn = document.getElementById('close-token-modal');

  const vitalsText = document.getElementById('vitals-text');

  const orbSection = document.getElementById('orb-section');

  const orbCanvas = document.getElementById('orb-canvas');

  const orbStatus = document.getElementById('orb-status');

  const chatContainer = document.getElementById('chat-container');

  const promptInput = document.getElementById('prompt-input');

  const sendBtn = document.getElementById('send-btn');

  const micBtn = document.getElementById('mic-btn');

  const attachBtn = document.getElementById('attach-btn');

  const fileInput = document.getElementById('file-input');

  const attachmentTray = document.getElementById('attachment-tray');

  const attachmentThumb = document.getElementById('attachment-thumb');

  const attachmentName = document.getElementById('attachment-name');

  const attachmentStatus = document.getElementById('attachment-status');

  const removeAttachmentBtn = document.getElementById('remove-attachment-btn');

  const imageLightbox = document.getElementById('image-lightbox');

  const lightboxImg = document.getElementById('lightbox-img');

  const closeLightboxBtn = document.getElementById('close-lightbox-btn');

  const remoteAudio = document.getElementById('remote-audio');

  const stopVoiceBtn = document.getElementById('stop-voice-btn');

  const audioPlayer = new AudioQueuePlayer(remoteAudio);

  audioPlayer.onStateChange = (playing) => {

    if (stopVoiceBtn) {

      stopVoiceBtn.style.display = playing ? 'inline-flex' : 'none';

    }

    if (playing) {

      setOrbState('speaking', 'SPEAKING // KOKORO-82M');

    } else {

      setOrbState('idle', 'STANDBY // READY');

    }

  };

  if (stopVoiceBtn) {

    stopVoiceBtn.addEventListener('click', (e) => {

      e.preventDefault();

      e.stopPropagation();

      audioPlayer.stop();

    });

  }

  let pendingAttachment = null;

  const authModal = document.getElementById('auth-modal');

  const tokenInput = document.getElementById('token-input');

  const saveTokenBtn = document.getElementById('save-token-btn');

  // Token Modal Card Elements

  const tokLastSpeed = document.getElementById('tok-last-speed');

  const tokLastCounts = document.getElementById('tok-last-counts');

  const tokLastModel = document.getElementById('tok-last-model');

  const tokSessTotal = document.getElementById('tok-sess-total');

  const tokSessBreakdown = document.getElementById('tok-sess-breakdown');

  const tokSessTurns = document.getElementById('tok-sess-turns');

  const tokTodayTotal = document.getElementById('tok-today-total');

  const tokTodayBreakdown = document.getElementById('tok-today-breakdown');

  const tokSavedTotal = document.getElementById('tok-saved-total');

  const tokSavedDesc = document.getElementById('tok-saved-desc');

  // --------------------------------------------------------------------------

  // 3. PWA SERVICE WORKER REGISTRATION

  // --------------------------------------------------------------------------

  if ('serviceWorker' in navigator) {

    window.addEventListener('load', () => {

      navigator.serviceWorker.register('/sw.js').catch((err) => {

        console.warn('[PWA] Service worker registration notice:', err);

      });

    });

  }

  // --------------------------------------------------------------------------

  // 4. THREE.JS 3D CYBERNETIC ORB VISUALIZATION

  // --------------------------------------------------------------------------

  let orbScene, orbCamera, orbRenderer, pointCloud, hudRing, coreMesh;

  const particleCount = 220;

  const baseRadius = 5.4;

  const baseDirections = [];

  let speedMultiplier = 1.0;

  let targetSpeedMultiplier = 1.0;

  let currentOrbState = 'idle';

  const STATE_COLORS = {

    idle: new THREE.Color(0x38bdf8),

    listening: new THREE.Color(0xfbbf24),

    thinking: new THREE.Color(0x818cf8),

    speaking: new THREE.Color(0x38bdf8),

    error: new THREE.Color(0xf87171)

  };

  function initOrb() {

    if (!orbCanvas || !orbSection) return;

    orbScene = new THREE.Scene();

    orbCamera = new THREE.PerspectiveCamera(55, orbSection.clientWidth / orbSection.clientHeight, 0.1, 1000);

    orbCamera.position.z = 15;

    orbRenderer = new THREE.WebGLRenderer({ canvas: orbCanvas, alpha: true, antialias: true });

    orbRenderer.setSize(orbSection.clientWidth, orbSection.clientHeight);

    orbRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    // Particle Cloud

    const positions = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {

      const phi = Math.acos(-1 + (2 * i) / particleCount);

      const theta = Math.sqrt(particleCount * Math.PI) * phi;

      const x = Math.cos(theta) * Math.sin(phi);

      const y = Math.sin(theta) * Math.sin(phi);

      const z = Math.cos(phi);

      positions[i * 3] = x * baseRadius;

      positions[i * 3 + 1] = y * baseRadius;

      positions[i * 3 + 2] = z * baseRadius;

      baseDirections.push(new THREE.Vector3(x, y, z));

    }

    const pGeo = new THREE.BufferGeometry();

    pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const pMat = new THREE.PointsMaterial({

      color: 0x00f2fe,

      size: 0.20,

      transparent: true,

      opacity: 0.85

    });

    pointCloud = new THREE.Points(pGeo, pMat);

    orbScene.add(pointCloud);

    // Orbital Ring

    const ringGeo = new THREE.RingGeometry(6.8, 6.85, 64);

    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00ffff, side: THREE.DoubleSide, transparent: true, opacity: 0.25 });

    hudRing = new THREE.Mesh(ringGeo, ringMat);

    hudRing.rotation.x = Math.PI / 3;

    orbScene.add(hudRing);

    // Core Wireframe

    const coreGeo = new THREE.IcosahedronGeometry(2.0, 2);

    const coreMat = new THREE.MeshBasicMaterial({ color: 0x0077aa, wireframe: true, transparent: true, opacity: 0.35 });

    coreMesh = new THREE.Mesh(coreGeo, coreMat);

    orbScene.add(coreMesh);

    window.addEventListener('resize', onOrbResize);

    animateOrb();

  }

  function onOrbResize() {

    if (!orbCamera || !orbRenderer || !orbSection) return;

    orbCamera.aspect = orbSection.clientWidth / orbSection.clientHeight;

    orbCamera.updateProjectionMatrix();

    orbRenderer.setSize(orbSection.clientWidth, orbSection.clientHeight);

  }

  function setOrbState(state, label) {

    currentOrbState = state;

    const col = STATE_COLORS[state] || STATE_COLORS.idle;

    if (pointCloud && pointCloud.material) pointCloud.material.color.copy(col);

    if (hudRing && hudRing.material) hudRing.material.color.copy(col);

    if (coreMesh && coreMesh.material) coreMesh.material.color.copy(col);

    if (state === 'speaking') targetSpeedMultiplier = 2.4;

    else if (state === 'thinking') targetSpeedMultiplier = 1.9;

    else if (state === 'listening') targetSpeedMultiplier = 1.4;

    else targetSpeedMultiplier = 1.0;

    if (orbStatus) {

      orbStatus.textContent = label || (state.toUpperCase() + ' // READY');

    }

  }

  let orbClock = new THREE.Clock();

  function animateOrb() {

    requestAnimationFrame(animateOrb);

    const delta = orbClock.getDelta();

    const time = orbClock.getElapsedTime();

    speedMultiplier += (targetSpeedMultiplier - speedMultiplier) * 0.08;

    if (pointCloud) {

      pointCloud.rotation.y += delta * 0.3 * speedMultiplier;

      pointCloud.rotation.x += delta * 0.1 * speedMultiplier;

    }

    if (hudRing) hudRing.rotation.z -= delta * 0.2 * speedMultiplier;

    if (coreMesh) coreMesh.rotation.y -= delta * 0.4 * speedMultiplier;

    if (pointCloud && pointCloud.geometry) {

      const posArr = pointCloud.geometry.attributes.position.array;

      const pulse = (currentOrbState === 'speaking' || currentOrbState === 'listening')

        ? (Math.sin(time * 8.0) * 0.5)

        : (Math.sin(time * 2.0) * 0.15);

      for (let i = 0; i < particleCount; i++) {

        const dir = baseDirections[i];

        const r = baseRadius + pulse;

        posArr[i * 3]     = dir.x * r;

        posArr[i * 3 + 1] = dir.y * r;

        posArr[i * 3 + 2] = dir.z * r;

      }

      pointCloud.geometry.attributes.position.needsUpdate = true;

    }

    if (orbRenderer && orbScene && orbCamera) {

      orbRenderer.render(orbScene, orbCamera);

    }

  }

  // Smart user scroll tracking & orb state synchronization

  if (chatContainer) {

    chatContainer.addEventListener('scroll', () => {

      // Determine if user has scrolled up away from latest content

      const distanceFromBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;

      userIsScrolledUp = distanceFromBottom > 80;

      if (scrollToBottomBtn) {

        scrollToBottomBtn.style.display = userIsScrolledUp ? 'flex' : 'none';

      }

      // Orb collapse behavior: if active chat (>1 msg), keep collapsed so messages don't jump/shift

      if (orbSection) {

        const msgCount = chatContainer.querySelectorAll('.msg').length;

        if (msgCount > 1 || chatContainer.scrollTop > 30) {

          if (!orbSection.classList.contains('collapsed')) {

            orbSection.classList.add('collapsed');

            setTimeout(onOrbResize, 350);

          }

        } else if (msgCount <= 1 && chatContainer.scrollTop <= 10) {

          if (orbSection.classList.contains('collapsed')) {

            orbSection.classList.remove('collapsed');

            setTimeout(onOrbResize, 350);

          }

        }

      }

    }, { passive: true });

  }

  if (scrollToBottomBtn && chatContainer) {

    scrollToBottomBtn.addEventListener('click', () => {

      userIsScrolledUp = false;

      chatContainer.scrollTop = chatContainer.scrollHeight;

      scrollToBottomBtn.style.display = 'none';

    });

  }

  // --------------------------------------------------------------------------

  // 5. MARKDOWN & CODE BLOCK FORMATTER

  // --------------------------------------------------------------------------

  function escapeHtml(str) {

    if (!str) return '';

    return str

      .replace(/&/g, '&amp;')

      .replace(/</g, '&lt;')

      .replace(/>/g, '&gt;')

      .replace(/"/g, '&quot;')

      .replace(/'/g, '&#039;');

  }

  function formatMarkdown(text) {

    if (!text) return '';

    // Extract fenced code blocks ```lang\ncode\n```

    const codeBlocks = [];

    let processed = text.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {

      const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;

      codeBlocks.push({ lang: lang || 'code', code: code.trim() });

      return placeholder;

    });

    // Escape raw HTML in prose

    processed = escapeHtml(processed);

    // Format bold **text**

    processed = processed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Format italics *text*

    processed = processed.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Format inline code `code`

    processed = processed.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Format bullet lists

    processed = processed.replace(/^\s*[-*]\s+(.*)$/gm, '<li>$1</li>');

    processed = processed.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Format paragraph breaks

    processed = processed.replace(/\n\n+/g, '</p><p>');

    processed = processed.replace(/\n/g, '<br>');

    processed = `<p>${processed}</p>`;

    // Restore fenced code blocks with Prism syntax highlighting & Copy Button

    codeBlocks.forEach((block, idx) => {

      let rawLang = (block.lang || 'text').toLowerCase().trim();

      if (rawLang === 'py') rawLang = 'python';

      if (rawLang === 'js') rawLang = 'javascript';

      if (rawLang === 'ts') rawLang = 'typescript';

      if (rawLang === 'sh' || rawLang === 'shell' || rawLang === 'zsh') rawLang = 'bash';

      if (rawLang === 'yml') rawLang = 'yaml';

      if (rawLang === 'md') rawLang = 'markdown';

      let highlightedCode = '';

      if (window.Prism && Prism.languages && Prism.languages[rawLang]) {

        try {

          highlightedCode = Prism.highlight(block.code, Prism.languages[rawLang], rawLang);

        } catch (e) {

          highlightedCode = escapeHtml(block.code);

        }

      } else {

        highlightedCode = escapeHtml(block.code);

      }

      const isPreviewable = ['html', 'svg', 'xml'].includes(rawLang);

      const previewBtnHtml = isPreviewable

        ? `<button class="preview-code-btn" data-code="${encodeURIComponent(block.code)}">▶ Preview</button>`

        : '';

      const replacement = `

        <div class="code-block-wrap">

          <div class="code-block-header">

            <span class="code-lang-badge"><span class="code-lang-dot"></span>${escapeHtml(rawLang)}</span>

            <div class="code-actions-group">

              ${previewBtnHtml}

              <button class="copy-code-btn" data-code="${encodeURIComponent(block.code)}" title="Copy full code snippet">

                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">

                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>

                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>

                </svg>

                <span>Copy</span>

              </button>

            </div>

          </div>

          <pre class="language-${rawLang}"><code class="language-${rawLang}">${highlightedCode}</code></pre>

        </div>

      `;

      processed = processed.replace(`__CODE_BLOCK_${idx}__`, replacement);

    });

    return processed;

  }

  // Delegate copy button clicks with smooth animation & feedback

  document.addEventListener('click', (e) => {

    const btn = e.target.closest('.copy-code-btn');

    if (btn) {

      const encodedCode = btn.getAttribute('data-code');

      if (encodedCode) {

        const rawCode = decodeURIComponent(encodedCode);

        navigator.clipboard.writeText(rawCode).then(() => {

          btn.classList.add('copied');

          btn.innerHTML = `

            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">

              <polyline points="20 6 9 17 4 12"></polyline>

            </svg>

            <span>Copied!</span>

          `;

          setTimeout(() => {

            btn.classList.remove('copied');

            btn.innerHTML = `

              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">

                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>

                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>

              </svg>

              <span>Copy</span>

            `;

          }, 2000);

        }).catch(err => {

          console.warn('Clipboard write failed:', err);

        });

      }

    }

  });

  // --------------------------------------------------------------------------

  // 6. CHAT RENDERING & LIGHTBOX

  // --------------------------------------------------------------------------

  function openLightbox(src) {

    if (imageLightbox && lightboxImg && src) {

      lightboxImg.src = src;

      imageLightbox.style.display = 'flex';

    }

  }

  function closeLightbox() {

    if (imageLightbox) {

      imageLightbox.style.display = 'none';

      if (lightboxImg) lightboxImg.src = '';

    }

  }

  if (closeLightboxBtn) closeLightboxBtn.addEventListener('click', closeLightbox);

  if (imageLightbox) {

    imageLightbox.addEventListener('click', (e) => {

      if (e.target === imageLightbox) closeLightbox();

    });

  }


  // --------------------------------------------------------------------------
  // AI THOUGHT PROCESS & MODEL REASONING ACCORDION COMPONENT (PHASE 12.6)
  // Antigravity / Cursor Sleek Cybernetic Thought Tree
  // --------------------------------------------------------------------------
  function formatDuration(sec) {
    if (!sec || sec < 1) return '1s';
    if (sec < 60) return `${Math.max(1, Math.round(sec))}s`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }

  function getThoughtSummary(steps, defaultText) {
    if (!steps || steps.length === 0) return defaultText || 'Analyzed context and synthesized response';
    const hasComputerUse = steps.some(s => s.action === 'click' || s.action === 'press' || s.action === 'type' || (s.title && s.title.includes('COMPUTER_USE')));
    if (hasComputerUse) return 'Automated browser, executed steps, completed workflow';
    const hasWebSearch = steps.some(s => s.action === 'web_search' || (s.title && s.title.toLowerCase().includes('web')));
    if (hasWebSearch) return 'Researched live web, verified sources, synthesized response';
    const hasCode = steps.some(s => s.action === 'run_code' || s.action === 'git_ops' || (s.title && s.title.toLowerCase().includes('file')));
    if (hasCode) return 'Explored files, ran commands, edited files';
    return defaultText || 'Analyzed memory context, queried neural model, synthesized response';
  }

  function formatThoughtReasoning(text) {
    if (!text) return '';
    const escaped = escapeHtml(text);
    return escaped.replace(/`([^`]+)`/g, '<span class="thought-code-pill">$1</span>');
  }

  function renderThoughtStepItemHtml(s, idx) {
    const isRetry = s.status === 'retry' || s.action === 'retry' || (s.title && s.title.toLowerCase().includes('error')) || (s.thought && s.thought.includes('attempt'));
    const isCorrected = s.status === 'corrected';
    const action = (s.action || '').toLowerCase();

    let headerText = '';
    if (isRetry) {
      headerText = s.title || s.thought || `Model error (attempt 1/3)`;
    } else if (action === 'click') {
      const coordStr = (s.x !== undefined && s.y !== undefined) ? ` (${s.x}, ${s.y})` : '';
      headerText = `Ran click${coordStr}`;
    } else if (action === 'press') {
      headerText = `Ran press key (${s.key || 'hotkey'})`;
    } else if (action === 'type') {
      headerText = `Ran type ('${s.text || ''}')`;
    } else if (action === 'done') {
      headerText = `Completed task`;
    } else if (s.title) {
      headerText = s.title;
    } else {
      headerText = `Step ${s.step || (idx + 1)}`;
    }

    const detailText = s.detail || s.thought || '';

    // Claude / Minimalist clean formatting: avoid raw JSON debugging dumps
    let paramHtml = '';
    if (action === 'click' || action === 'press' || action === 'type' || action === 'run_code') {
      const paramList = [];
      if (s.x !== undefined && s.y !== undefined) paramList.push(`coords: [${s.x}, ${s.y}]`);
      if (s.key) paramList.push(`key: "${s.key}"`);
      if (s.text) paramList.push(`text: "${s.text}"`);
      if (paramList.length > 0) {
        paramHtml = `<div class="thought-action-params">${escapeHtml(paramList.join(' • '))}</div>`;
      }
    }

    return `
      <div class="thought-action-row ${isRetry ? 'thought-retry-row' : ''} ${isCorrected ? 'thought-corrected-row' : ''}">
        <button class="thought-action-btn" type="button" aria-expanded="false" title="Click to inspect action details">
          <span class="thought-action-label">${escapeHtml(headerText)}</span>
          <span class="thought-action-chevron">&gt;</span>
        </button>
        <div class="thought-action-pane" style="display: none;">
          ${detailText ? `<div class="thought-action-rationale">${formatThoughtReasoning(detailText)}</div>` : ''}
          ${paramHtml}
        </div>
      </div>
    `;
  }

  function _wireActionBtn(btn) {
    if (!btn || btn.hasAttribute('data-wired')) return;
    btn.setAttribute('data-wired', 'true');
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = btn.closest('.thought-action-row');
      if (!row) return;
      const isOpen = row.classList.toggle('open');
      btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      const ch = btn.querySelector('.thought-action-chevron');
      if (ch) ch.textContent = isOpen ? '▾' : '>';
      const pane = row.querySelector('.thought-action-pane');
      if (pane) pane.style.display = isOpen ? 'block' : 'none';
    });
  }

  function _wireThoughtAccordionEvents(acc) {
    const topHeader = acc.querySelector('.thought-top-header');
    const body = acc.querySelector('.thought-body');
    if (topHeader && body) {
      topHeader.addEventListener('click', (e) => {
        e.stopPropagation();
        body.classList.toggle('collapsed');
      });
    }

    const subHeader = acc.querySelector('.thought-sub-header');
    const subSection = acc.querySelector('.thought-sub-section');
    if (subHeader && subSection) {
      subHeader.addEventListener('click', (e) => {
        e.stopPropagation();
        subSection.classList.toggle('collapsed');
      });
    }

    acc.querySelectorAll('.thought-action-btn').forEach(_wireActionBtn);
  }

  function createThoughtAccordion(steps, initialLabel, isStreaming = false, reasoningText = '', elapsedSec = 8) {
    const acc = document.createElement('div');
    acc.className = 'thought-accordion' + (isStreaming ? ' streaming' : '');

    const durationText = initialLabel || (isStreaming ? 'Thinking... 0s ▾' : `Thought for ${formatDuration(elapsedSec)} ▾`);
    const stepsHtml = (steps && steps.length > 0) ? steps.map(renderThoughtStepItemHtml).join('') : '';

    let reasoning = reasoningText;
    if (!reasoning && steps && steps.length > 0) {
      const firstWithThought = steps.find(s => s.thought && !s.thought.startsWith('Model error') && !s.thought.startsWith('Chrome is visible'));
      if (firstWithThought) {
        reasoning = firstWithThought.thought;
      }
    }

    acc.innerHTML = `
      <div class="thought-top-header" title="Click to collapse / expand thought process">
        <button class="thought-duration-btn" type="button" aria-expanded="${isStreaming ? 'true' : 'false'}">
          ${isStreaming ? '<span class="thought-pulse-dot"></span>' : ''}
          <span class="thought-duration-label">${escapeHtml(durationText)}</span>
        </button>
      </div>
      <div class="thought-body ${isStreaming ? '' : 'collapsed'}">
        <div class="thought-sub-section thought-cot-box" style="${reasoning ? '' : 'display: none;'}">
          <div class="thought-cot-text">${formatThoughtReasoning(reasoning || '')}</div>
        </div>
        <div class="thought-actions-list">${stepsHtml}</div>
      </div>
    `;

    _wireThoughtAccordionEvents(acc);
    return acc;
  }

  function appendLiveStepToAccordion(acc, stepData) {
    if (!acc || !stepData) return;
    const list = acc.querySelector('.thought-actions-list');
    if (!list) return;

    if (stepData.thought && !stepData.action && !stepData.title) {
      updateThoughtAccordionReasoning(acc, stepData.thought, true);
    } else {
      const rowWrapper = document.createElement('div');
      rowWrapper.innerHTML = renderThoughtStepItemHtml(stepData, list.children.length);
      const newRow = rowWrapper.firstElementChild;
      if (newRow) {
        list.appendChild(newRow);
        const btn = newRow.querySelector('.thought-action-btn');
        if (btn) _wireActionBtn(btn);
      }
    }

    if (stepData.thought && !acc._hasReasoning && (stepData.action || stepData.title)) {
      updateThoughtAccordionReasoning(acc, stepData.thought, false);
      acc._hasReasoning = true;
    }
  }

  function updateThoughtAccordionReasoning(acc, reasoningText, append = false) {
    if (!acc || !reasoningText) return;
    const subSec = acc.querySelector('.thought-sub-section');
    const cotText = acc.querySelector('.thought-cot-text');
    if (subSec && cotText) {
      subSec.style.display = 'block';
      subSec.classList.remove('collapsed');
      if (append) {
        acc._cotReasoning = (acc._cotReasoning || '') + reasoningText;
      } else {
        acc._cotReasoning = reasoningText;
      }
      cotText.innerHTML = formatThoughtReasoning(acc._cotReasoning);
    }
  }

  function finalizeThoughtAccordion(acc, steps, t0_stream) {
    if (!acc || acc._isFinalized) return;
    acc._isFinalized = true;
    acc.classList.remove('streaming');
    if (acc._timerInterval) {
      clearInterval(acc._timerInterval);
      acc._timerInterval = null;
    }
    const elapsedSec = (t0_stream && typeof t0_stream === 'number')
      ? Math.max(1, ((performance.now() - t0_stream) / 1000))
      : (acc._streamElapsedSec || 6);
    const durLabel = acc.querySelector('.thought-duration-label');
    const pulseDot = acc.querySelector('.thought-pulse-dot');
    if (pulseDot) pulseDot.remove();
    if (durLabel) {
      durLabel.textContent = `Thought for ${formatDuration(elapsedSec)} ▾`;
    }

    // Automatically collapse thought body when answer starts (Claude style)
    const body = acc.querySelector('.thought-body');
    if (body) {
      body.classList.add('collapsed');
    }

    if (steps && Array.isArray(steps) && steps.length > 0) {
      const list = acc.querySelector('.thought-actions-list');
      if (list && list.children.length === 0) {
        list.innerHTML = steps.map(renderThoughtStepItemHtml).join('');
        list.querySelectorAll('.thought-action-btn').forEach(_wireActionBtn);
      }
    }
  }

  function appendMessage(text, isUser, meta = {}) {

    const hero = document.getElementById('empty-chat-hero');

    if (hero) hero.remove();

    const msgDiv = document.createElement('div');

    msgDiv.className = 'msg ' + (isUser ? 'msg-user' : 'msg-libra');

    const contentDiv = document.createElement('div');

    contentDiv.className = 'msg-content';

    // 1. Render attached file (Image or Document)

    if (meta.attached_file) {

      const attachDiv = document.createElement('div');

      attachDiv.className = 'msg-attachment-wrap';

      if (meta.attached_file.file_type === 'image') {

        const imgEl = document.createElement('img');

        imgEl.className = 'msg-img-preview';

        imgEl.src = meta.attached_file.preview_url || meta.attached_file.dataUrl;

        imgEl.alt = meta.attached_file.filename || 'Uploaded image';

        imgEl.title = 'Click to enlarge';

        imgEl.addEventListener('click', () => openLightbox(imgEl.src));

        attachDiv.appendChild(imgEl);

      } else {

        const docChip = document.createElement('div');

        docChip.className = 'msg-doc-chip';

        docChip.innerHTML = `

          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>

            <polyline points="14 2 14 8 20 8"/>

            <line x1="16" y1="13" x2="8" y2="13"/>

            <line x1="16" y1="17" x2="8" y2="17"/>

            <polyline points="10 9 9 9 8 9"/>

          </svg>

          <span>${escapeHtml(meta.attached_file.filename || 'Document')}</span>

        `;

        attachDiv.appendChild(docChip);

      }

      contentDiv.appendChild(attachDiv);

    }

    // 2. Render text / markdown content
    let visibleText = text;
    let reasoningText = '';
    if (!isUser && text) {
      const thinkMatch = text.match(/<think>([\s\S]*?)(?:<\/think>|$)/i);
      if (thinkMatch) {
        reasoningText = thinkMatch[1].trim();
        visibleText = text.replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, '').trim();
      }

      const steps = (meta.thought_steps && meta.thought_steps.length > 0) ? meta.thought_steps : [
        { step: 1, title: 'Intent & Scope Analysis', detail: 'Analyzed query context and loaded active conversation memory.' },
        { step: 2, title: 'AI Model Allocation', detail: 'Allocated ' + ((meta.token_metrics && meta.token_metrics.model) || 'qwen3:8b') + ' on NVIDIA GeForce RTX 5060 Ti.' },
        { step: 3, title: 'Neural Synthesis', detail: 'Synthesized response in ' + (meta.latency_ms ? meta.latency_ms + 'ms' : '0.8s') + '.' }
      ];

      const elapsedSec = meta.latency_ms ? (meta.latency_ms / 1000) : 8;
      const thoughtAcc = createThoughtAccordion(
        steps,
        `Worked for ${formatDuration(elapsedSec)} ▾`,
        false,
        reasoningText,
        elapsedSec
      );
      contentDiv.appendChild(thoughtAcc);
    }

    const textNode = document.createElement('div');
    if (isUser) {
      textNode.textContent = text;
    } else {
      textNode.innerHTML = formatMarkdown(visibleText);
    }
    contentDiv.appendChild(textNode);

    // 3. Render generated visual plot (e.g. from DataScienceAgent or Image generation)

    if (meta.generated_image_url) {

      const genImg = document.createElement('img');

      genImg.className = 'msg-generated-plot';

      genImg.src = meta.generated_image_url;

      genImg.alt = 'Visual output';

      genImg.title = 'Click to enlarge';

      genImg.addEventListener('click', () => openLightbox(genImg.src));

      contentDiv.appendChild(genImg);

    }

    msgDiv.appendChild(contentDiv);

    if (isUser) {

      const userMeta = document.createElement('div');

      userMeta.className = 'msg-meta user-msg-meta';

      const promptTokCount = meta.prompt_tokens || Math.max(1, Math.round((text || '').length / 4));

      const tokBadge = document.createElement('span');

      tokBadge.className = 'token-badge user-token-badge';

      tokBadge.textContent = '⚡ Prompt: ' + promptTokCount + ' tok';

      tokBadge.title = 'Prompt: ' + (text || '').length + ' characters (~' + promptTokCount + ' tokens)';

      userMeta.appendChild(tokBadge);

      msgDiv.appendChild(userMeta);

    } else {

      const metaDiv = document.createElement('div');

      metaDiv.className = 'msg-meta';

      if (meta.action) {

        const badge = document.createElement('span');

        badge.className = 'tool-badge';

        badge.textContent = meta.action;

        metaDiv.appendChild(badge);

      }

      if (meta.latency_ms) {

        const lat = document.createElement('span');

        lat.textContent = meta.latency_ms + 'ms';

        metaDiv.appendChild(lat);

      }

      if (meta.token_metrics && (meta.token_metrics.eval_count || meta.token_metrics.output_tokens || meta.token_metrics.input_tokens || meta.token_metrics.prompt_eval_count || meta.token_metrics.turn_in || meta.token_metrics.turn_out)) {

        const tok = document.createElement("span");

        tok.className = "token-badge";

        const inTok = meta.token_metrics.prompt_eval_count || meta.token_metrics.input_tokens || meta.token_metrics.turn_in || 0;

        const outTok = meta.token_metrics.eval_count || meta.token_metrics.output_tokens || meta.token_metrics.turn_out || 0;

        const tokPerSec = meta.token_metrics.tokens_per_sec || meta.token_metrics.tok_per_sec;

        const speedStr = tokPerSec ? " • " + tokPerSec.toFixed(1) + " tok/s" : "";

        if (inTok > 0 && outTok > 0) {

          tok.textContent = "⚡ Prompt: " + inTok + " tok • Reply: " + outTok + " tok" + speedStr;

          tok.title = "Prompt Tokens: " + inTok + " | Response Tokens: " + outTok + " | Total: " + (inTok + outTok);

        } else if (inTok > 0) {

          tok.textContent = "⚡ Prompt: " + inTok + " tok";

        } else {

          tok.textContent = tokPerSec ? "⚡ Reply: " + outTok + " tok" + speedStr : "⚡ " + outTok + " tok";

        }

        metaDiv.appendChild(tok);

      } else if (meta.token_metrics && meta.token_metrics.fast_path) {

        const tok = document.createElement('span');

        tok.className = 'token-badge';

        tok.textContent = '⚡ FAST-PATH (0 TOK)';

        metaDiv.appendChild(tok);

      }

      if (meta.audio_base64 && remoteAudio) {

        const playBtn = document.createElement('button');

        playBtn.className = 'replay-audio-btn';

        playBtn.title = 'Replay Kokoro TTS Voice';

        playBtn.innerHTML = `

          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>

            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>

          </svg>

          <span>Listen</span>

        `;

        playBtn.addEventListener('click', (e) => {

          e.stopPropagation();

          setOrbState('speaking', 'SPEAKING // KOKORO-82M');

          remoteAudio.src = 'data:audio/wav;base64,' + meta.audio_base64;

          remoteAudio.play().catch(err => console.warn('Audio play error:', err));

          remoteAudio.onended = () => setOrbState('idle', 'STANDBY // READY');

        });

        metaDiv.appendChild(playBtn);

      }

      msgDiv.appendChild(metaDiv);

    }

    chatContainer.appendChild(msgDiv);

    chatContainer.scrollTop = chatContainer.scrollHeight;

  }

  // --------------------------------------------------------------------------

  // 7. GEMINI-STYLE SESSIONS & DRAWER CONTROLS

  // --------------------------------------------------------------------------

  function toggleDrawer(open) {

    if (!drawer) return;

    const isMobile = window.innerWidth <= 768;

    if (isMobile) {

      const shouldOpen = open !== undefined ? open : !drawer.classList.contains('open');

      if (shouldOpen) {

        drawer.classList.add('open');

        if (drawerBackdrop) drawerBackdrop.classList.add('open');

      } else {

        drawer.classList.remove('open');

        if (drawerBackdrop) drawerBackdrop.classList.remove('open');

      }

    } else {

      // Desktop: Only toggle collapsed when user explicitly clicks drawerToggleBtn (open === undefined)

      // or explicitly requests open=true/open=false on desktop

      if (open !== undefined) {

        if (open === true) {

          drawer.classList.remove('collapsed');

        }

        // Do not auto-collapse desktop sidebar on chat switches!

        return;

      }

      if (drawer.classList.contains('collapsed')) {

        drawer.classList.remove('collapsed');

      } else {

        drawer.classList.add('collapsed');

      }

    }

  }

  if (drawerToggleBtn) drawerToggleBtn.addEventListener('click', () => toggleDrawer());

  if (closeDrawerBtn) closeDrawerBtn.addEventListener('click', () => toggleDrawer(false));

  if (drawerBackdrop) drawerBackdrop.addEventListener('click', () => toggleDrawer(false));

  async function fetchSessions() {

    try {

      const res = await fetch('/api/sessions', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        return;

      }

      if (res.ok) {

        const data = await res.json();

        sessionsList = data.sessions || [];

        renderSessionList();

      }

    } catch (err) {

      console.warn('Error fetching sessions:', err);

    }

  }

  function renderSessionList() {

    if (!sessionListContainer) return;

    sessionListContainer.innerHTML = '';

    if (sessionsList.length === 0) {

      const emptyNotice = document.createElement('div');

      emptyNotice.style.padding = '12px';

      emptyNotice.style.fontSize = '12px';

      emptyNotice.style.color = 'var(--text-dim)';

      emptyNotice.textContent = 'No previous threads found.';

      sessionListContainer.appendChild(emptyNotice);

      return;

    }

    sessionsList.forEach((sess) => {

      const item = document.createElement('div');

      item.className = 'session-item' + (sess.session_id === activeSessionId ? ' active' : '');

      item.setAttribute('data-id', sess.session_id);

      const titleWrap = document.createElement('div');

      titleWrap.className = 'session-title-wrap';

      const iconSvg = `

        <svg class="session-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>

        </svg>

      `;

      titleWrap.innerHTML = iconSvg;

      const titleSpan = document.createElement('span');

      titleSpan.textContent = sess.title || 'New Chat';

      titleWrap.appendChild(titleSpan);

      item.appendChild(titleWrap);

      // Session Actions (Rename & Delete)

      const actionsDiv = document.createElement('div');

      actionsDiv.className = 'session-actions';

      // Rename button

      const renameBtn = document.createElement('button');

      renameBtn.className = 'session-action-btn';

      renameBtn.title = 'Rename Thread';

      renameBtn.innerHTML = `

        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

          <path d="M12 20h9"/>

          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>

        </svg>

      `;

      renameBtn.addEventListener('click', (e) => {

        e.preventDefault();

        e.stopPropagation();

        openRenameModal(sess.session_id, sess.title);

      });

      actionsDiv.appendChild(renameBtn);

      // Delete button

      const deleteBtn = document.createElement('button');

      deleteBtn.className = 'session-action-btn delete-btn';

      deleteBtn.title = 'Delete Thread';

      deleteBtn.innerHTML = `

        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

          <polyline points="3 6 5 6 21 6"/>

          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>

        </svg>

      `;

      deleteBtn.addEventListener('click', (e) => {

        e.preventDefault();

        e.stopPropagation();

        openDeleteModal(sess.session_id, sess.title);

      });

      actionsDiv.appendChild(deleteBtn);

      item.appendChild(actionsDiv);

      item.addEventListener('click', () => {

        switchSession(sess.session_id, sess.title);

        toggleDrawer(false);

      });

      sessionListContainer.appendChild(item);

    });

  }

  async function switchSession(sessionId, title) {

    if (!sessionId) return;

    activeSessionId = sessionId;

    localStorage.setItem('libra_active_session', activeSessionId);

    activeSessionTitle = title || 'Chat Thread';

    if (activeThreadTitleEl) activeThreadTitleEl.textContent = activeSessionTitle;

    renderSessionList();

    // Load messages

    try {

      chatContainer.innerHTML = '';

      const res = await fetch(`/api/sessions/${sessionId}`, {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.ok) {

        const data = await res.json();

        if (data.session && data.session.title) {

          activeSessionTitle = data.session.title;

          if (activeThreadTitleEl) activeThreadTitleEl.textContent = activeSessionTitle;

        }

        const msgs = data.messages || [];

        if (msgs.length === 0) {

          if (typeof renderStarterChips === 'function') {

            renderStarterChips();

          }

        } else {

          msgs.forEach((m) => {

            const isUser = m.role === 'user';

            appendMessage(m.content, isUser, {

              action: m.tool_used,

              latency_ms: m.latency_ms,

              token_metrics: {

                input_tokens: m.input_tokens,

                output_tokens: m.output_tokens,

                eval_count: m.output_tokens,

                prompt_eval_count: m.input_tokens,

                tokens_per_sec: m.tokens_per_sec

              }

            });

          });

        }

      }

    } catch (err) {

      console.warn('Error loading session messages:', err);

    }

    fetchTokenSummary();

  }

  async function createNewSession() {

    try {

      const res = await fetch('/api/sessions/new', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({ title: 'New Chat', client_scope: 'remote_web' })

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        return;

      }

      if (res.ok) {

        const data = await res.json();

        const newSid = data.session_id;

        await fetchSessions();

        await switchSession(newSid, 'New Chat');

        toggleDrawer(false);

      }

    } catch (err) {

      console.warn('Error creating new session:', err);

    }

  }

  if (newChatBtn) newChatBtn.addEventListener('click', createNewSession);

  if (headerNewChatBtn) headerNewChatBtn.addEventListener('click', createNewSession);

  // In-DOM Delete Confirmation Modal (Replaces unsupported window.confirm on Mobile)

  function openDeleteModal(sessionId, title) {

    pendingDeleteSessionId = sessionId;

    if (deleteModalPrompt) {

      deleteModalPrompt.textContent = `Are you sure you want to delete "${title || 'this thread'}"? This will permanently erase the chat history.`;

    }

    if (deleteModal) deleteModal.style.display = 'flex';

  }

  function closeDeleteModal() {

    pendingDeleteSessionId = null;

    if (deleteModal) deleteModal.style.display = 'none';

  }

  async function executeDeleteSession() {

    if (!pendingDeleteSessionId) return;

    const targetId = pendingDeleteSessionId;

    closeDeleteModal();

    try {

      const res = await fetch(`/api/sessions/${targetId}`, {

        method: 'DELETE',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        return;

      }

      if (res.ok) {

        await fetchSessions();

        if (targetId === activeSessionId) {

          const nextSession = sessionsList.length > 0 ? sessionsList[0].session_id : null;

          if (nextSession) {

            await switchSession(nextSession);

          } else {

            await createNewSession();

          }

        }

      }

    } catch (err) {

      console.warn('Error deleting session:', err);

    }

  }

  if (closeDeleteModalBtn) closeDeleteModalBtn.addEventListener('click', closeDeleteModal);

  if (cancelDeleteBtn) cancelDeleteBtn.addEventListener('click', closeDeleteModal);

  if (confirmDeleteBtn) confirmDeleteBtn.addEventListener('click', executeDeleteSession);

  if (deleteModal) {

    deleteModal.addEventListener('click', (e) => {

      if (e.target === deleteModal) closeDeleteModal();

    });

  }

  // In-DOM Rename Modal (Replaces unsupported window.prompt on Mobile)

  function openRenameModal(sessionId, title) {

    pendingRenameSessionId = sessionId;

    if (renameInput) {

      renameInput.value = title || 'New Chat';

    }

    if (renameModal) renameModal.style.display = 'flex';

    setTimeout(() => {

      if (renameInput) {

        renameInput.focus();

        renameInput.select();

      }

    }, 100);

  }

  function closeRenameModal() {

    pendingRenameSessionId = null;

    if (renameModal) renameModal.style.display = 'none';

  }

  async function executeRenameSession() {

    if (!pendingRenameSessionId || !renameInput) return;

    const updated = renameInput.value.trim();

    const targetId = pendingRenameSessionId;

    closeRenameModal();

    if (!updated) return;

    try {

      const res = await fetch(`/api/sessions/${targetId}`, {

        method: 'PATCH',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({ title: updated })

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        return;

      }

      if (res.ok) {

        if (targetId === activeSessionId) {

          activeSessionTitle = updated;

          if (activeThreadTitleEl) activeThreadTitleEl.textContent = activeSessionTitle;

        }

        await fetchSessions();

      }

    } catch (err) {

      console.warn('Error renaming session:', err);

    }

  }

  if (closeRenameModalBtn) closeRenameModalBtn.addEventListener('click', closeRenameModal);

  if (cancelRenameBtn) cancelRenameBtn.addEventListener('click', closeRenameModal);

  if (confirmRenameBtn) confirmRenameBtn.addEventListener('click', executeRenameSession);

  if (renameInput) {

    renameInput.addEventListener('keydown', (e) => {

      if (e.key === 'Enter') {

        e.preventDefault();

        executeRenameSession();

      } else if (e.key === 'Escape') {

        closeRenameModal();

      }

    });

  }

  if (renameModal) {

    renameModal.addEventListener('click', (e) => {

      if (e.target === renameModal) closeRenameModal();

    });

  }

  // --------------------------------------------------------------------------

  // 8. TOKEN TELEMETRY MODAL & HUD

  // --------------------------------------------------------------------------

  async function fetchTokenSummary() {

    try {

      const url = `/api/tokens/summary?session_id=${encodeURIComponent(activeSessionId)}`;

      const res = await fetch(url, {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.ok) {

        const root = await res.json();

        const data = root.data || {};

        updateTokenHUD(data);

        populateTokenModal(data);

      }

    } catch (err) {

      console.warn('Error fetching token summary:', err);

    }

  }

  function formatNumber(num) {

    if (num === undefined || num === null) return '0';

    return Number(num).toLocaleString();

  }

  function updateTokenHUD(data) {

    if (!tokenHudText) return;

    const sessTotal = (data.active_session && data.active_session.total_tokens) || 0;

    tokenHudText.textContent = `${formatNumber(sessTotal)} tok`;

  }

  function populateTokenModal(data) {
    // Live GPU Hardware Vitals
    fetch('/api/vitals', { headers: getAuthHeaders() })
      .then(r => r.json())
      .then(v => {
        const gpuNameEl = document.getElementById('gpu-device-name');
        const gpuTempEl = document.getElementById('gpu-live-temp');
        const gpuVramNum = document.getElementById('gpu-vram-numbers');
        const gpuVramFill = document.getElementById('gpu-vram-fill');
        if (v) {
          if (gpuNameEl && v.gpu) gpuNameEl.textContent = v.gpu.name || 'NVIDIA GeForce RTX 5060 Ti';
          if (gpuTempEl && v.gpu) gpuTempEl.textContent = `${v.gpu.temperature_c || 48}°C | ${v.gpu.load_percent || 9}% Load`;
          const usedGb = ((v.vram_used_mb || 11695) / 1024).toFixed(1);
          const totalGb = ((v.vram_total_mb || 16311) / 1024).toFixed(1);
          const pct = Math.min(100, Math.round(((v.vram_used_mb || 11695) / (v.vram_total_mb || 16311)) * 100));
          if (gpuVramNum) gpuVramNum.textContent = `${usedGb} GB / ${totalGb} GB (${pct}%)`;
          if (gpuVramFill) gpuVramFill.style.width = `${pct}%`;
        }
      })
      .catch(() => {});


    // 1. Last Turn

    const last = data.last_turn || {};

    if (tokLastSpeed) {

      tokLastSpeed.textContent = last.tokens_per_sec ? `${last.tokens_per_sec.toFixed(1)} t/s` : '0.0 t/s';

    }

    if (tokLastCounts) {

      tokLastCounts.textContent = `In: ${formatNumber(last.input_tokens)} | Out: ${formatNumber(last.output_tokens)} (${last.latency_ms || 0}ms)`;

    }

    if (tokLastModel) {

      tokLastModel.textContent = last.model_used || 'qwen3:8b (Local GPU)';

    }

    // 2. Active Session

    const sess = data.active_session || {};

    if (tokSessTotal) {

      tokSessTotal.textContent = formatNumber(sess.total_tokens || 0);

    }

    if (tokSessBreakdown) {

      tokSessBreakdown.textContent = `Prompt: ${formatNumber(sess.input_tokens || 0)} | Eval: ${formatNumber(sess.output_tokens || 0)}`;

    }

    if (tokSessTurns) {

      tokSessTurns.textContent = `Turns: ${sess.turn_count || 0}`;

    }

    // 3. Today

    const today = data.today || {};

    if (tokTodayTotal) {

      tokTodayTotal.textContent = formatNumber(today.total_tokens || 0);

    }

    if (tokTodayBreakdown) {

      tokTodayBreakdown.textContent = `In: ${formatNumber(today.input_tokens || 0)} | Out: ${formatNumber(today.output_tokens || 0)}`;

    }

    // 4. Saved Tokens

    const saved = data.saved_tokens || {};

    const totalSaved = (saved.markovian_saved || 0) + (saved.fast_path_saved || 0) + (saved.total_saved || 0);

    if (tokSavedTotal) {

      tokSavedTotal.textContent = `⚡ ${formatNumber(totalSaved)}`;

    }

    if (tokSavedDesc) {

      tokSavedDesc.textContent = `Bypassed via Markovian H-MEM context window & Fast-Path PreAct macros`;

    }

  }

  function toggleTokenModal(open) {

    if (!tokenModal) return;

    const shouldOpen = open !== undefined ? open : (tokenModal.style.display !== 'flex');

    if (shouldOpen) {

      fetchTokenSummary();

      tokenModal.style.display = 'flex';

    } else {

      tokenModal.style.display = 'none';

    }

  }

  if (tokenHudBtn) tokenHudBtn.addEventListener('click', () => toggleTokenModal(true));

  if (closeTokenModalBtn) closeTokenModalBtn.addEventListener('click', () => toggleTokenModal(false));

  if (tokenModal) {

    tokenModal.addEventListener('click', (e) => {

      if (e.target === tokenModal) toggleTokenModal(false);

    });

  }

  // --------------------------------------------------------------------------

  // 9. LIVE VITALS POLLING

  // --------------------------------------------------------------------------

  async function fetchVitals() {

    try {

      const res = await fetch('/api/vitals', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        return;

      }

      if (res.ok) {

        const data = await res.json();

        const gpuName = data.gpu?.name || 'RTX 5060 Ti';

        const vramUsed = data.vram_used_mb ? (data.vram_used_mb / 1024).toFixed(1) + 'GB' : '11.6GB';

        if (vitalsText) {

          vitalsText.textContent = `${gpuName} | ${vramUsed} | ${data.version || 'v10.2.0'}`;

        }

      }

    } catch (e) {

      if (vitalsText) vitalsText.textContent = 'PC OFFLINE';

    }

  }

  setInterval(fetchVitals, 5000);

  // --------------------------------------------------------------------------

  // --------------------------------------------------------------------------

  // VOICE SPEECH OUTPUT (READ ALOUD) PREFERENCE

  // --------------------------------------------------------------------------

  function isVoiceSpeechEnabled() {

    return localStorage.getItem('libra_voice_speech') !== 'disabled';

  }

  function setVoiceSpeechEnabled(enabled) {

    localStorage.setItem('libra_voice_speech', enabled ? 'enabled' : 'disabled');

    if (!enabled && audioPlayer) {

      audioPlayer.stop();

      if (remoteAudio) {

        remoteAudio.pause();

        remoteAudio.src = '';

      }

      setOrbState('idle', 'STANDBY // READY');

    }

    updateVoiceSpeechUI();

  }

  function updateVoiceSpeechUI() {

    const enabled = isVoiceSpeechEnabled();

    const toggleEl = document.getElementById('options-voice-toggle') || document.getElementById('voice-speech-toggle');

    if (toggleEl) toggleEl.checked = enabled;

    const noteEl = document.getElementById('voice-status-note');

    if (noteEl) {

      if (enabled) {

        noteEl.className = 'voice-status-note';

        noteEl.innerHTML = '🔊 <strong>Speaking Aloud:</strong> Libra speaks every answer using neural voice (Kokoro-82M).';

      } else {

        noteEl.className = 'voice-status-note muted';

        noteEl.innerHTML = '🔇 <strong>Silent Mode Active:</strong> Libra responds with text only. Fast response with 0 audio synthesis.';

      }

    }

    const quickBtn = document.getElementById('quick-voice-toggle-btn');

    const quickIcon = document.getElementById('quick-voice-icon');

    if (quickBtn && quickIcon) {

      if (enabled) {

        quickBtn.className = 'header-action-btn voice-active';

        quickIcon.textContent = '🔊 Voice';

        quickBtn.title = 'Libra Voice: ON (Click to Mute)';

      } else {

        quickBtn.className = 'header-action-btn voice-muted';

        quickIcon.textContent = '🔇 Muted';

        quickBtn.title = 'Libra Voice: OFF (Click to Unmute)';

      }

    }

  }

  // 10. CHAT PROMPT SUBMISSION & KOKORO TTS PLAYBACK

  // --------------------------------------------------------------------------

  function unlockAudio() {

    if (remoteAudio) {

      // Priming user gesture: triggers play/pause immediately within the synchronous click/touch handler

      remoteAudio.play().then(() => remoteAudio.pause()).catch(() => {});

    }

  }

  // --------------------------------------------------------------------------

  // ATTACHMENT MANAGEMENT (IMAGES, PDFS & DOCUMENTS)

  // --------------------------------------------------------------------------

  function handleFileSelected(e) {

    const file = e.target.files && e.target.files[0];

    if (!file) return;

    if (file.size > 35 * 1024 * 1024) {

      alert('File size exceeds 35 MB limit.');

      if (fileInput) fileInput.value = '';

      return;

    }

    const isImage = file.type.startsWith('image/');

    pendingAttachment = {

      file: file,

      name: file.name,

      size: file.size,

      fileType: isImage ? 'image' : 'document'

    };

    if (attachmentName) attachmentName.textContent = file.name;

    if (attachmentStatus) {

      const sizeStr = file.size > 1024 * 1024

        ? (file.size / (1024 * 1024)).toFixed(1) + ' MB'

        : Math.round(file.size / 1024) + ' KB';

      attachmentStatus.textContent = `${isImage ? 'Photo' : 'Document'} (${sizeStr}) • Ready to analyze`;

    }

    if (attachmentThumb) {

      attachmentThumb.innerHTML = '';

      if (isImage) {

        const reader = new FileReader();

        reader.onload = (re) => {

          attachmentThumb.innerHTML = `<img src="${re.target.result}" alt="Thumb">`;

        };

        reader.readAsDataURL(file);

      } else {

        attachmentThumb.innerHTML = `

          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>

            <polyline points="14 2 14 8 20 8"/>

          </svg>

        `;

      }

    }

    if (attachmentTray) attachmentTray.style.display = 'flex';

  }

  function clearAttachment() {

    pendingAttachment = null;

    if (fileInput) fileInput.value = '';

    if (attachmentTray) attachmentTray.style.display = 'none';

    if (attachmentThumb) attachmentThumb.innerHTML = '';

  }

  if (attachBtn && fileInput) {

    attachBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', handleFileSelected);

  }

  if (removeAttachmentBtn) {

    removeAttachmentBtn.addEventListener('click', clearAttachment);

  }

  // Drag and drop files onto the chat interface

  window.addEventListener('dragover', (e) => e.preventDefault());

  window.addEventListener('drop', (e) => {

    e.preventDefault();

    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {

      handleFileSelected({ target: { files: e.dataTransfer.files } });

    }

  });

  // Clipboard paste support (e.g. pasting copied screenshot directly)

  window.addEventListener('paste', (e) => {

    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {

      handleFileSelected({ target: { files: e.clipboardData.files } });

    }

  });

  let isGenerating = false;
  let activeAbortController = null;

  function stopGeneration() {
    if (activeAbortController) {
      try {
        activeAbortController.abort();
      } catch (e) {}
      activeAbortController = null;
    }
  }

  function setGeneratingState(generating) {
    isGenerating = generating;
    if (!sendBtn) return;
    if (generating) {
      sendBtn.classList.add('stop-mode');
      sendBtn.title = 'Stop generating';
      sendBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <rect x="5" y="5" width="14" height="14" rx="2" ry="2"/>
        </svg>
      `;
    } else {
      sendBtn.classList.remove('stop-mode');
      sendBtn.title = 'Send Message';
      sendBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="19" x2="12" y2="5"/>
          <polyline points="5 12 12 5 19 12"/>
        </svg>
      `;
    }
  }

  async function sendPrompt(text) {

    if ((!text || !text.trim()) && !pendingAttachment) return;

    // If currently generating, clicking the button or submitting triggers Stop
    if (isGenerating) {
      stopGeneration();
      return;
    }

    unlockAudio();

    const t0_stream = performance.now();
    activeAbortController = new AbortController();
    setGeneratingState(true);

    const cleanPrompt = (text || '').trim();

    if (promptInput) promptInput.value = '';

    // Clear starter chips when conversation starts

    document.querySelectorAll('.starter-hero-wrap').forEach(el => el.remove());

    // Reset user scroll state to follow response

    userIsScrolledUp = false;

    if (scrollToBottomBtn) scrollToBottomBtn.style.display = 'none';

    // Collapse orb smoothly to give room for chat

    if (orbSection && !orbSection.classList.contains('collapsed')) {

      orbSection.classList.add('collapsed');

      setTimeout(onOrbResize, 350);

    }

    const currentAttach = pendingAttachment;

    clearAttachment();

    let uploadedFileInfo = null;

    if (currentAttach) {

      setOrbState('thinking', 'UPLOADING // MULTIMODAL');

      try {

        const formData = new FormData();

        formData.append('file', currentAttach.file);

        formData.append('session_id', activeSessionId);

        const headers = {};

        if (authToken) headers['Authorization'] = 'Bearer ' + authToken;

        const upRes = await fetch('/api/upload', {

          method: 'POST',

          headers: headers,

          body: formData

        });

        if (upRes.ok) {

          uploadedFileInfo = await upRes.json();

        }

      } catch (upErr) {

        console.warn('Upload error:', upErr);

      }

    }

    const userDisplayText = cleanPrompt || (uploadedFileInfo ? `Analyze attached ${uploadedFileInfo.file_type}: ${uploadedFileInfo.filename}` : 'Analyze file');

    appendMessage(userDisplayText, true, {

      attached_file: uploadedFileInfo

    });

    setOrbState('thinking', 'THINKING // LLM REASONING');

    // Stop any existing audio before starting a new turn

    audioPlayer.stop();

    try {

      const payload = {

        prompt: cleanPrompt || 'Please examine and analyze this attached file in detail, summarizing key insights.',

        session_id: activeSessionId,

        client_scope: 'remote_web',

        synthesize_audio: isVoiceSpeechEnabled()

      };

      if (uploadedFileInfo) {

        payload.attached_file_path = uploadedFileInfo.file_path;

        payload.attached_file_name = uploadedFileInfo.filename;

        payload.attached_file_type = uploadedFileInfo.file_type;

      }

      // ----------------------------------------------------------------------

      // BRANCH B: MULTIMODAL FILE UPLOAD (SYNCHRONOUS FALLBACK)

      // ----------------------------------------------------------------------

      if (uploadedFileInfo) {

        const res = await fetch('/api/chat', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

          body: JSON.stringify(payload)

        });

        if (res.status === 401 || res.status === 403) {

          showAuthModal();

          setOrbState('error', 'AUTH REQUIRED');

          return;

        }

        const data = await res.json();

        const reply = data.reply_text || data.voice_response || 'Understood.';

        appendMessage(reply, false, {

          action: data.action,

          latency_ms: data.latency_ms,

          token_metrics: data.token_metrics,

          audio_base64: data.audio_base64,

          generated_image_url: data.generated_image_url

        });

        fetchTokenSummary();

        fetchSessions();

        if (data.audio_base64) {

          audioPlayer.enqueue(data.audio_base64);

        } else {

          setOrbState('idle', 'STANDBY // READY');

        }

        return;

      }

      // ----------------------------------------------------------------------

      // BRANCH A: SSE TOKEN STREAMING + KOKORO SENTENCE AUDIO QUEUE

      // ----------------------------------------------------------------------

      setOrbState('thinking', 'STREAMING // TIME-TO-FIRST-TOKEN <200MS');

      const msgDiv = document.createElement('div');

      msgDiv.className = 'msg msg-libra';

      const contentDiv = document.createElement('div');

      contentDiv.className = 'msg-content';

      // Live Thought Accordion (Phase 12.6)
      let activeThoughtSteps = [];
      const thoughtAccordion = createThoughtAccordion(
        activeThoughtSteps,
        'Thinking... 0s ▾',
        true
      );
      let streamElapsedSec = 0;
      thoughtAccordion._streamElapsedSec = 0;
      thoughtAccordion._timerInterval = setInterval(() => {
        if (!thoughtAccordion || thoughtAccordion._isFinalized) {
          if (thoughtAccordion && thoughtAccordion._timerInterval) {
            clearInterval(thoughtAccordion._timerInterval);
            thoughtAccordion._timerInterval = null;
          }
          return;
        }
        streamElapsedSec += 1;
        thoughtAccordion._streamElapsedSec = streamElapsedSec;
        const durLabel = thoughtAccordion.querySelector('.thought-duration-label');
        if (durLabel && thoughtAccordion.classList.contains('streaming')) {
          durLabel.textContent = `Thinking... ${formatDuration(streamElapsedSec)} ▾`;
        }
      }, 1000);
      contentDiv.appendChild(thoughtAccordion);

      const textNode = document.createElement('div');
      textNode.className = 'msg-text';
      contentDiv.appendChild(textNode);
      msgDiv.appendChild(contentDiv);

      const metaDiv = document.createElement('div');

      metaDiv.className = 'msg-meta';

      msgDiv.appendChild(metaDiv);

      chatContainer.appendChild(msgDiv);

      if (!userIsScrolledUp) {

        chatContainer.scrollTop = chatContainer.scrollHeight;

      }

      let accumulatedText = '';

      const collectedAudioChunks = [];

      let finalTokenMetrics = null;

      const res = await fetch('/api/chat?stream=true', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify(payload),

        signal: activeAbortController ? activeAbortController.signal : undefined

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        setOrbState('error', 'AUTH REQUIRED');

        msgDiv.remove();

        return;

      }

      if (!res.ok) {

        throw new Error(`HTTP ${res.status}: ${res.statusText}`);

      }

      const reader = res.body.getReader();

      const decoder = new TextDecoder('utf-8');

      let streamBuffer = '';

      // Progressive Render Queue Throttling (UI Thread Optimization - Task 5)
      let renderRafId = null;
      let isRenderScheduled = false;
      let lastRenderTime = 0;
      const RENDER_INTERVAL_MS = 24; // ~40-60 FPS throttle window

      function renderProgressive(immediate = false) {
        let curVisible = accumulatedText;
        const thinkMatch = accumulatedText.match(/<think>([\s\S]*?)(?:<\/think>|$)/i);
        if (thinkMatch) {
          const reasoning = thinkMatch[1].trim();
          if (accumulatedText.includes('</think>')) {
            curVisible = accumulatedText.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
          } else {
            curVisible = immediate ? accumulatedText.replace(/<\/?think>/gi, '').trim() : '';
          }
          if (thoughtAccordion && reasoning) {
            updateThoughtAccordionReasoning(thoughtAccordion, reasoning, false);
          }
        }

        const textToDisplay = curVisible || (immediate ? accumulatedText.replace(/<\/?think>/gi, '').trim() : '');

        if (immediate) {
          if (renderRafId) {
            cancelAnimationFrame(renderRafId);
            clearTimeout(renderRafId);
            renderRafId = null;
          }
          isRenderScheduled = false;
          textNode.innerHTML = formatMarkdown(textToDisplay);
          if (!userIsScrolledUp) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
          }
          lastRenderTime = performance.now();
          return;
        }

        if (isRenderScheduled) return;

        const now = performance.now();
        const delta = now - lastRenderTime;

        if (delta >= RENDER_INTERVAL_MS) {
          isRenderScheduled = true;
          renderRafId = requestAnimationFrame(() => {
            renderRafId = null;
            isRenderScheduled = false;
            textNode.innerHTML = formatMarkdown(textToDisplay);
            if (!userIsScrolledUp) {
              chatContainer.scrollTop = chatContainer.scrollHeight;
            }
            lastRenderTime = performance.now();
          });
        } else {
          isRenderScheduled = true;
          renderRafId = setTimeout(() => {
            renderRafId = requestAnimationFrame(() => {
              renderRafId = null;
              isRenderScheduled = false;
              textNode.innerHTML = formatMarkdown(textToDisplay);
              if (!userIsScrolledUp) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
              }
              lastRenderTime = performance.now();
            });
          }, Math.max(0, RENDER_INTERVAL_MS - delta));
        }
      }

      while (true) {

        const { done, value } = await reader.read();

        if (done) break;

        streamBuffer += decoder.decode(value, { stream: true });

        const events = streamBuffer.split(/\r?\n\r?\n/);

        streamBuffer = events.pop(); // Trailing incomplete chunk remains in buffer

        for (const evtStr of events) {

          const trimmed = evtStr.trim();

          if (!trimmed) continue;

          const lines = trimmed.split(/\r?\n/);

          for (const line of lines) {

            if (!line.startsWith('data:')) continue;

            const jsonText = line.slice(5).trim();

            if (!jsonText) continue;

            try {

              const data = JSON.parse(jsonText);

              if (data.type === 'meta') {
                if (data.session_id) {
                  activeSessionId = data.session_id;
                }
                if (data.session_title && activeThreadTitleEl) {
                  activeThreadTitleEl.textContent = data.session_title;
                }
              } else if (data.type === 'thought') {
                if (thoughtAccordion && !thoughtAccordion._isFinalized) {
                  if (data.steps && Array.isArray(data.steps)) {
                    data.steps.forEach(s => {
                      activeThoughtSteps.push(s);
                      appendLiveStepToAccordion(thoughtAccordion, s);
                    });
                  }
                }
              } else if (data.type === 'thought_step') {
                if (thoughtAccordion && data.step && !thoughtAccordion._isFinalized) {
                  activeThoughtSteps.push(data.step);
                  appendLiveStepToAccordion(thoughtAccordion, data.step);
                }
              } else if (data.type === 'clear') {
                accumulatedText = '';
                renderProgressive(true);
              } else if (data.type === 'token') {
                // First answer token: thinking is finished! Immediately freeze thought timer & accordion
                if (thoughtAccordion && !thoughtAccordion._isFinalized) {
                  finalizeThoughtAccordion(thoughtAccordion, activeThoughtSteps, t0_stream);
                }
                accumulatedText += data.content;
                renderProgressive(false);
              } else if (data.type === 'audio') {
                if (data.audio_base64) {
                  collectedAudioChunks.push(data.audio_base64);
                  audioPlayer.enqueue(data.audio_base64);
                }
              } else if (data.type === 'done') {
                finalTokenMetrics = data.token_metrics;
                if (data.reply_text && (!accumulatedText || accumulatedText.length < data.reply_text.length)) {
                  accumulatedText = data.reply_text;
                }
                renderProgressive(true);
                if (thoughtAccordion && !thoughtAccordion._isFinalized) {
                  finalizeThoughtAccordion(thoughtAccordion, data.thought_steps || activeThoughtSteps, t0_stream);
                }
              }

            } catch (pErr) {

              console.warn('[SSE] Event parse error:', pErr, jsonText);

            }

          }

        }

      }

      // Check leftover data in streamBuffer

      if (streamBuffer.trim().startsWith('data:')) {

        try {

          const jsonText = streamBuffer.trim().slice(5).trim();

          const data = JSON.parse(jsonText);

          if (data.type === 'token') {

            accumulatedText += data.content;

          } else if (data.type === 'audio' && data.audio_base64) {

            collectedAudioChunks.push(data.audio_base64);

            audioPlayer.enqueue(data.audio_base64);

          } else if (data.type === 'done') {

            finalTokenMetrics = data.token_metrics;

          }

        } catch (e) {}

      }

      // Final synchronous render to ensure complete markdown and Prism code blocks
      renderProgressive(true);

      // Render Telemetry Badges

      if (finalTokenMetrics) {

        if (finalTokenMetrics.latency_ms) {

          const lat = document.createElement('span');

          lat.textContent = finalTokenMetrics.latency_ms + 'ms';

          metaDiv.appendChild(lat);

        }

        if (finalTokenMetrics && (finalTokenMetrics.turn_out || finalTokenMetrics.output_tokens || finalTokenMetrics.turn_in || finalTokenMetrics.input_tokens)) {

          const tok = document.createElement("span");

          tok.className = "token-badge";

          const inCount = finalTokenMetrics.turn_in || finalTokenMetrics.input_tokens || 0;

          const outCount = finalTokenMetrics.turn_out || finalTokenMetrics.output_tokens || 0;

          const tokSpeed = finalTokenMetrics.tok_per_sec || finalTokenMetrics.tokens_per_sec;

          const speedStr = tokSpeed ? " • " + tokSpeed.toFixed(1) + " tok/s" : "";

          if (inCount > 0 && outCount > 0) {

            tok.textContent = "⚡ Prompt: " + inCount + " tok • Reply: " + outCount + " tok" + speedStr;

            tok.title = "Prompt Tokens: " + inCount + " | Response Tokens: " + outCount + " | Total: " + (inCount + outCount);

          } else if (inCount > 0) {

            tok.textContent = "⚡ Prompt: " + inCount + " tok";

          } else {

            tok.textContent = tokSpeed ? "⚡ Reply: " + outCount + " tok" + speedStr : "⚡ " + outCount + " tok";

          }

          metaDiv.appendChild(tok);

        }

      }

      // Replay Audio Button if audio was generated

      if (collectedAudioChunks.length > 0) {

        const replayBtn = document.createElement('button');

        replayBtn.className = 'replay-audio-btn';

        replayBtn.title = 'Replay Kokoro TTS Voice';

        replayBtn.innerHTML = `

          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">

            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>

            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>

          </svg>

          <span>Listen</span>

        `;

        replayBtn.addEventListener('click', (e) => {

          e.stopPropagation();

          audioPlayer.stop();

          for (const chunk of collectedAudioChunks) {

            audioPlayer.enqueue(chunk);

          }

        });

        metaDiv.appendChild(replayBtn);

      }

      if (!userIsScrolledUp) {

        chatContainer.scrollTop = chatContainer.scrollHeight;

      }

      // Update telemetry & sidebar threads

      fetchTokenSummary();

      fetchSessions();

      if (!audioPlayer.isPlaying) {

        setOrbState('idle', 'STANDBY // READY');

      }

    } catch (err) {

      if (err.name === 'AbortError') {
        console.log('[Chat] Generation stopped by user.');
        if (accumulatedText) {
          accumulatedText += '\n\n*(Generation stopped by user)*';
          renderProgressive(true);
        }
        setOrbState('idle', 'STANDBY // READY');
      } else {
        console.error('[Chat Error]:', err);
        appendMessage('Connection Error: Unable to reach Home PC server.', false, { action: 'error' });
        setOrbState('error', 'OFFLINE');
      }

    } finally {
      setGeneratingState(false);
      activeAbortController = null;
      if (typeof thoughtAccordion !== 'undefined' && thoughtAccordion) {
        if (!thoughtAccordion._isFinalized) {
          finalizeThoughtAccordion(thoughtAccordion, activeThoughtSteps, t0_stream);
        }
        if (thoughtAccordion._timerInterval) {
          clearInterval(thoughtAccordion._timerInterval);
          thoughtAccordion._timerInterval = null;
        }
      }
    }

  }

  if (sendBtn) {

    sendBtn.addEventListener('click', () => {

      unlockAudio();

      if (promptInput) sendPrompt(promptInput.value);

    });

  }

  if (promptInput) {

    promptInput.addEventListener('keydown', (e) => {

      if (e.key === 'Enter') {

        if (isGenerating) {
          e.preventDefault();
          return; // Prevents sending a new prompt while the previous one is running
        }

        unlockAudio();

        sendPrompt(promptInput.value);

      }

    });

  }

  // --------------------------------------------------------------------------

  // 11. VOICE MICROPHONE CAPTURE (TAP-TO-SPEAK)

  // --------------------------------------------------------------------------

  async function startRecording() {

    try {

      unlockAudio();

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      audioChunks = [];

      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')

        ? 'audio/webm;codecs=opus'

        : (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus') ? 'audio/ogg;codecs=opus' : '');

      mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (e) => {

        if (e.data && e.data.size > 0) audioChunks.push(e.data);

      };

      mediaRecorder.onstop = async () => {

        const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });

        stream.getTracks().forEach(t => t.stop());

        await uploadVoiceAudio(audioBlob);

      };

      mediaRecorder.start(100);

      isRecording = true;

      if (micBtn) micBtn.classList.add('recording');

      setOrbState('listening', 'LISTENING // RECORDING MIC');

    } catch (err) {

      alert('Microphone access denied or unavailable: ' + err.message);

    }

  }

  function stopRecording() {

    if (mediaRecorder && isRecording) {

      unlockAudio();

      mediaRecorder.stop();

      isRecording = false;

      if (micBtn) micBtn.classList.remove('recording');

      setOrbState('thinking', 'TRANSCRIBING // FASTER-WHISPER');

    }

  }

  if (micBtn) {

    micBtn.addEventListener('click', () => {

      unlockAudio();

      if (!isRecording) startRecording();

      else stopRecording();

    });

  }

  async function uploadVoiceAudio(blob) {

    const formData = new FormData();

    formData.append('audio', blob, 'recording.webm');

    formData.append('session_id', activeSessionId);

    formData.append('client_scope', 'remote_web');

    formData.append('synthesize_audio', isVoiceSpeechEnabled() ? 'true' : 'false');

    try {

      const headers = {};

      if (authToken) headers['Authorization'] = 'Bearer ' + authToken;

      const url = `/api/voice?session_id=${encodeURIComponent(activeSessionId)}&client_scope=remote_web`;

      const res = await fetch(url, {

        method: 'POST',

        headers: headers,

        body: formData

      });

      if (res.status === 401 || res.status === 403) {

        showAuthModal();

        setOrbState('error', 'AUTH REQUIRED');

        return;

      }

      const data = await res.json();

      if (data.transcribed_text) {

        appendMessage(data.transcribed_text, true);

      }

      const reply = data.reply_text || data.voice_response || 'Understood.';

      appendMessage(reply, false, {

        action: data.action,

        latency_ms: data.latency_ms,

        token_metrics: data.token_metrics,

        audio_base64: data.audio_base64

      });

      fetchTokenSummary();

      fetchSessions();

      if (data.audio_base64) {

        audioPlayer.stop();

        audioPlayer.enqueue(data.audio_base64);

      } else {

        setOrbState('idle', 'STANDBY // READY');

      }

    } catch (err) {

      appendMessage('Voice upload error: ' + err.message, false, { action: 'error' });

      setOrbState('error', 'OFFLINE');

    }

  }

  // --------------------------------------------------------------------------

  // 12. AUTHENTICATION & MULTI-USER REGISTRATION (GOOGLE & EMAIL GATEWAY)

  // --------------------------------------------------------------------------

  const authTabLogin = document.getElementById('auth-tab-login');

  const authTabSignup = document.getElementById('auth-tab-signup');

  const authViewGoogle = document.getElementById('auth-view-google');

  const authStepEmail = document.getElementById('auth-step-email');

  const authStepOtp = document.getElementById('auth-step-otp');

  const authStepToken = document.getElementById('auth-step-token');

  const gMainHeading = document.getElementById('g-main-heading');

  const gSubHeading = document.getElementById('g-sub-heading');

  const gUseAnotherAccountBtn = document.getElementById('g-use-another-account-btn');

  const showEmailSigninBtn = document.getElementById('show-email-signin-btn');

  const backToGoogleBtn = document.getElementById('back-to-google-btn');

  const otpBackToGoogleBtn = document.getElementById('otp-back-to-google-btn');

  const gAccountsList = document.getElementById('g-accounts-list');

  const authEmailInput = document.getElementById('auth-email-input');

  const sendCodeBtn = document.getElementById('send-code-btn');

  const authOtpInput = document.getElementById('auth-otp-input');

  const verifyCodeBtn = document.getElementById('verify-code-btn');

  const resendCodeBtn = document.getElementById('resend-code-btn');

  const backToEmailBtn = document.getElementById('back-to-email-btn');

  const showTokenModeBtn = document.getElementById('show-token-mode-btn');

  const showEmailModeBtn = document.getElementById('show-email-mode-btn');

  const authStatusMsg = document.getElementById('auth-status-msg');

  const authRecipientDisplay = document.getElementById('auth-recipient-display');

  const autofillDevCodeBtn = document.getElementById('autofill-dev-code-btn');

  const authenticatorSetupBox = document.getElementById('authenticator-setup-box');

  const totpSecretDisplay = document.getElementById('totp-secret-display');

  const signOutBtn = document.getElementById('sign-out-btn');

  const currentRedirectUriEl = document.getElementById('current-redirect-uri');

  let currentAuthMode = 'login'; // 'login' or 'signup'

  let currentAuthStep = 'email'; // 'email', 'otp', 'token'

  let pendingAuthEmail = '';

  let activeDevCode = '';

  // Dynamic Google Callback Display & 1-Click Copy

  if (currentRedirectUriEl) {

    const cb = `${window.location.origin}/auth/google/callback`;

    currentRedirectUriEl.textContent = cb;

    currentRedirectUriEl.addEventListener('click', () => {

      navigator.clipboard.writeText(cb).then(() => {

        alert(`Copied callback URI:\n${cb}\n\nAdd this to "Authorized redirect URIs" in Google Cloud Console if needed!`);

      });

    });

  }

  function setAuthMode(mode) {

    currentAuthMode = 'login';

    if (gMainHeading) gMainHeading.textContent = 'Sign in';

    if (gSubHeading) gSubHeading.innerHTML = 'to continue to <span class="g-app-highlight">Project Libra</span>';

    if (authViewGoogle) authViewGoogle.style.display = 'flex';

    setAuthStatus('');

  }

  if (authTabLogin) authTabLogin.addEventListener('click', () => setAuthMode('login'));

  if (authTabSignup) authTabSignup.addEventListener('click', () => setAuthMode('login'));

  if (showEmailSigninBtn) {

    showEmailSigninBtn.addEventListener('click', () => {

      showAuthModal('google');

    });

  }

  if (gUseAnotherAccountBtn) {

    gUseAnotherAccountBtn.addEventListener('click', () => {

      showAuthModal('google');

    });

  }

  if (backToGoogleBtn) {

    backToGoogleBtn.addEventListener('click', () => {

      showAuthModal('google');

    });

  }

  if (otpBackToGoogleBtn) {

    otpBackToGoogleBtn.addEventListener('click', () => {

      showAuthModal('google');

    });

  }

  // Bind 1-click Google accounts from list (if rendered)

  if (gAccountsList) {

    const accItems = gAccountsList.querySelectorAll('.g-acc-item[data-email]');

    accItems.forEach((item) => {

      item.addEventListener('click', () => {

        const email = item.getAttribute('data-email');

        const name = item.getAttribute('data-name') || email;

        handleDirectGoogleAccountLogin(email, name);

      });

    });

  }

  function setAuthStatus(msg, type = 'info') {

    if (!authStatusMsg) return;

    if (!msg) {

      authStatusMsg.style.display = 'none';

      authStatusMsg.className = 'auth-status-msg';

      authStatusMsg.textContent = '';

      return;

    }

    authStatusMsg.textContent = msg;

    authStatusMsg.className = `auth-status-msg ${type}`;

    authStatusMsg.style.display = 'block';

  }

  function showAuthModal() {

    if (!authModal) return;

    authModal.style.display = 'flex';

    currentAuthStep = 'google';

    setAuthStatus('');

    if (authViewGoogle) authViewGoogle.style.display = 'flex';

    if (gMainHeading) gMainHeading.textContent = 'Sign in';

    if (gSubHeading) gSubHeading.textContent = 'to continue to Project Libra';

  }

  function hideAuthModal() {

    if (authModal) authModal.style.display = 'none';

    currentAuthStep = 'google';

    setAuthStatus('');

  }

  async function handleDirectGoogleAccountLogin(email, name, credential = null) {

    setAuthStatus(`Signing in with Google...`, 'info');

    try {

      const payload = {};

      if (credential) {

        payload.credential = credential;

      } else {

        payload.email = email;

        payload.name = name;

      }

      const res = await fetch('/api/auth/google-login', {

        method: 'POST',

        headers: { 'Content-Type': 'application/json' },

        body: JSON.stringify(payload)

      });

      const data = await res.json();

      if (res.ok && data.status === 'success') {

        authToken = data.token;

        localStorage.setItem('libra_token', authToken);

        document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;

        hideAuthModal();

        await initAuthAndRole();

  loadUserProfile();

        await fetchSessions();

        await fetchVitals();

        await fetchTokenSummary();

      } else {

        setAuthStatus(data.detail || 'Google authentication failed.', 'error');

      }

    } catch (err) {

      setAuthStatus('Could not connect to Libra server for Google login.', 'error');

    }

  }

  // Google Identity Services (GSI) Client Initializer

  function initGoogleIdentityServices() {

    if (window.google && google.accounts && google.accounts.id) {

      try {

        google.accounts.id.initialize({

          client_id: '1026074711825-75jqkhl8hbpnhqb4vtuedkm0eto727rl.apps.googleusercontent.com',

          callback: async (resp) => {

            if (resp && resp.credential) {

              await handleDirectGoogleAccountLogin(null, 'Google User', resp.credential);

            }

          },

          auto_select: false

        });

      } catch (gErr) {

        console.warn('[GSI] Google Identity init notice:', gErr);

      }

    }

  }

  initGoogleIdentityServices();

  window.addEventListener('load', initGoogleIdentityServices);

  // --- SEND VERIFICATION CODE / REGISTER ---

  async function handleSendVerificationCode() {

    if (!authEmailInput) return;

    const email = authEmailInput.value.trim().toLowerCase();

    if (!email || !email.includes('@') || !email.includes('.')) {

      setAuthStatus('Please enter a valid email address.', 'error');

      return;

    }

    pendingAuthEmail = email;

    if (sendCodeBtn) {

      sendCodeBtn.disabled = true;

      sendCodeBtn.textContent = 'CONNECTING...';

    }

    setAuthStatus('Generating secure unique passcode...', 'info');

    try {

      const res = await fetch('/api/auth/send-code', {

        method: 'POST',

        headers: { 'Content-Type': 'application/json' },

        body: JSON.stringify({ email: email, mode: currentAuthMode })

      });

      const data = await res.json();

      if (data.status === 'not_found') {

        setAuthStatus(data.message || 'Account not found. Switch to Sign Up to create your account.', 'error');

        return;

      }

      if (data.status === 'already_exists') {

        setAuthStatus(data.message || 'Email already registered. Switch to Log In to enter.', 'info');

        return;

      }

      if (res.ok && data.status === 'success') {

        if (authRecipientDisplay) authRecipientDisplay.textContent = email;

        showAuthModal('otp');

        // If dev/fallback code is provided

        if (data.dev_code) {

          activeDevCode = data.dev_code;

          if (autofillDevCodeBtn) {

            autofillDevCodeBtn.style.display = 'block';

            autofillDevCodeBtn.textContent = `⚡ Click to Autofill Code: ${data.dev_code}`;

          }

        } else {

          if (autofillDevCodeBtn) autofillDevCodeBtn.style.display = 'none';

        }

        // Google Authenticator Setup option

        if (data.totp_secret && authenticatorSetupBox && totpSecretDisplay) {

          totpSecretDisplay.textContent = data.totp_secret;

          authenticatorSetupBox.style.display = 'block';

        }

        if (data.is_new_user) {

          setAuthStatus('Account created! Enter the 6-digit verification code below or from Google Authenticator to enter.', 'success');

        } else {

          setAuthStatus('Welcome back! Enter the 6-digit verification code to enter your workspace.', 'success');

        }

      } else {

        setAuthStatus(data.detail || data.message || 'Failed to dispatch code.', 'error');

      }

    } catch (err) {

      setAuthStatus('Connection error. Could not reach Libra server.', 'error');

    } finally {

      if (sendCodeBtn) {

        sendCodeBtn.disabled = false;

        sendCodeBtn.textContent = currentAuthMode === 'login' ? 'LOG IN WITH CODE' : 'SIGN UP & VERIFY';

      }

    }

  }

  // --- AUTOFILL DEV CODE ---

  if (autofillDevCodeBtn) {

    autofillDevCodeBtn.addEventListener('click', () => {

      if (activeDevCode && authOtpInput) {

        authOtpInput.value = activeDevCode;

        handleVerifyCode();

      }

    });

  }

  // --- VERIFY CODE & ENTER ---

  async function handleVerifyCode() {

    if (!authOtpInput) return;

    const code = authOtpInput.value.trim();

    if (!code || code.length !== 6) {

      setAuthStatus('Please enter the complete 6-digit code.', 'error');

      return;

    }

    if (verifyCodeBtn) {

      verifyCodeBtn.disabled = true;

      verifyCodeBtn.textContent = 'VERIFYING...';

    }

    setAuthStatus('Authenticating identity & loading workspace...', 'info');

    try {

      const res = await fetch('/api/auth/verify-code', {

        method: 'POST',

        headers: { 'Content-Type': 'application/json' },

        body: JSON.stringify({ email: pendingAuthEmail, code: code })

      });

      const data = await res.json();

      if (res.ok && data.status === 'success') {

        authToken = data.token;

        localStorage.setItem('libra_token', authToken);

        document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;

        hideAuthModal();

        await initAuthAndRole();

        await fetchSessions();

        await fetchVitals();

        await fetchTokenSummary();

      } else {

        setAuthStatus(data.detail || 'Invalid or expired verification code.', 'error');

      }

    } catch (err) {

      setAuthStatus('Connection error while validating code.', 'error');

    } finally {

      if (verifyCodeBtn) {

        verifyCodeBtn.disabled = false;

        verifyCodeBtn.textContent = 'VERIFY & ENTER';

      }

    }

  }

  if (sendCodeBtn) sendCodeBtn.addEventListener('click', handleSendVerificationCode);

  if (authEmailInput) {

    authEmailInput.addEventListener('keydown', (e) => {

      if (e.key === 'Enter') handleSendVerificationCode();

    });

  }

  if (verifyCodeBtn) verifyCodeBtn.addEventListener('click', handleVerifyCode);

  if (authOtpInput) {

    authOtpInput.addEventListener('keydown', (e) => {

      if (e.key === 'Enter') handleVerifyCode();

    });

    authOtpInput.addEventListener('input', () => {

      if (authOtpInput.value.trim().length === 6) {

        handleVerifyCode();

      }

    });

  }

  if (resendCodeBtn) resendCodeBtn.addEventListener('click', handleSendVerificationCode);

  if (backToEmailBtn) backToEmailBtn.addEventListener('click', () => showAuthModal('email'));

  if (showTokenModeBtn) showTokenModeBtn.addEventListener('click', () => showAuthModal('token'));

  if (showEmailModeBtn) showEmailModeBtn.addEventListener('click', () => showAuthModal('email'));

  if (saveTokenBtn) {

    saveTokenBtn.addEventListener('click', () => {

      if (tokenInput) {

        authToken = tokenInput.value.trim();

        localStorage.setItem('libra_token', authToken);

        document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;

      }

      hideAuthModal();

      initAuthAndRole();

      fetchVitals();

      fetchSessions();

      fetchTokenSummary();

    });

  }

  if (signOutBtn) {

    signOutBtn.addEventListener('click', async (e) => {

      if (e) e.stopPropagation();

      if (currentUserRole === 'guest') {

        showAuthModal();

        return;

      }

      // 1. Instantly silence and abort all audio

      if (audioPlayer) audioPlayer.stop();

      if (remoteAudio) {

        remoteAudio.pause();

        remoteAudio.src = '';

      }

      // 2. Clear credentials and active thread

      authToken = '';

      localStorage.removeItem('libra_token');

      localStorage.removeItem('libra_active_session');

      document.cookie = 'libra_auth=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';

      // 3. Close navigation drawer immediately

      toggleDrawer(false);

      // 4. Reset DOM state immediately without full page reload

      if (chatContainer) chatContainer.innerHTML = '';

      if (sessionListContainer) sessionListContainer.innerHTML = '';

      updateRoleBadge({ role: 'guest', email: 'Signed Out' });

      // 5. Display clean pristine Google sign-in modal in 0ms

      showAuthModal();

      // 6. Asynchronous server cookie deletion

      fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});

    });

  }

  // --------------------------------------------------------------------------

  // 12B. PHASE 11: MEMORY VAULT, AIRDROP BRIDGE, & DAILY BRIEFING

  // --------------------------------------------------------------------------

  // --- VAULT MODAL ---

  const vaultNavBtn = document.getElementById('vault-nav-btn');

  const vaultModal = document.getElementById('vault-modal');

  const closeVaultModalBtn = document.getElementById('close-vault-modal');

  const vaultSearchInput = document.getElementById('vault-search-input');

  const vaultCategoryFilter = document.getElementById('vault-category-filter');

  const vaultCardsGrid = document.getElementById('vault-cards-grid');

  const vaultAddBtn = document.getElementById('vault-add-btn');

  async function loadVaultFacts() {

    if (!vaultCardsGrid) return;

    const q = vaultSearchInput ? vaultSearchInput.value.trim() : '';

    const cat = vaultCategoryFilter ? vaultCategoryFilter.value : '';

    let url = '/api/vault?';

    if (q) url += 'q=' + encodeURIComponent(q) + '&';

    if (cat) url += 'category=' + encodeURIComponent(cat);

    try {

      const resp = await fetch(url, { headers: getAuthHeaders() });

      if (!resp.ok) return;

      const data = await resp.json();

      const facts = data.facts || [];

      if (vaultCategoryFilter && vaultCategoryFilter.options.length <= 1) {

        const cats = Array.from(new Set(facts.map(f => f.category).filter(Boolean)));

        cats.forEach(c => {

          const opt = document.createElement('option');

          opt.value = c;

          opt.textContent = c.toUpperCase();

          vaultCategoryFilter.appendChild(opt);

        });

      }

      vaultCardsGrid.innerHTML = '';

      if (facts.length === 0) {

        vaultCardsGrid.innerHTML = '<div style="color: #64748b; padding: 20px; text-align: center;">No memory notes found matching query.</div>';

        return;

      }

      facts.forEach(f => {

        const card = document.createElement('div');

        card.className = 'vault-card' + (f.pinned ? ' pinned' : '');

        card.innerHTML = `

          <div class="vault-card-header">

            <div style="display: flex; align-items: center; gap: 8px;">

              <button class="vault-pin-btn" data-id="${f.id}" data-pinned="${f.pinned}">${f.pinned ? '★' : '☆'}</button>

              <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #00ffcc;">${escapeHtml(f.entity)}.${escapeHtml(f.relation)}</span>

            </div>

            <div style="display: flex; align-items: center; gap: 8px;">

              <span style="font-size: 10px; color: #38bdf8; background: #0c1c2e; padding: 2px 6px; border-radius: 4px;">[${escapeHtml((f.category || 'general').toUpperCase())}]</span>

              <span style="font-size: 10px; color: #64748b;">${escapeHtml((f.updated_at || '').substring(0, 16))}</span>

              <button class="vault-delete-btn" data-id="${f.id}" style="background: none; border: none; color: #f43f5e; cursor: pointer; font-size: 11px; margin-left: 6px;">✕</button>

            </div>

          </div>

          <div class="vault-card-body">${escapeHtml(f.value)}</div>

        `;

        vaultCardsGrid.appendChild(card);

      });

      vaultCardsGrid.querySelectorAll('.vault-pin-btn').forEach(btn => {

        btn.addEventListener('click', async (e) => {

          const id = e.target.getAttribute('data-id');

          const isPinned = e.target.getAttribute('data-pinned') === 'true';

          await fetch(`/api/vault/${id}`, {

            method: 'PUT',

            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

            body: JSON.stringify({ value: '', pinned: !isPinned })

          });

          loadVaultFacts();

        });

      });

      vaultCardsGrid.querySelectorAll('.vault-delete-btn').forEach(btn => {

        btn.addEventListener('click', async (e) => {

          const id = e.target.getAttribute('data-id');

          if (confirm('Delete this memory fact from SQLite and assets/vault/?')) {

            await fetch(`/api/vault/${id}`, {

              method: 'DELETE',

              headers: getAuthHeaders()

            });

            loadVaultFacts();

          }

        });

      });

    } catch (err) {

      console.error('Vault load error:', err);

    }

  }

  if (vaultNavBtn) {

    vaultNavBtn.addEventListener('click', () => {

      if (vaultModal) vaultModal.style.display = 'flex';

      loadVaultFacts();

    });

  }

  if (closeVaultModalBtn) {

    closeVaultModalBtn.addEventListener('click', () => {

      if (vaultModal) vaultModal.style.display = 'none';

    });

  }

  if (vaultSearchInput) {

    vaultSearchInput.addEventListener('input', () => loadVaultFacts());

  }

  if (vaultCategoryFilter) {

    vaultCategoryFilter.addEventListener('change', () => loadVaultFacts());

  }

  if (vaultAddBtn) {

    vaultAddBtn.addEventListener('click', async () => {

      const val = prompt('Enter memory fact text:');

      if (!val) return;

      const cat = prompt('Category (e.g. user_profile, career, preferences):', 'general') || 'general';

      await fetch('/api/vault', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({ entity: 'user', relation: 'note', value: val, category: cat, pinned: false })

      });

      loadVaultFacts();

    });

  }

  // --- AIRDROP MODAL ---

  const airdropNavBtn = document.getElementById('airdrop-nav-btn');

  const airdropModal = document.getElementById('airdrop-modal');

  const closeAirdropModalBtn = document.getElementById('close-airdrop-modal');

  const airdropDropZone = document.getElementById('airdrop-drop-zone');

  const airdropFileInput = document.getElementById('airdrop-file-input');

  const airdropSendBtn = document.getElementById('airdrop-send-btn');

  const airdropZoneText = document.getElementById('airdrop-zone-text');

  const airdropStatus = document.getElementById('airdrop-status');

  const airdropOpenOnPc = document.getElementById('airdrop-open-on-pc');

  let selectedAirdropFile = null;

  if (airdropNavBtn) {

    airdropNavBtn.addEventListener('click', () => {

      if (airdropModal) airdropModal.style.display = 'flex';

      if (airdropStatus) airdropStatus.style.display = 'none';

    });

  }

  if (closeAirdropModalBtn) {

    closeAirdropModalBtn.addEventListener('click', () => {

      if (airdropModal) airdropModal.style.display = 'none';

    });

  }

  if (airdropDropZone && airdropFileInput) {

    airdropDropZone.addEventListener('click', () => airdropFileInput.click());

    airdropFileInput.addEventListener('change', (e) => {

      if (e.target.files && e.target.files[0]) {

        selectedAirdropFile = e.target.files[0];

        airdropZoneText.textContent = `Selected: ${selectedAirdropFile.name} (${(selectedAirdropFile.size / 1024).toFixed(1)} KB)`;

        if (airdropSendBtn) airdropSendBtn.style.display = 'block';

      }

    });

  }

  if (airdropSendBtn) {

    airdropSendBtn.addEventListener('click', async () => {

      if (!selectedAirdropFile) return;

      airdropSendBtn.textContent = 'DROPPING TO PC...';

      airdropSendBtn.disabled = true;

      const fd = new FormData();

      fd.append('file', selectedAirdropFile);

      fd.append('open_on_pc', airdropOpenOnPc ? airdropOpenOnPc.checked : false);

      try {

        const resp = await fetch('/api/bridge/drop', {

          method: 'POST',

          headers: getAuthHeaders(),

          body: fd

        });

        const res = await resp.json();

        if (resp.ok && res.status === 'success') {

          if (airdropStatus) {

            airdropStatus.textContent = `✓ Dropped to PC (Downloads/LibraDrop/)! ${res.indexed_rag ? 'Auto-indexed into RAG.' : ''} ${res.opened_on_pc ? 'Opened on screen.' : ''}`;

            airdropStatus.style.display = 'block';

          }

          airdropZoneText.textContent = 'AirDrop another file';

          selectedAirdropFile = null;

          airdropSendBtn.style.display = 'none';

        } else {

          alert('AirDrop error: ' + (res.message || 'Unknown error'));

        }

      } catch (err) {

        alert('AirDrop error: ' + err.message);

      } finally {

        airdropSendBtn.textContent = 'AIRDROP TO PC';

        airdropSendBtn.disabled = false;

      }

    });

  }

  // --- BRIEFING MODAL ---

  const briefingNavBtn = document.getElementById('briefing-nav-btn');

  const briefingModal = document.getElementById('briefing-modal');

  const closeBriefingModalBtn = document.getElementById('close-briefing-modal');

  const briefingBulletsBox = document.getElementById('briefing-bullets-box');

  const briefingVitalsStrip = document.getElementById('briefing-vitals-strip');

  const refreshBriefingBtn = document.getElementById('refresh-briefing-btn');

  const speakBriefingBtn = document.getElementById('speak-briefing-btn');

  let currentBriefingText = '';

  async function loadDailyBriefing(force = false) {

    if (!briefingBulletsBox) return;

    briefingBulletsBox.innerHTML = '<div style="color: #64748b;">Synthesizing tactical morning briefing...</div>';

    try {

      const resp = await fetch(`/api/briefing?force=${force}`, { headers: getAuthHeaders() });

      if (!resp.ok) return;

      const data = await resp.json();

      const bullets = data.bullets || [];

      const telem = data.telemetry || {};

      if (briefingVitalsStrip) {

        const w = telem.weather || {};

        const h = telem.hardware || {};

        const g = telem.git || {};

        briefingVitalsStrip.innerHTML = `

          <div class="briefing-vital-card">

            <div class="label">KL Rain Prob</div>

            <div class="value" style="color: #38bdf8;">${w.max_rain_prob_12h || 0}%</div>

          </div>

          <div class="briefing-vital-card">

            <div class="label">GPU Temp</div>

            <div class="value" style="color: #00ffcc;">${h.gpu_temp_c ? h.gpu_temp_c + '°C' : '42°C'}</div>

          </div>

          <div class="briefing-vital-card">

            <div class="label">NVMe Free</div>

            <div class="value" style="color: #a7f3d0;">${h.nvme_free_gb ? h.nvme_free_gb + ' GB' : '--'}</div>

          </div>

          <div class="briefing-vital-card">

            <div class="label">Git Status</div>

            <div class="value" style="color: #fbbf24;">${g.dirty_count !== undefined ? g.dirty_count + ' dirty' : 'clean'}</div>

          </div>

        `;

      }

      briefingBulletsBox.innerHTML = '';

      currentBriefingText = bullets.join(' ');

      bullets.forEach(b => {

        const el = document.createElement('div');

        el.className = 'briefing-bullet';

        el.innerHTML = `<span style="color: #f59e0b; font-weight: bold;">•</span> <span>${escapeHtml(b.replace(/^[•\-]\s*/, ''))}</span>`;

        briefingBulletsBox.appendChild(el);

      });

    } catch (err) {

      briefingBulletsBox.innerHTML = `<div style="color: #f43f5e;">Error loading briefing: ${escapeHtml(err.message)}</div>`;

    }

  }

  if (briefingNavBtn) {

    briefingNavBtn.addEventListener('click', () => {

      if (briefingModal) briefingModal.style.display = 'flex';

      loadDailyBriefing(false);

    });

  }

  if (closeBriefingModalBtn) {

    closeBriefingModalBtn.addEventListener('click', () => {

      if (briefingModal) briefingModal.style.display = 'none';

    });

  }

  if (refreshBriefingBtn) {

    refreshBriefingBtn.addEventListener('click', () => loadDailyBriefing(true));

  }

  if (speakBriefingBtn) {

    speakBriefingBtn.addEventListener('click', async () => {

      if (!currentBriefingText) return;

      speakBriefingBtn.disabled = true;

      speakBriefingBtn.textContent = '🔊 Synthesizing Kokoro...';

      

      // 1. Try high-fidelity Kokoro-82M neural TTS (voice: af_heart) via backend

      try {

        setOrbState('speaking', 'SPEAKING // KOKORO (AF_HEART)');

        const res = await fetch('/api/tts', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

          body: JSON.stringify({ text: currentBriefingText })

        });

        if (res.ok) {

          const data = await res.json();

          if (data.audio_base64 && remoteAudio) {

            remoteAudio.src = 'data:audio/wav;base64,' + data.audio_base64;

            remoteAudio.play().catch(e => console.warn('Audio play error:', e));

            remoteAudio.onended = () => {

              setOrbState('idle', 'STANDBY // READY');

              speakBriefingBtn.disabled = false;

              speakBriefingBtn.textContent = '🔊 Speak Briefing';

            };

            return;

          }

        }

      } catch (err) {

        console.warn('Kokoro TTS synthesis error, using female browser fallback:', err);

      }

      // 2. Browser fallback: Strictly filter for natural female voice (exclude creepy Microsoft David!)

      if ('speechSynthesis' in window) {

        window.speechSynthesis.cancel();

        const u = new SpeechSynthesisUtterance(currentBriefingText);

        const voices = window.speechSynthesis.getVoices();

        const naturalVoice = voices.find(v => 

          (v.name.includes('Zira') || v.name.includes('Jenny') || v.name.includes('Aria') || 

           v.name.includes('Female') || v.name.includes('Google US English') || v.name.includes('Samantha')) &&

          !v.name.includes('David')

        ) || voices.find(v => !v.name.includes('David'));

        if (naturalVoice) u.voice = naturalVoice;

        u.rate = 1.0;

        u.onend = () => {

          setOrbState('idle', 'STANDBY // READY');

          speakBriefingBtn.disabled = false;

          speakBriefingBtn.textContent = '🔊 Speak Briefing';

        };

        window.speechSynthesis.speak(u);

      } else {

        speakBriefingBtn.disabled = false;

        speakBriefingBtn.textContent = '🔊 Speak Briefing';

      }

    });

  }

  // --------------------------------------------------------------------------

  // ROLE-BASED ACCESS CONTROL & GUEST TOKENS ENGINE (PHASE 11)

  // --------------------------------------------------------------------------

  let currentUserRole = 'guest';

  let currentUserInfo = null;

  async function initAuthAndRole() {

    try {

      const res = await fetch('/api/auth/me', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.ok) {

        const data = await res.json();

        currentUserInfo = data;

        currentUserRole = data.role || 'guest';

        updateRoleBadge(data);

      } else if (res.status === 401 || res.status === 403) {

        if (authToken) {

          localStorage.removeItem('libra_token');

          authToken = '';

        }

        currentUserRole = 'guest';

        updateRoleBadge({ role: 'guest', email: 'Guest User', label: 'Guest User' });

      }

    } catch (err) {

      console.warn('Failed to fetch auth info:', err);

      currentUserRole = 'guest';

      updateRoleBadge({ role: 'guest', email: 'Guest User', label: 'Guest User' });

    }

  }

  function updateRoleBadge(info) {

    const badge = document.getElementById('role-badge');

    const userEmailText = document.getElementById('user-email-text');

    const userRoleLabel = document.getElementById('user-role-label');

    const userAvatarInitial = document.getElementById('user-avatar-initial');

    const vitalsContainer = document.getElementById('vitals-container');

    const hostBugInbox = document.getElementById('host-bug-inbox-section');

    const drawerHostTools = document.getElementById('drawer-host-tools');

    const displayEmail = info.email || (info.role === 'host' ? 'Host Account' : 'Tester');

    if (userEmailText) userEmailText.textContent = displayEmail;

    if (userRoleLabel) userRoleLabel.textContent = (info.role || 'tester').toUpperCase();

    if (userAvatarInitial) {

      userAvatarInitial.textContent = (displayEmail[0] || 'U').toUpperCase();

    }

    currentUserRole = info.role || 'tester';

    if (!badge) return;

    if (info.role === 'host') {

      badge.textContent = '👑 HOST';

      badge.className = 'role-badge host';

      badge.title = `Host Owner (${displayEmail})`;

      document.querySelectorAll('.host-only-btn').forEach(btn => {

        if (btn.classList.contains('vitals-pill')) {

          btn.style.display = 'flex';

        } else {

          btn.style.display = 'inline-flex';

        }

      });

      if (vitalsContainer) vitalsContainer.style.display = 'flex';

      if (hostBugInbox) hostBugInbox.style.display = 'block';

      if (drawerHostTools) drawerHostTools.style.display = 'block';

      if (typeof updateHostBugBadge === 'function') updateHostBugBadge();

    } else {

      badge.textContent = `🧪 ${info.label || (info.role || 'TESTER').toUpperCase()}`;

      badge.className = 'role-badge guest';

      badge.title = 'Tester Mode: Chat, document analysis & bug reporting.';

      document.querySelectorAll('.host-only-btn').forEach(btn => btn.style.display = 'none');

      if (vitalsContainer) vitalsContainer.style.display = 'none';

      if (hostBugInbox) hostBugInbox.style.display = 'none';

      if (drawerHostTools) drawerHostTools.style.display = 'none';

    }

    if (signOutBtn) {

      if (info.role === 'host' || info.role === 'tester') {

        signOutBtn.title = 'Sign Out (' + displayEmail + ')';

        signOutBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>';

      } else {

        signOutBtn.title = 'Sign In / Enter Token';

        signOutBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line></svg>';

      }

    }

  }

  function promptForToken() {

    showAuthModal();

  }

  const inviteModal = document.getElementById('invite-modal');

  const inviteNavBtn = document.getElementById('invite-nav-btn');

  const closeInviteModalBtn = document.getElementById('close-invite-modal');

  const createGuestTokenBtn = document.getElementById('create-guest-token-btn');

  const guestLabelInput = document.getElementById('guest-label-input');

  const guestTokenCreatedBox = document.getElementById('guest-token-created-box');

  const guestInviteUrlField = document.getElementById('guest-invite-url-field');

  const copyGuestUrlBtn = document.getElementById('copy-guest-url-btn');

  const enableFunnelBtn = document.getElementById('enable-funnel-btn');

  if (inviteNavBtn) {

    inviteNavBtn.addEventListener('click', () => {

      openInviteModal();

    });

  }

  if (closeInviteModalBtn) {

    closeInviteModalBtn.addEventListener('click', () => {

      if (inviteModal) inviteModal.style.display = 'none';

    });

  }

  async function openInviteModal() {

    if (!inviteModal) return;

    inviteModal.style.display = 'flex';

    refreshFunnelStatus();

    loadGuestTokens();

  }

  async function refreshFunnelStatus() {

    try {

      const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });

      if (res.ok) {

        const data = await res.json();

        const fBadge = document.getElementById('funnel-badge');

        const fBox = document.getElementById('funnel-status-box');

        const fDesc = document.getElementById('funnel-status-desc');

        const cfField = document.getElementById('cloudflare-base-url-field');

        if (data.cloudflare_active && data.cloudflare_url) {

          if (fBadge) {

            fBadge.textContent = 'CLOUDFLARE + TAILSCALE LIVE';

            fBadge.className = 'funnel-badge-indicator active';

          }

          if (fBox) fBox.className = 'funnel-notice-box active';

          if (fDesc) {

            fDesc.innerHTML = '✅ <strong>Cloudflare Public Tunnel + Tailscale Active!</strong> Your friends can open the Cloudflare link from any phone/laptop without needing Tailscale.';

          }

          if (cfField) cfField.value = data.cloudflare_url;

        } else {

          if (fBadge) {

            fBadge.textContent = 'TAILNET ONLY';

            fBadge.className = 'funnel-badge-indicator';

          }

          if (fDesc) {

            fDesc.innerHTML = '⚠️ Cloudflare Tunnel is starting or offline. Click <strong>↻ Restart Cloudflare</strong> to generate a public link for friends.';

          }

          if (cfField) cfField.value = data.serve_url || 'https://libra-beta.note-loggerhead.ts.net/';

        }

      }

    } catch (e) {

      console.warn('Error refreshing tunnel status:', e);

    }

  }

  const restartCfBtn = document.getElementById('restart-cf-btn');

  if (restartCfBtn) {

    restartCfBtn.addEventListener('click', async () => {

      restartCfBtn.disabled = true;

      restartCfBtn.textContent = 'Starting...';

      try {

        await fetch('/api/cloudflare/restart', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' })

        });

        await refreshFunnelStatus();

      } catch (e) {

        console.warn('Cloudflare restart error:', e);

      } finally {

        restartCfBtn.disabled = false;

        restartCfBtn.textContent = '↻ Restart Cloudflare';

      }

    });

  }

  if (enableFunnelBtn) {

    enableFunnelBtn.addEventListener('click', async () => {

      enableFunnelBtn.disabled = true;

      enableFunnelBtn.textContent = 'Enabling...';

      try {

        const res = await fetch('/api/tailscale/funnel/enable', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' })

        });

        const data = await res.json();

        if (data.funnel_active) {

          alert('Tailscale Funnel enabled successfully! Your server is now accessible to guest invite links from any network.');

        } else {

          alert('Tailscale Funnel requested!\n\nIf you see a Tailscale authorization prompt, please approve node funnel access at:\n' + data.enable_url);

          window.open(data.enable_url, '_blank');

        }

        refreshFunnelStatus();

      } catch (err) {

        alert('Failed to enable funnel: ' + err.message);

      } finally {

        enableFunnelBtn.disabled = false;

        enableFunnelBtn.textContent = '⚡ ENABLE FUNNEL';

      }

    });

  }

  if (createGuestTokenBtn) {

    createGuestTokenBtn.addEventListener('click', async () => {

      const label = guestLabelInput ? (guestLabelInput.value.trim() || 'Guest Friend') : 'Guest Friend';

      createGuestTokenBtn.disabled = true;

      createGuestTokenBtn.textContent = 'Generating...';

      try {

        const res = await fetch('/api/tokens/guests', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

          body: JSON.stringify({ label: label, expires_in_days: 7 })

        });

        if (res.ok) {

          const data = await res.json();

          const tsField = document.getElementById('guest-ts-invite-url-field');

          if (guestTokenCreatedBox && guestInviteUrlField) {

            guestInviteUrlField.value = data.cloudflare_invite_url || data.invite_url;

            if (tsField) tsField.value = data.tailscale_invite_url || data.invite_url;

            guestTokenCreatedBox.style.display = 'block';

          }

          if (guestLabelInput) guestLabelInput.value = '';

          loadGuestTokens();

          refreshFunnelStatus();

        } else {

          const errData = await res.json();

          alert('Failed to create guest token: ' + (errData.detail || res.statusText));

        }

      } catch (err) {

        alert('Network error creating token: ' + err.message);

      } finally {

        createGuestTokenBtn.disabled = false;

        createGuestTokenBtn.textContent = '+ GENERATE';

      }

    });

  }

  if (copyGuestUrlBtn) {

    copyGuestUrlBtn.addEventListener('click', () => {

      if (guestInviteUrlField) {

        navigator.clipboard.writeText(guestInviteUrlField.value).then(() => {

          copyGuestUrlBtn.textContent = 'COPIED!';

          setTimeout(() => { copyGuestUrlBtn.textContent = 'COPY'; }, 2000);

        });

      }

    });

  }

  async function loadGuestTokens() {

    const listEl = document.getElementById('guest-tokens-list');

    if (!listEl) return;

    try {

      const res = await fetch('/api/tokens/guests', { headers: getAuthHeaders() });

      if (!res.ok) {

        listEl.innerHTML = '<div style="color: #64748b; font-size: 12px; padding: 10px;">Guest tokens only available to host.</div>';

        return;

      }

      const data = await res.json();

      const tokens = data.tokens || [];

      if (tokens.length === 0) {

        listEl.innerHTML = '<div style="color: #64748b; font-size: 12px; padding: 10px;">No active guest tokens yet. Generate one above!</div>';

        return;

      }

      let html = '';

      tokens.forEach(t => {

        const expiresStr = t.expires_at ? t.expires_at.split('T')[0] : 'Never';

        html += `

          <div class="guest-token-row" id="tok-row-${t.token}">

            <div class="guest-token-meta">

              <span class="guest-token-label">${t.label || 'Guest'}</span>

              <span class="guest-token-sub">${t.token.slice(0, 18)}... | Expires: ${expiresStr}</span>

            </div>

            <div class="guest-token-actions">

              <button class="guest-btn-small" onclick="window.libraCopyInvite('${t.token}')">Copy Link</button>

              <button class="guest-btn-small guest-btn-revoke" onclick="window.libraRevokeToken('${t.token}')">Revoke</button>

            </div>

          </div>

        `;

      });

      listEl.innerHTML = html;

    } catch (e) {

      listEl.innerHTML = '<div style="color: #f87171; font-size: 12px; padding: 10px;">Error loading guest tokens.</div>';

    }

  }

  window.libraCopyInvite = function(token) {

    const base = window.location.origin;

    const url = `${base}/?token=${token}`;

    navigator.clipboard.writeText(url).then(() => {

      alert(`Invite link copied to clipboard!\n\n${url}`);

    });

  };

  window.libraRevokeToken = async function(token) {

    if (!confirm('Are you sure you want to revoke this guest access token?')) return;

    try {

      const res = await fetch(`/api/tokens/guests/${token}`, {

        method: 'DELETE',

        headers: getAuthHeaders()

      });

      if (res.ok) {

        loadGuestTokens();

      } else {

        alert('Failed to revoke token');

      }

    } catch (e) {

      alert('Error revoking token: ' + e.message);

    }

  };

  // --------------------------------------------------------------------------

  // USER & ROLE MANAGEMENT CONTROLLER (HOST ONLY)

  // --------------------------------------------------------------------------

  const usersModal = document.getElementById('users-modal');

  const usersNavBtn = document.getElementById('users-nav-btn');

  const manageUsersDrawerBtn = document.getElementById('manage-users-drawer-btn');

  const closeUsersModalBtn = document.getElementById('close-users-modal-btn');

  const refreshUsersBtn = document.getElementById('refresh-users-btn');

  const usersTableBody = document.getElementById('users-table-body');

  const usersCountBadge = document.getElementById('users-count-badge');

  const inviteUserForm = document.getElementById('invite-user-form');

  const inviteUserEmail = document.getElementById('invite-user-email');

  const inviteUserName = document.getElementById('invite-user-name');

  const inviteUserRole = document.getElementById('invite-user-role');

  const usersModalStatus = document.getElementById('users-modal-status');

  let _lastModalCloseTimestamp = 0;
  function registerModalClosed() {
    _lastModalCloseTimestamp = Date.now();
  }
  function isGhostClickFromModalClose() {
    return (Date.now() - _lastModalCloseTimestamp) < 450;
  }

  function showUsersModal() {
    if (typeof optionsModal !== 'undefined' && optionsModal) {
      optionsModal.style.display = 'none';
      optionsModal.classList.remove('active');
    }
    if (usersModal) {
      usersModal.style.display = 'flex';
      usersModal.classList.add('active');
      fetchUsersList();
    }
  }

  function hideUsersModal() {
    registerModalClosed();
    if (usersModal) {
      usersModal.style.display = 'none';
      usersModal.classList.remove('active');
    }
  }

  if (usersNavBtn) {
    usersNavBtn.addEventListener('click', (e) => {
      if (isGhostClickFromModalClose()) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      toggleDrawer(false);
      showUsersModal();
    });
  }

  if (manageUsersDrawerBtn) {
    manageUsersDrawerBtn.addEventListener('click', (e) => {
      if (isGhostClickFromModalClose()) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      toggleDrawer(false);
      showUsersModal();
    });
  }

  const optionsOpenUsersBtn = document.getElementById('options-open-users-btn');
  if (optionsOpenUsersBtn) {
    optionsOpenUsersBtn.addEventListener('click', () => {
      closeOptionsModal();
      showUsersModal();
    });
  }

  const desktopGuiDrawerBtn = document.getElementById('desktop-gui-drawer-btn');
  if (desktopGuiDrawerBtn) {
    desktopGuiDrawerBtn.addEventListener('click', async () => {
      toggleDrawer(false);
      try {
        await fetch('/api/gui/show', {
          method: 'POST',
          headers: getAuthHeaders()
        });
        showGlobalToast('✨ Bringing Project Libra to your desktop monitor...');
      } catch (e) {
        console.error('Failed to show GUI:', e);
      }
    });
  }

  if (closeUsersModalBtn) {
    closeUsersModalBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      hideUsersModal();
    });
  }

  if (refreshUsersBtn) refreshUsersBtn.addEventListener('click', fetchUsersList);

  async function fetchUsersList() {

    if (!usersTableBody) return;

    usersTableBody.innerHTML = '<div class="users-loading-state" style="color:#94a3b8; font-size:12px; padding:12px; text-align:center;">Loading users...</div>';

    try {

      const res = await fetch('/api/users', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (!res.ok) {

        usersTableBody.innerHTML = `<div style="color:#ef4444; font-size:12px; padding:12px; text-align:center;">Failed to load users (${res.status})</div>`;

        return;

      }

      const data = await res.json();

      const users = data.users || [];

      if (usersCountBadge) usersCountBadge.textContent = users.length;

      if (users.length === 0) {

        usersTableBody.innerHTML = '<div style="color:#94a3b8; font-size:12px; padding:12px; text-align:center;">No users registered yet.</div>';

        return;

      }

      usersTableBody.innerHTML = '';

      users.forEach((u) => {
        const row = document.createElement('div');
        const isMainHost = u.is_primary_host;
        const roleClass = u.role === 'host' ? 'role-host' : 'role-tester';
        row.className = `user-row-item ${isMainHost ? 'is-main-host' : (u.role === 'host' ? 'is-host' : 'is-tester')}`;
        const initial = (u.display_name || u.email || 'U')[0].toUpperCase();
        const avatarClass = u.role === 'host' ? 'avatar-host' : 'avatar-tester';

        row.innerHTML = `
          <div class="user-row-left">
            <div class="user-row-avatar ${avatarClass}">${initial}</div>
            <div class="user-row-info">
              <div class="user-row-name">
                <span>${escapeHtml(u.display_name || u.email.split('@')[0])}</span>
                ${isMainHost ? '<span class="primary-host-tag">MAIN HOST</span>' : ''}
              </div>
              <div class="user-row-email">${escapeHtml(u.email)}</div>
            </div>
          </div>
          <div class="user-row-right">
            <select class="user-role-select ${roleClass}" data-email="${escapeHtml(u.email)}" ${isMainHost ? 'disabled title="Primary Host cannot be changed"' : ''}>
              <option value="tester" ${u.role === 'tester' ? 'selected' : ''}>🧪 Tester</option>
              <option value="host" ${u.role === 'host' ? 'selected' : ''}>👑 Host</option>
            </select>
            <button class="user-delete-btn" data-email="${escapeHtml(u.email)}" ${isMainHost ? 'disabled title="Primary Host cannot be deleted"' : ''}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:middle; margin-right:3px;"><path d="M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
              Delete
            </button>
          </div>
        `;

        // Role select change listener
        const roleSelect = row.querySelector('.user-role-select');
        if (roleSelect && !isMainHost) {
          roleSelect.addEventListener('change', async (e) => {
            const newRole = e.target.value;
            await changeUserRole(u.email, newRole, roleSelect);
          });
        }

        // Delete button listener
        const delBtn = row.querySelector('.user-delete-btn');
        if (delBtn && !isMainHost) {
          delBtn.addEventListener('click', async () => {
            if (confirm(`Are you sure you want to remove user "${u.email}"?`)) {
              await deleteUser(u.email);
            }
          });
        }

        usersTableBody.appendChild(row);

      });

    } catch (err) {

      usersTableBody.innerHTML = `<div style="color:#ef4444; font-size:12px; padding:12px; text-align:center;">Error: ${err.message}</div>`;

    }

  }

  async function changeUserRole(email, newRole, selectElem) {

    showUsersStatus(`Updating ${email} to ${newRole}...`, 'info');

    try {

      const res = await fetch('/api/users/role', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({ email: email, role: newRole })

      });

      const data = await res.json();

      if (res.ok) {

        showUsersStatus(`Success: ${email} is now ${newRole.toUpperCase()}!`, 'success');

        if (selectElem) {

          selectElem.className = `user-role-select ${newRole === 'host' ? 'role-host' : 'role-tester'}`;
          const rowElem = selectElem.closest('.user-row-item');
          if (rowElem) {
            rowElem.className = `user-row-item ${newRole === 'host' ? 'is-host' : 'is-tester'}`;
            const avatar = rowElem.querySelector('.user-row-avatar');
            if (avatar) avatar.className = `user-row-avatar ${newRole === 'host' ? 'avatar-host' : 'avatar-tester'}`;
          }

        }

      } else {

        showUsersStatus(data.detail || 'Failed to update role.', 'error');

        fetchUsersList(); // Revert

      }

    } catch (err) {

      showUsersStatus('Network error updating role.', 'error');

      fetchUsersList();

    }

  }

  async function deleteUser(email) {

    showUsersStatus(`Removing ${email}...`, 'info');

    try {

      const res = await fetch(`/api/users/${encodeURIComponent(email)}`, {

        method: 'DELETE',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      const data = await res.json();

      if (res.ok) {

        showUsersStatus(`User ${email} removed.`, 'success');

        fetchUsersList();

      } else {

        showUsersStatus(data.detail || 'Failed to delete user.', 'error');

      }

    } catch (err) {

      showUsersStatus('Network error deleting user.', 'error');

    }

  }

  if (inviteUserForm) {

    inviteUserForm.addEventListener('submit', async (e) => {

      e.preventDefault();

      const email = inviteUserEmail.value.trim().toLowerCase();

      const name = inviteUserName ? inviteUserName.value.trim() : '';

      const role = inviteUserRole ? inviteUserRole.value : 'tester';

      if (!email) return;

      showUsersStatus(`Adding ${email}...`, 'info');

      try {

        const res = await fetch('/api/users/invite', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

          body: JSON.stringify({ email: email, display_name: name, role: role })

        });

        const data = await res.json();

        if (res.ok) {

          showUsersStatus(`User ${email} registered with role ${role.toUpperCase()}!`, 'success');

          inviteUserEmail.value = '';

          if (inviteUserName) inviteUserName.value = '';

          fetchUsersList();

        } else {

          showUsersStatus(data.detail || 'Failed to add user.', 'error');

        }

      } catch (err) {

        showUsersStatus('Network error adding user.', 'error');

      }

    });

  }

  function showUsersStatus(msg, type = 'info') {

    if (!usersModalStatus) return;

    usersModalStatus.textContent = msg;

    usersModalStatus.className = `auth-status-msg ${type}`;

    usersModalStatus.style.display = 'block';

    setTimeout(() => {

      if (usersModalStatus) usersModalStatus.style.display = 'none';

    }, 4500);

  }

  // --------------------------------------------------------------------------

  // 12.6 BUG REPORT & TESTER FEEDBACK CENTER (AUTO SCREENSHOT & GITHUB ISSUES)

  // --------------------------------------------------------------------------

  const bugNavBtn = document.getElementById('bug-nav-btn');

  const bugBadge = document.getElementById('bug-badge');

  const bugReportModal = document.getElementById('bug-report-modal');

  const closeBugModalBtn = document.getElementById('close-bug-modal');

  const submitBugBtn = document.getElementById('submit-bug-btn');

  const bugReporterInput = document.getElementById('bug-reporter-input');

  const bugCategorySelect = document.getElementById('bug-category-select');

  const bugDescInput = document.getElementById('bug-desc-input');

  const bugSubmitStatus = document.getElementById('bug-submit-status');

  const bugScreenshotThumb = document.getElementById('bug-screenshot-thumb');

  const bugScreenshotPreviewBox = document.getElementById('bug-screenshot-preview-box');

  const bugScreenshotStatusText = document.getElementById('bug-screenshot-status-text');

  const hostBugInboxSection = document.getElementById('host-bug-inbox-section');

  const hostBugInboxCount = document.getElementById('host-bug-inbox-count');

  const refreshBugsBtn = document.getElementById('refresh-bugs-btn');

  const toggleHostSubmitForm = document.getElementById('toggle-host-submit-form');

  const testerBugFormSection = document.getElementById('tester-bug-form-section');

  const bugReportsList = document.getElementById('bug-reports-list');

  const bugResolvedList = document.getElementById('bug-resolved-list');

  const bugStatTotal = document.getElementById('bug-stat-total');

  const bugStatActive = document.getElementById('bug-stat-active');

  const bugStatResolved = document.getElementById('bug-stat-resolved');

  const bugStatSince = document.getElementById('bug-stat-since');

  const bugTabActiveBtn = document.getElementById('bug-tab-active-btn');

  const bugTabResolvedBtn = document.getElementById('bug-tab-resolved-btn');

  const bugTabActiveCount = document.getElementById('bug-tab-active-count');

  const bugTabResolvedCount = document.getElementById('bug-tab-resolved-count');

  let currentBugScreenshot = '';

  let currentBugTab = 'active';

  function setBugTab(tab) {

    currentBugTab = tab;

    if (tab === 'active') {

      if (bugReportsList) bugReportsList.style.display = 'flex';

      if (bugResolvedList) bugResolvedList.style.display = 'none';

      if (bugTabActiveBtn) {

        bugTabActiveBtn.style.background = 'rgba(251, 113, 133, 0.15)';

        bugTabActiveBtn.style.borderColor = 'rgba(251, 113, 133, 0.4)';

        bugTabActiveBtn.style.color = '#fb7185';

      }

      if (bugTabResolvedBtn) {

        bugTabResolvedBtn.style.background = 'transparent';

        bugTabResolvedBtn.style.borderColor = 'rgba(255, 255, 255, 0.15)';

        bugTabResolvedBtn.style.color = '#94a3b8';

      }

    } else {

      if (bugReportsList) bugReportsList.style.display = 'none';

      if (bugResolvedList) bugResolvedList.style.display = 'flex';

      if (bugTabActiveBtn) {

        bugTabActiveBtn.style.background = 'transparent';

        bugTabActiveBtn.style.borderColor = 'rgba(255, 255, 255, 0.15)';

        bugTabActiveBtn.style.color = '#94a3b8';

      }

      if (bugTabResolvedBtn) {

        bugTabResolvedBtn.style.background = 'rgba(52, 211, 153, 0.15)';

        bugTabResolvedBtn.style.borderColor = 'rgba(52, 211, 153, 0.4)';

        bugTabResolvedBtn.style.color = '#34d399';

      }

    }

  }

  if (bugTabActiveBtn) bugTabActiveBtn.addEventListener('click', () => setBugTab('active'));

  if (bugTabResolvedBtn) bugTabResolvedBtn.addEventListener('click', () => setBugTab('resolved'));

  async function updateHostBugBadge() {

    if (currentUserRole !== 'host' || !bugBadge) return;

    try {

      const res = await fetch('/api/bugs', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (res.ok) {

        const data = await res.json();

        const reports = data.reports || [];

        if (reports.length > 0) {

          bugBadge.textContent = reports.length;

          bugBadge.style.display = 'inline-flex';

          if (hostBugInboxCount) hostBugInboxCount.textContent = `(${reports.length} Open)`;

        } else {

          bugBadge.style.display = 'none';

          if (hostBugInboxCount) hostBugInboxCount.textContent = '(0 Open)';

        }

      }

    } catch (e) {}

  }

  // Periodic badge poll for host (every 20s)

  setInterval(() => {

    if (currentUserRole === 'host') updateHostBugBadge();

  }, 20000);

  async function openBugModal() {

    if (!bugReportModal) return;

    bugReportModal.style.display = 'flex';

    if (bugSubmitStatus) bugSubmitStatus.style.display = 'none';

    if (bugDescInput) bugDescInput.value = '';

    // Auto-fill reporter name/email

    if (bugReporterInput && currentUserInfo) {

      bugReporterInput.value = currentUserInfo.email || currentUserInfo.label || '';

    }

    // Role-specific view

    if (currentUserRole === 'host') {

      if (hostBugInboxSection) hostBugInboxSection.style.display = 'block';

      if (testerBugFormSection) testerBugFormSection.style.display = 'none';

      fetchBugReports();

    } else {

      if (hostBugInboxSection) hostBugInboxSection.style.display = 'none';

      if (testerBugFormSection) testerBugFormSection.style.display = 'block';

    }

    // Capture screenshot automatically

    if (window.html2canvas) {

      if (bugScreenshotStatusText) bugScreenshotStatusText.textContent = 'Capturing current screen...';

      if (bugScreenshotPreviewBox) bugScreenshotPreviewBox.style.display = 'flex';

      try {

        bugReportModal.style.opacity = '0';

        const canvas = await window.html2canvas(document.body, {

          logging: false,

          useCORS: true,

          scale: 1,

          ignoreElements: (el) => el.id === 'bug-report-modal' || el.classList.contains('modal-overlay')

        });

        bugReportModal.style.opacity = '1';

        currentBugScreenshot = canvas.toDataURL('image/png', 0.85);

        if (bugScreenshotThumb) {

          bugScreenshotThumb.src = currentBugScreenshot;

          bugScreenshotThumb.style.display = 'block';

        }

        if (bugScreenshotStatusText) {

          bugScreenshotStatusText.textContent = 'Screen captured and ready to attach.';

        }

      } catch (err) {

        console.warn('[Screenshot error]:', err);

        bugReportModal.style.opacity = '1';

        currentBugScreenshot = '';

        if (bugScreenshotThumb) bugScreenshotThumb.style.display = 'none';

        if (bugScreenshotStatusText) bugScreenshotStatusText.textContent = 'Screenshot skipped.';

      }

    } else {

      currentBugScreenshot = '';

      if (bugScreenshotThumb) bugScreenshotThumb.style.display = 'none';

    }

  }

  function closeBugModal() {
    registerModalClosed();
    if (bugReportModal) bugReportModal.style.display = 'none';
  }

  if (bugNavBtn) {
    bugNavBtn.addEventListener('click', (e) => {
      if (isGhostClickFromModalClose()) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      openBugModal();
    });
  }

  if (closeBugModalBtn) {
    closeBugModalBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      closeBugModal();
    });
  }

  if (refreshBugsBtn) refreshBugsBtn.addEventListener('click', fetchBugReports);

  if (toggleHostSubmitForm && testerBugFormSection) {

    toggleHostSubmitForm.addEventListener('click', () => {

      const isHidden = testerBugFormSection.style.display === 'none';

      testerBugFormSection.style.display = isHidden ? 'block' : 'none';

      toggleHostSubmitForm.textContent = isHidden ? '➖ Hide Bug Submission Form' : '➕ File a New Bug / Feedback as Host';

    });

  }

  // Click on thumbnail to preview full captured screenshot

  if (bugScreenshotThumb) {

    bugScreenshotThumb.addEventListener('click', () => {

      if (currentBugScreenshot && typeof openLightbox === 'function') {

        openLightbox(currentBugScreenshot);

      } else if (currentBugScreenshot && imageLightbox && lightboxImg) {

        lightboxImg.src = currentBugScreenshot;

        imageLightbox.style.display = 'flex';

      }

    });

  }

  async function submitBugReport() {

    if (!bugDescInput || !bugDescInput.value.trim()) {

      showBugStatus('Please describe what happened or what you encountered.', 'error');

      return;

    }

    const reporter = (bugReporterInput && bugReporterInput.value.trim()) || 'Tester';

    const category = (bugCategorySelect && bugCategorySelect.value) || 'UI / Mobile Layout';

    const desc = bugDescInput.value.trim();

    showBugStatus('Submitting bug report & screenshot to GitHub...', 'info');

    if (submitBugBtn) submitBugBtn.disabled = true;

    try {

      const res = await fetch('/api/bugs', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({

          reporter_name: reporter,

          category: category,

          description: desc,

          device_info: navigator.userAgent,

          session_id: activeSessionId,

          screenshot: currentBugScreenshot

        })

      });

      const data = await res.json();

      if (res.ok && data.status === 'success') {

        let msg = '🚀 Bug report and screenshot successfully submitted!';

        if (data.github_issue_url) {

          msg += ` <a href="${data.github_issue_url}" target="_blank" style="color: #38bdf8; text-decoration: underline; font-weight: 600; margin-left: 6px;">View on GitHub Issues (#${data.github_issue_number || 'New'}) &rarr;</a>`;

        }

        showBugStatus(msg, 'success');

        bugDescInput.value = '';

        currentBugScreenshot = '';

        if (currentUserRole === 'host') {

          fetchBugReports();

        }

        updateHostBugBadge();

      } else {

        showBugStatus(data.detail || 'Failed to submit bug report.', 'error');

      }

    } catch (err) {

      showBugStatus('Network error submitting bug report.', 'error');

    } finally {

      if (submitBugBtn) submitBugBtn.disabled = false;

    }

  }

  function showBugStatus(msg, type = 'info') {

    if (!bugSubmitStatus) return;

    bugSubmitStatus.innerHTML = msg;

    bugSubmitStatus.style.display = 'block';

    bugSubmitStatus.style.color = type === 'error' ? '#f87171' : (type === 'info' ? '#38bdf8' : '#34d399');

  }

  if (submitBugBtn) submitBugBtn.addEventListener('click', submitBugReport);

  async function fetchBugReports() {

    if (!bugReportsList) return;

    bugReportsList.innerHTML = '<div style="color:#94a3b8; font-size:12px; padding:8px;">Loading reports...</div>';

    if (bugResolvedList) bugResolvedList.innerHTML = '<div style="color:#94a3b8; font-size:12px; padding:8px;">Loading resolved history...</div>';

    try {

      const res = await fetch('/api/bugs', {

        headers: getAuthHeaders({ 'Content-Type': 'application/json' })

      });

      if (!res.ok) {

        bugReportsList.innerHTML = '<div style="color:#ef4444; font-size:12px;">Failed to load reports.</div>';

        return;

      }

      const data = await res.json();

      const reports = data.reports || [];

      const resolved = data.resolved || [];

      const stats = data.stats || {};

      

      // Update telemetry strip

      if (bugStatTotal) bugStatTotal.textContent = stats.total_submitted ?? (reports.length + resolved.length);

      if (bugStatActive) bugStatActive.textContent = stats.active_count ?? reports.length;

      if (bugStatResolved) bugStatResolved.textContent = stats.resolved_count ?? resolved.length;

      if (bugStatSince) bugStatSince.textContent = stats.tracking_since ? stats.tracking_since.split(' ')[0] : '-';

      if (bugTabActiveCount) bugTabActiveCount.textContent = reports.length;

      if (bugTabResolvedCount) bugTabResolvedCount.textContent = resolved.length;

      // Update badge counter

      if (bugBadge) {

        if (reports.length > 0) {

          bugBadge.textContent = reports.length;

          bugBadge.style.display = 'inline-flex';

        } else {

          bugBadge.style.display = 'none';

        }

      }

      if (hostBugInboxCount) hostBugInboxCount.textContent = `(${reports.length} Open)`;

      // --- 1. RENDER ACTIVE REPORTS ---

      if (reports.length === 0) {

        bugReportsList.innerHTML = '<div style="color:#94a3b8; font-size:12px; padding:12px; text-align: center;">🎉 No unresolved bug reports. All clear!</div>';

      } else {

        bugReportsList.innerHTML = '';

        reports.forEach(r => {

          const item = document.createElement('div');

          item.className = 'host-bug-card';

          

          const headerRow = document.createElement('div');

          headerRow.className = 'host-bug-card-top';

          headerRow.innerHTML = `

            <div style="display: flex; align-items: center; gap: 6px;">

              <span class="host-bug-badge">${escapeHtml(r.category || 'Bug')}</span>

              <strong style="color: #38bdf8;">${escapeHtml(r.reporter || 'Tester')}</strong>

              <span style="font-size: 10px; color: #94a3b8;">(${escapeHtml(r.role || 'tester')})</span>

            </div>

            <span style="font-size: 10px; color: #64748b; font-family: monospace;">${r.created_at || ''}</span>

          `;

          item.appendChild(headerRow);

          const desc = document.createElement('div');

          desc.style.cssText = 'color: #e2e8f0; white-space: pre-wrap; font-size: 12.5px; line-height: 1.4; margin: 4px 0;';

          desc.textContent = r.description;

          item.appendChild(desc);

          // Screenshot thumbnail with click-to-preview

          const previewImgUrl = r.screenshot_url || r.github_screenshot_url;

          if (previewImgUrl) {

            const shotRow = document.createElement('div');

            shotRow.style.cssText = 'display: flex; align-items: center; gap: 8px; margin: 4px 0; background: rgba(0,0,0,0.3); padding: 6px; border-radius: 6px;';

            shotRow.innerHTML = `

              <img src="${previewImgUrl}" style="width: 76px; height: 46px; object-fit: cover; border-radius: 4px; border: 1px solid rgba(0,242,254,0.4); cursor: pointer;" title="Click to enlarge screenshot" alt="Bug Screenshot">

              <span style="font-size: 11px; color: #38bdf8; cursor: pointer;">🔍 Click to enlarge captured screen</span>

            `;

            shotRow.addEventListener('click', () => {

              if (typeof openLightbox === 'function') openLightbox(previewImgUrl);

            });

            item.appendChild(shotRow);

          }

          const actionsRow = document.createElement('div');

          actionsRow.className = 'host-bug-actions';

          

          if (r.github_issue_url) {

            const ghLink = document.createElement('a');

            ghLink.href = r.github_issue_url;

            ghLink.target = '_blank';

            ghLink.innerHTML = `🐙 Issue #${r.github_issue_number || ''} &rarr;`;

            ghLink.style.cssText = 'display: inline-flex; align-items: center; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc; border-radius: 4px; padding: 4px 10px; font-size: 11px; text-decoration: none; font-weight: 600;';

            actionsRow.appendChild(ghLink);

          } else {

            const syncBtn = document.createElement('button');

            syncBtn.textContent = '🐙 Push to GitHub';

            syncBtn.style.cssText = 'background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc; border-radius: 4px; padding: 4px 10px; font-size: 11px; cursor: pointer; font-weight: 600;';

            syncBtn.addEventListener('click', async () => {

              syncBtn.disabled = true;

              syncBtn.textContent = 'Pushing...';

              try {

                const sRes = await fetch(`/api/bugs/${r.id}/sync-github`, {

                  method: 'POST',

                  headers: getAuthHeaders({ 'Content-Type': 'application/json' })

                });

                const sData = await sRes.json();

                if (sRes.ok) {

                  alert(`Created GitHub Issue #${sData.github_issue_number}!`);

                  fetchBugReports();

                } else {

                  alert(sData.detail || 'Failed to sync to GitHub.');

                }

              } catch (e) {

                alert('Error syncing to GitHub: ' + e.message);

              } finally {

                syncBtn.disabled = false;

              }

            });

            actionsRow.appendChild(syncBtn);

          }

          const delBtn = document.createElement('button');

          delBtn.textContent = '✓ Resolve & Archive';

          delBtn.style.cssText = 'background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4); color: #34d399; border-radius: 4px; padding: 4px 10px; font-size: 11px; cursor: pointer; font-weight: 600; margin-left: auto;';

          delBtn.addEventListener('click', async () => {

            if (!confirm(`Mark bug report from ${r.reporter} as resolved and archive it?`)) return;

            try {

              await fetch(`/api/bugs/${r.id}`, {

                method: 'DELETE',

                headers: getAuthHeaders({ 'Content-Type': 'application/json' })

              });

              fetchBugReports();

              updateHostBugBadge();

            } catch (e) {

              alert('Failed to resolve bug report.');

            }

          });

          actionsRow.appendChild(delBtn);

          item.appendChild(actionsRow);

          bugReportsList.appendChild(item);

        });

      }

      // --- 2. RENDER RESOLVED HISTORY ---

      if (bugResolvedList) {

        if (resolved.length === 0) {

          bugResolvedList.innerHTML = '<div style="color:#94a3b8; font-size:12px; padding:12px; text-align: center;">No resolved bug history yet.</div>';

        } else {

          bugResolvedList.innerHTML = '';

          resolved.forEach(r => {

            const item = document.createElement('div');

            item.className = 'host-bug-card';

            item.style.borderColor = 'rgba(52, 211, 153, 0.2)';

            

            const headerRow = document.createElement('div');

            headerRow.className = 'host-bug-card-top';

            headerRow.innerHTML = `

              <div style="display: flex; align-items: center; gap: 6px;">

                <span style="background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4); color: #34d399; font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px;">✓ RESOLVED</span>

                <span class="host-bug-badge">${escapeHtml(r.category || 'Bug')}</span>

                <strong style="color: #cbd5e1;">${escapeHtml(r.reporter || 'Tester')}</strong>

              </div>

              <span style="font-size: 10px; color: #64748b; font-family: monospace;">${r.resolved_at || r.created_at || ''}</span>

            `;

            item.appendChild(headerRow);

            const desc = document.createElement('div');

            desc.style.cssText = 'color: #94a3b8; font-size: 12px; line-height: 1.4; margin: 4px 0; text-decoration: line-through; opacity: 0.85;';

            desc.textContent = r.description;

            item.appendChild(desc);

            const previewImgUrl = r.screenshot_url || r.github_screenshot_url;

            if (previewImgUrl) {

              const shotRow = document.createElement('div');

              shotRow.style.cssText = 'display: flex; align-items: center; gap: 8px; margin: 4px 0; background: rgba(0,0,0,0.2); padding: 5px; border-radius: 6px;';

              shotRow.innerHTML = `

                <img src="${previewImgUrl}" style="width: 60px; height: 36px; object-fit: cover; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3); cursor: pointer;" title="Click to view archived screenshot" alt="Resolved Screenshot">

                <span style="font-size: 10px; color: #64748b; cursor: pointer;">Archived screenshot preview</span>

              `;

              shotRow.addEventListener('click', () => {

                if (typeof openLightbox === 'function') openLightbox(previewImgUrl);

              });

              item.appendChild(shotRow);

            }

            if (r.github_issue_url) {

              const actionsRow = document.createElement('div');

              actionsRow.className = 'host-bug-actions';

              const ghLink = document.createElement('a');

              ghLink.href = r.github_issue_url;

              ghLink.target = '_blank';

              ghLink.innerHTML = `🐙 Closed Issue #${r.github_issue_number || ''} &rarr;`;

              ghLink.style.cssText = 'display: inline-flex; align-items: center; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: #94a3b8; border-radius: 4px; padding: 3px 8px; font-size: 10.5px; text-decoration: none; font-weight: 500;';

              actionsRow.appendChild(ghLink);

              item.appendChild(actionsRow);

            }

            bugResolvedList.appendChild(item);

          });

        }

      }

    } catch (err) {

      bugReportsList.innerHTML = `<div style="color:#ef4444; font-size:12px;">Error: ${err.message}</div>`;

    }

  }

  // --------------------------------------------------------------------------

  // 12.5 PHASE 12: COMMAND PALETTE (CTRL+K), GAME SHIELD, STARTER CHIPS & EXPORT

  // --------------------------------------------------------------------------

  const cmdPaletteBtn = document.getElementById('cmd-palette-btn');

  const cmdPaletteModal = document.getElementById('cmd-palette-modal');

  const cmdPaletteInput = document.getElementById('cmd-palette-input');

  const cmdPaletteList = document.getElementById('cmd-palette-list');

  const gameShieldBtn = document.getElementById('game-shield-btn');

  const gameShieldModal = document.getElementById('game-shield-modal');

  const closeGameShieldBtn = document.getElementById('close-game-shield-modal');

  const gameShieldBadge = document.getElementById('game-shield-badge');

  const gameShieldCards = document.getElementById('game-shield-status-cards');

  const gameAudioList = document.getElementById('game-audio-sessions-list');

  const healAudioBtn = document.getElementById('heal-audio-btn');

  const artifactPreviewModal = document.getElementById('artifact-preview-modal');

  const closeArtifactPreviewBtn = document.getElementById('close-artifact-preview-modal');

  const artifactPreviewIframe = document.getElementById('artifact-preview-iframe');

  if (localStorage.getItem('libra_zen_mode') === '1') {

    document.body.classList.add('zen-mode');

  }

  function toggleZenMode() {

    document.body.classList.toggle('zen-mode');

    const isZen = document.body.classList.contains('zen-mode');

    localStorage.setItem('libra_zen_mode', isZen ? '1' : '0');

  }

  function exportCurrentSessionMarkdown() {

    if (!activeSessionId) return;

    window.open(`/api/sessions/${encodeURIComponent(activeSessionId)}/export`, '_blank');

  }

  async function openGameShieldModal() {

    if (!gameShieldModal) return;

    gameShieldModal.style.display = 'flex';

    await refreshGameShieldStatus();

  }

  async function refreshGameShieldStatus() {

    if (!gameShieldCards || !gameAudioList) return;

    try {

      const res = await fetch('/api/gaming/status', { headers: getAuthHeaders() });

      if (!res.ok) return;

      const data = await res.json();

      const activeGame = data.active_game;

      const isShield = data.gaming_shield_active;

      if (gameShieldBadge) {

        gameShieldBadge.textContent = isShield ? '🛡️ SHIELD ACTIVE' : 'DESKTOP MODE';

        gameShieldBadge.style.color = isShield ? '#10b981' : '#38bdf8';

      }

      const gameTitle = activeGame ? `${activeGame.app_label}` : 'No Active Game';

      const gameSub = activeGame ? `${activeGame.process_name} (${activeGame.memory_mb || 0} MB RAM)` : 'Scanning 30+ game engines';

      const overrideMode = data.override_mode || 'auto';
      gameShieldCards.innerHTML = `
        <div class="token-card highlight">
          <div class="token-card-header">DETECTED GAME</div>
          <div class="token-card-value" style="font-size: 18px; color: ${activeGame ? '#10b981' : '#94a3b8'};">${escapeHtml(gameTitle)}</div>
          <div class="token-card-sub">${escapeHtml(gameSub)}</div>
          ${activeGame ? `<button id="kill-game-proc-btn" class="modal-btn secondary" style="margin-top: 8px; font-size: 11px; padding: 4px 10px; color: #f43f5e; border-color: rgba(244,63,94,0.3); width: 100%;">🧹 Kill Zombie Process (${escapeHtml(activeGame.process_name)})</button>` : ''}
        </div>
        <div class="token-card">
          <div class="token-card-header">SHIELD OVERRIDE MODE</div>
          <div class="gaming-mode-pills">
            <button class="gaming-mode-btn ${overrideMode === 'auto' ? 'active' : ''}" data-mode="auto">🟢 Auto</button>
            <button class="gaming-mode-btn ${overrideMode === 'on' ? 'active' : ''}" data-mode="on">⚡ Force On</button>
            <button class="gaming-mode-btn ${overrideMode === 'off' ? 'active mode-off' : ''}" data-mode="off">⏸ Standby</button>
          </div>
          <div class="token-card-sub" style="margin-top: 8px;">Threshold: ${data.wake_threshold} | ${escapeHtml(data.agc_status)}</div>
        </div>
      `;

      // Attach mode switcher listeners
      gameShieldCards.querySelectorAll('.gaming-mode-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const mode = btn.getAttribute('data-mode');
          await fetch('/api/gaming/toggle', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ mode })
          });
          renderGamingStatus();
        });
      });

      // Attach kill process listener
      const killProcBtn = document.getElementById('kill-game-proc-btn');
      if (killProcBtn && activeGame) {
        killProcBtn.addEventListener('click', async () => {
          killProcBtn.textContent = 'Killing...';
          await fetch('/api/gaming/kill-process', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ process_name: activeGame.process_name, pid: activeGame.pid })
          });
          setTimeout(renderGamingStatus, 600);
        });
      }

      const sessions = data.audio_sessions || [];

      if (sessions.length === 0) {

        gameAudioList.innerHTML = '<div style="color: #64748b; font-size: 12px;">No active audio sessions found.</div>';

      } else {

        gameAudioList.innerHTML = sessions.map(s => `

          <div class="audio-session-row">

            <div>

              <strong style="color: ${s.protected ? '#10b981' : '#f1f5f9'};">${escapeHtml(s.process)}</strong>

              ${s.protected ? '<span style="font-size: 10px; color: #10b981; margin-left: 6px;">[GAME PROTECTED]</span>' : ''}

            </div>

            <span style="font-family: monospace; color: ${s.volume_percent < 100 ? '#f59e0b' : '#00f2fe'};">${s.volume_percent}%</span>

          </div>

        `).join('');

      }

    } catch (e) {

      console.warn('Error loading gaming status:', e);

    }

  }

  if (gameShieldBtn) gameShieldBtn.addEventListener('click', openGameShieldModal);

  if (closeGameShieldBtn) {

    closeGameShieldBtn.addEventListener('click', () => {

      if (gameShieldModal) gameShieldModal.style.display = 'none';

    });

  }

  if (healAudioBtn) {

    healAudioBtn.addEventListener('click', async () => {

      healAudioBtn.textContent = 'RESTORING...';

      try {

        await fetch('/api/gaming/heal-audio', { method: 'POST', headers: getAuthHeaders() });

        await refreshGameShieldStatus();

        healAudioBtn.textContent = '✓ ALL AT 100%';

        setTimeout(() => { healAudioBtn.textContent = '🔊 RESTORE ALL TO 100%'; }, 1800);

      } catch (e) {

        healAudioBtn.textContent = '🔊 RESTORE ALL TO 100%';

      }

    });

  }

  // Live HTML/SVG Code Block Artifact Preview

  document.addEventListener('click', (e) => {

    if (e.target && e.target.classList.contains('preview-code-btn')) {

      const encoded = e.target.getAttribute('data-code');

      if (encoded && artifactPreviewModal && artifactPreviewIframe) {

        artifactPreviewIframe.srcdoc = decodeURIComponent(encoded);

        artifactPreviewModal.style.display = 'flex';

      }

    }

  });

  if (closeArtifactPreviewBtn) {

    closeArtifactPreviewBtn.addEventListener('click', () => {

      if (artifactPreviewModal) artifactPreviewModal.style.display = 'none';

    });

  }

  // Command Palette Actions (Inspired by Raycast AI / Open WebUI)

  const COMMAND_ACTIONS = [

    { icon: '🎯', title: 'Autonomous Goal Execution', desc: 'Execute a multi-step autonomous goal (/goal)', shortcut: '/goal', run: () => { const inp = document.getElementById('prompt-input'); if (inp) { inp.value = '/goal '; inp.focus(); } } },
    { icon: '🖥️', title: 'Show PC GUI Window', desc: 'Bring the full futuristic Libra voice assistant onto your PC monitor', shortcut: '/show', run: async () => { await fetch('/api/gui/show', { method: 'POST', headers: getAuthHeaders() }); } },
    { icon: '🫥', title: 'Hide PC GUI Window', desc: 'Hide the interface and let Libra run silently in the background', shortcut: '/hide', run: async () => { await fetch('/api/gui/hide', { method: 'POST', headers: getAuthHeaders() }); } },
    { icon: '🎮', title: 'Gaming & Audio Shield Control', desc: 'Inspect active game & toggle audio/VRAM shield', shortcut: '/game', run: () => openGameShieldModal() },
    { icon: '📊', title: 'GPU & Hardware Telemetry HUD', desc: 'Live RTX 5060 Ti VRAM gauge, temperature & load', shortcut: '/vitals', run: () => toggleTokenModal(true) },
    { icon: '🧠', title: 'Core Memory & Knowledge Base', desc: 'View learned facts, habits & personal preferences', shortcut: '/memory', run: () => { if (vaultNavBtn) vaultNavBtn.click(); } },

    { icon: '🔊', title: 'Heal & Restore All App Audio to 100%', desc: 'Immediately restore all Windows WASAPI audio sessions to 100%', shortcut: '/heal', run: async () => { await fetch('/api/gaming/heal-audio', { method: 'POST', headers: getAuthHeaders() }); openGameShieldModal(); } },

    { icon: '⚡', title: 'Daily Tactical Briefing', desc: 'Weather rain forecast, RTX GPU vitals & schedule summary', shortcut: '/briefing', run: () => { if (briefingNavBtn) briefingNavBtn.click(); } },

    { icon: '◈', title: 'Obsidian Memory Vault', desc: 'Search, pin, or add persistent markdown memories (BM25 FTS5)', shortcut: '/vault', run: () => { if (vaultNavBtn) vaultNavBtn.click(); } },

    { icon: '✈', title: 'AirDrop Bridge (Phone ⟷ PC)', desc: 'Send files from mobile directly to PC Downloads/LibraDrop', shortcut: '/drop', run: () => { if (airdropNavBtn) airdropNavBtn.click(); } },

    { icon: '📥', title: 'Export Conversation to Markdown (.md)', desc: 'Download current chat thread with tool badges & metrics', shortcut: '/export', run: () => exportCurrentSessionMarkdown() },

    { icon: '🧘', title: 'Toggle Zen Focus Mode', desc: 'Collapse/expand the 3D WebGL Orb for maximum reading space', shortcut: '/zen', run: () => toggleZenMode() },

    { icon: '📊', title: 'GPU Token Telemetry HUD', desc: 'Inspect qwen3:8b tokens/sec and Markovian saved tokens', shortcut: '/tokens', run: () => { if (tokenHudBtn) tokenHudBtn.click(); } },

    { icon: '➕', title: 'Start New Conversation Thread', desc: 'Create a fresh isolated chat session', shortcut: '/new', run: () => createNewSession() }

  ];

  let selectedCmdIdx = 0;

  let filteredCommands = [...COMMAND_ACTIONS];

  function renderCommandPalette(filterText = '') {

    if (!cmdPaletteList) return;

    const q = (filterText || '').toLowerCase().trim();

    filteredCommands = COMMAND_ACTIONS.filter(c =>

      !q || c.title.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q) || c.shortcut.toLowerCase().includes(q)

    );

    selectedCmdIdx = 0;

    cmdPaletteList.innerHTML = filteredCommands.map((c, idx) => `

      <div class="cmd-item ${idx === selectedCmdIdx ? 'selected' : ''}" data-idx="${idx}">

        <div class="cmd-item-left">

          <span class="cmd-item-icon">${c.icon}</span>

          <div>

            <div class="cmd-item-title">${escapeHtml(c.title)}</div>

            <div class="cmd-item-desc">${escapeHtml(c.desc)}</div>

          </div>

        </div>

        <span class="cmd-item-shortcut">${escapeHtml(c.shortcut)}</span>

      </div>

    `).join('');

    cmdPaletteList.querySelectorAll('.cmd-item').forEach(el => {

      el.addEventListener('click', () => {

        const i = parseInt(el.getAttribute('data-idx'), 10);

        if (filteredCommands[i]) {

          closeCommandPalette();

          filteredCommands[i].run();

        }

      });

    });

  }

  function openCommandPalette(initialFilter = '') {

    if (!cmdPaletteModal) return;

    cmdPaletteModal.style.display = 'flex';

    if (cmdPaletteInput) {

      cmdPaletteInput.value = initialFilter;

      renderCommandPalette(initialFilter);

      setTimeout(() => cmdPaletteInput.focus(), 50);

    }

  }

  function closeCommandPalette() {

    if (cmdPaletteModal) cmdPaletteModal.style.display = 'none';

  }

  if (cmdPaletteBtn) cmdPaletteBtn.addEventListener('click', () => openCommandPalette(''));

  if (cmdPaletteModal) {

    cmdPaletteModal.addEventListener('click', (e) => {

      if (e.target === cmdPaletteModal) closeCommandPalette();

    });

  }

  if (cmdPaletteInput) {

    cmdPaletteInput.addEventListener('input', (e) => renderCommandPalette(e.target.value));

    cmdPaletteInput.addEventListener('keydown', (e) => {

      if (e.key === 'Escape') {

        closeCommandPalette();

      } else if (e.key === 'ArrowDown') {

        e.preventDefault();

        if (filteredCommands.length > 0) {

          selectedCmdIdx = (selectedCmdIdx + 1) % filteredCommands.length;

          cmdPaletteList.querySelectorAll('.cmd-item').forEach((el, i) => el.classList.toggle('selected', i === selectedCmdIdx));

        }

      } else if (e.key === 'ArrowUp') {

        e.preventDefault();

        if (filteredCommands.length > 0) {

          selectedCmdIdx = (selectedCmdIdx - 1 + filteredCommands.length) % filteredCommands.length;

          cmdPaletteList.querySelectorAll('.cmd-item').forEach((el, i) => el.classList.toggle('selected', i === selectedCmdIdx));

        }

      } else if (e.key === 'Enter') {

        e.preventDefault();

        if (filteredCommands[selectedCmdIdx]) {

          const act = filteredCommands[selectedCmdIdx];

          closeCommandPalette();

          act.run();

        }

      }

    });

  }

  document.addEventListener('keydown', (e) => {

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {

      if (currentUserRole !== 'host') return; // Don't trigger host command palette for tester

      e.preventDefault();

      if (cmdPaletteModal && cmdPaletteModal.style.display === 'flex') {

        closeCommandPalette();

      } else {

        openCommandPalette('');

      }

    }

  });

  function renderStarterChips() {

    if (!chatContainer) return;

    const existingHero = document.getElementById('empty-chat-hero');

    if (existingHero) existingHero.remove();

    const hero = document.createElement('div');

    hero.id = 'empty-chat-hero';

    hero.className = 'empty-chat-hero';

    if (currentUserRole === 'host') {

      hero.innerHTML = `

        <h1 class="hero-title">What can I help with today?</h1>

        <p class="hero-subtitle">Ask questions, analyze documents, inspect code, or manage your workstation.</p>

        <div class="starter-chips-grid">

          <div class="starter-chip-card" data-prompt="Good morning Libra, give me my daily tactical briefing">

            <div class="starter-chip-title">⚡ Daily Morning Briefing</div>

            <div class="starter-chip-desc">Weather in KL, PC storage, uncommitted git files &amp; action items</div>

          </div>

          <div class="starter-chip-card" data-prompt="What is the latest NBA basketball news and Premier League sports updates today?">

            <div class="starter-chip-title">🏀 Live Sports &amp; NBA News</div>

            <div class="starter-chip-desc">Latest scores, trades, standings and verified sports headlines</div>

          </div>

          <div class="starter-chip-card" data-prompt="Review my current uncommitted git changes across the workspace and tell me what needs attention">

            <div class="starter-chip-title">💻 Review Uncommitted Code</div>

            <div class="starter-chip-desc">Inspect modified files, syntax checks &amp; diff analysis</div>

          </div>

          <div class="starter-chip-card" data-prompt="Search my core memory and knowledge base for my key notes, user preferences, and pinned facts">

            <div class="starter-chip-title">📁 Core Memory & Knowledge Search</div>

            <div class="starter-chip-desc">Explore persistent notes, BM25 memory index &amp; preferences</div>

          </div>

        </div>

      `;

    } else {

      hero.innerHTML = `

        <h1 class="hero-title">What can I help with today?</h1>

        <p class="hero-subtitle">Ask questions, review documents, test AI capabilities, or report feedback.</p>

        <div class="starter-chips-grid">

          <div class="starter-chip-card" data-prompt="Hello Libra! What capabilities can I test today?">

            <div class="starter-chip-title">✦ Explore Capabilities</div>

            <div class="starter-chip-desc">Overview of vision, reasoning, web research and coding tools</div>

          </div>

          <div class="starter-chip-card" data-prompt="What is the latest breaking news and trends today?">

            <div class="starter-chip-title">🏀 Today's Top News &amp; Trends</div>

            <div class="starter-chip-desc">Real-time live news, sports, tech updates &amp; citations</div>

          </div>

          <div class="starter-chip-card" data-prompt="Explain this programming or math concept with step-by-step examples">

            <div class="starter-chip-title">🧠 Logic &amp; Coding Help</div>

            <div class="starter-chip-desc">Generate code snippets, algorithms, and technical solutions</div>

          </div>

          <div class="starter-chip-card" data-action="open-bug">

            <div class="starter-chip-title">🐞 Report Issue &amp; Feedback</div>

            <div class="starter-chip-desc">File a bug report with auto-captured screenshot to GitHub</div>

          </div>

        </div>

      `;

    }

    hero.querySelectorAll('.starter-chip-card').forEach(card => {

      card.addEventListener('click', () => {

        const act = card.getAttribute('data-action');

        const p = card.getAttribute('data-prompt');

        if (act === 'cmd-palette' && typeof openCommandPalette === 'function') {

          openCommandPalette('');

        } else if (act === 'open-bug' && typeof openBugModal === 'function') {

          openBugModal();

        } else if (p && promptInput && sendBtn) {

          promptInput.value = p;

          sendBtn.click();

        }

      });

    });

    chatContainer.appendChild(hero);

  }

  // --------------------------------------------------------------------------

  // 12.7 PHASE 12: UNIFIED OPTIONS, CUSTOM INSTRUCTIONS & GITHUB SYNC

  // --------------------------------------------------------------------------

  const optionsNavBtn = document.getElementById('options-nav-btn');

  const optionsModal = document.getElementById('options-modal');

  const closeOptionsModalBtn = document.getElementById('close-options-modal');

  const profNameInput = document.getElementById('prof-name-input');

  const profLocationInput = document.getElementById('prof-location-input');

  const profAboutInput = document.getElementById('prof-about-input');

  const profInstructionsInput = document.getElementById('prof-instructions-input');

  const profInterestsInput = document.getElementById('prof-interests-input');

  const profStatusMsg = document.getElementById('prof-status-msg');

  const saveProfileBtn = document.getElementById('save-profile-btn');

  const optionsGhRepoInput = document.getElementById('options-gh-repo-input');

  const optionsGhTokenInput = document.getElementById('options-gh-token-input');

  const optionsGhStatusIndicator = document.getElementById('options-gh-status-indicator');

  const optionsGhStatusMsg = document.getElementById('options-gh-status-msg');

  const saveGhConfigBtn = document.getElementById('save-gh-config-btn');

  const syncPendingGhBtn = document.getElementById('sync-pending-gh-btn');

  const quickCreateInviteBtn = document.getElementById('quick-create-invite-btn');

  const copyPublicUrlBtn = document.getElementById('copy-public-url-btn');

  const optionsPublicUrl = document.getElementById('options-public-url');

  const optionsNewInviteBox = document.getElementById('options-new-invite-box');

  const optionsGeneratedInviteUrl = document.getElementById('options-generated-invite-url');

  const optionsCopyGeneratedBtn = document.getElementById('options-copy-generated-btn');

  const optionsUsersList = document.getElementById('options-users-list');

  // Options Tabs Switching

  document.querySelectorAll('.options-tab-btn').forEach(btn => {

    btn.addEventListener('click', () => {

      document.querySelectorAll('.options-tab-btn').forEach(b => b.classList.remove('active'));

      document.querySelectorAll('.options-tab-content').forEach(c => c.style.display = 'none');

      btn.classList.add('active');

      const targetId = btn.getAttribute('data-tab');

      const target = document.getElementById(targetId);

      if (target) target.style.display = 'block';

    });

  });

  async function loadUserProfile() {

    try {

      const res = await fetch('/api/user/profile', { headers: getAuthHeaders() });

      if (res.ok) {

        const data = await res.json();

        const prof = data.profile || {};

        if (profNameInput) profNameInput.value = prof.display_name || (currentUserRole === 'host' ? 'Chen Xuan' : '');

        if (profLocationInput) profLocationInput.value = prof.location || 'Kuala Lumpur';

        if (profAboutInput) profAboutInput.value = prof.about_user || (currentUserRole === 'host' ? 'Software engineer and master architect of Project Libra.' : '');

        if (profInstructionsInput) profInstructionsInput.value = prof.custom_instructions || (currentUserRole === 'host' ? 'Be sharp, articulate, concise, and subtly witty. No robotic corporate filler.' : '');

        if (profInterestsInput) profInterestsInput.value = prof.interests || (currentUserRole === 'host' ? 'AI, Python, Cybernetics, RTX GPUs, Basketball' : '');

      }

    } catch (e) {}

  }

  async function saveUserProfile() {

    if (!saveProfileBtn) return;

    saveProfileBtn.disabled = true;

    saveProfileBtn.textContent = 'Saving...';

    try {

      const payload = {

        display_name: profNameInput ? profNameInput.value.trim() : '',

        location: profLocationInput ? profLocationInput.value.trim() : 'Kuala Lumpur',

        about_user: profAboutInput ? profAboutInput.value.trim() : '',

        custom_instructions: profInstructionsInput ? profInstructionsInput.value.trim() : '',

        interests: profInterestsInput ? profInterestsInput.value.trim() : ''

      };

      const res = await fetch('/api/user/profile', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify(payload)

      });

      const data = await res.json();

      if (res.ok) {

        if (profStatusMsg) {

          profStatusMsg.textContent = '✨ Profile & Custom Instructions saved to Libra!';

          profStatusMsg.style.color = '#34d399';

          profStatusMsg.style.display = 'block';

          setTimeout(() => { if (profStatusMsg) profStatusMsg.style.display = 'none'; }, 4000);

        }

        if (payload.display_name && userEmailText) {

          userEmailText.textContent = payload.display_name;

        }

      } else {

        if (profStatusMsg) {

          profStatusMsg.textContent = data.detail || 'Failed to save profile.';

          profStatusMsg.style.color = '#f87171';

          profStatusMsg.style.display = 'block';

        }

      }

    } catch (e) {

      if (profStatusMsg) {

        profStatusMsg.textContent = 'Network error saving profile.';

        profStatusMsg.style.color = '#f87171';

        profStatusMsg.style.display = 'block';

      }

    } finally {

      saveProfileBtn.disabled = false;

      saveProfileBtn.textContent = '💾 SAVE PROFILE & CUSTOM INSTRUCTIONS';

    }

  }

  async function loadGitHubConfig() {
    try {
      const res = await fetch('/api/github/config', { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        if (optionsGhRepoInput && data.repo) optionsGhRepoInput.value = data.repo;
        if (optionsGhStatusIndicator) {
          if (data.has_token) {
            optionsGhStatusIndicator.innerHTML = '<span style="color: #34d399; font-weight: 600;">● Connected (GitHub PAT Active — Automatic Issue Creation Online)</span>';
          } else {
            optionsGhStatusIndicator.innerHTML = '<span style="color: #fb7185; font-weight: 600;">● No Token Configured (Paste your GitHub PAT below to auto-post issues)</span>';
          }
        }
      } else {
        if (optionsGhStatusIndicator) {
          optionsGhStatusIndicator.innerHTML = '<span style="color: #fb7185; font-weight: 600;">● Unable to connect to GitHub service</span>';
        }
      }
    } catch (e) {
      if (optionsGhStatusIndicator) {
        optionsGhStatusIndicator.innerHTML = '<span style="color: #fb7185; font-weight: 600;">● Connection Error</span>';
      }
    }
  }

  async function saveGitHubConfig() {

    if (!saveGhConfigBtn || !optionsGhTokenInput) return;

    const token = optionsGhTokenInput.value.trim();

    const repo = optionsGhRepoInput ? optionsGhRepoInput.value.trim() : 'Xuan09-30/LibraAi';

    if (!token) {

      alert('Please enter your GitHub Personal Access Token.');

      return;

    }

    saveGhConfigBtn.disabled = true;

    saveGhConfigBtn.textContent = 'Saving...';

    try {

      const res = await fetch('/api/github/config', {

        method: 'POST',

        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

        body: JSON.stringify({ token: token, repo: repo })

      });

      const data = await res.json();

      if (res.ok) {

        if (optionsGhStatusMsg) {

          optionsGhStatusMsg.textContent = '🎉 GitHub Token saved! Bug reports will now auto-create issues on GitHub!';

          optionsGhStatusMsg.style.color = '#34d399';

          optionsGhStatusMsg.style.display = 'block';

          setTimeout(() => { if (optionsGhStatusMsg) optionsGhStatusMsg.style.display = 'none'; }, 5000);

        }

        loadGitHubConfig();

      } else {

        if (optionsGhStatusMsg) {

          optionsGhStatusMsg.textContent = data.detail || 'Failed to save GitHub token.';

          optionsGhStatusMsg.style.color = '#f87171';

          optionsGhStatusMsg.style.display = 'block';

        }

      }

    } catch (e) {

      alert('Network error saving GitHub token.');

    } finally {

      saveGhConfigBtn.disabled = false;

      saveGhConfigBtn.textContent = '💾 SAVE GITHUB TOKEN';

    }

  }

  async function syncPendingReportsToGitHub() {

    if (!syncPendingGhBtn) return;

    syncPendingGhBtn.disabled = true;

    syncPendingGhBtn.textContent = 'Syncing to GitHub...';

    try {

      const bRes = await fetch('/api/bugs', { headers: getAuthHeaders() });

      if (!bRes.ok) throw new Error('Could not fetch reports');

      const bData = await bRes.json();

      const reports = bData.reports || [];

      const pending = reports.filter(r => !r.github_issue_url || r.github_issue_url.includes('/issues/new'));

      if (pending.length === 0) {

        alert('All bug reports are already posted to GitHub!');

        return;

      }

      let syncedCount = 0;

      for (const r of pending) {

        const sRes = await fetch(`/api/bugs/${r.id}/sync-github`, {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' })

        });

        if (sRes.ok) syncedCount++;

      }

      alert(`🎉 Successfully created ${syncedCount} new issue(s) on GitHub!`);

      fetchBugReports();

    } catch (e) {

      alert('Error syncing to GitHub: ' + e.message);

    } finally {

      syncPendingGhBtn.disabled = false;

      syncPendingGhBtn.textContent = '🚀 Push Reports to GitHub';

    }

  }

  async function loadOptionsUsersList() {

    if (!optionsUsersList) return;

    try {

      const res = await fetch('/api/users', { headers: getAuthHeaders() });

      if (res.ok) {

        const data = await res.json();

        const users = data.users || [];

        optionsUsersList.innerHTML = '';

        users.forEach(u => {
          const item = document.createElement('div');
          const isMainHost = u.is_primary_host;
          const initial = (u.display_name || u.email || 'U')[0].toUpperCase();
          const avatarClass = u.role === 'host' ? 'avatar-host' : 'avatar-tester';
          const badgeClass = u.role === 'host' ? 'host' : 'guest';
          item.className = `user-row-item ${isMainHost ? 'is-main-host' : (u.role === 'host' ? 'is-host' : 'is-tester')}`;
          item.style.marginBottom = '6px';
          item.innerHTML = `
            <div class="user-row-left">
              <div class="user-row-avatar ${avatarClass}">${initial}</div>
              <div class="user-row-info">
                <div class="user-row-name">
                  <span>${escapeHtml(u.display_name || u.email.split('@')[0])}</span>
                  ${isMainHost ? '<span class="primary-host-tag">MAIN HOST</span>' : ''}
                </div>
                <div class="user-row-email">${escapeHtml(u.email)}</div>
              </div>
            </div>
            <div class="user-row-right">
              <span class="role-badge ${badgeClass}">${u.role.toUpperCase()}</span>
            </div>
          `;
          optionsUsersList.appendChild(item);
        });

      }

    } catch (e) {}

  }

  function openOptionsModal(targetTab = null) {

    if (!optionsModal) return;

    optionsModal.style.display = 'flex';

    loadUserProfile();

    if (currentUserRole === 'host') {

      loadGitHubConfig();

      loadOptionsUsersList();

      document.querySelectorAll('.options-tab-btn.host-only-btn').forEach(b => b.style.display = 'inline-block');

    } else {

      document.querySelectorAll('.options-tab-btn.host-only-btn').forEach(b => b.style.display = 'none');

    }

    if (targetTab) {

      const btn = document.querySelector(`.options-tab-btn[data-tab="${targetTab}"]`);

      if (btn) btn.click();

    }

  }

  function closeOptionsModal() {
    registerModalClosed();
    if (optionsModal) optionsModal.style.display = 'none';
  }

  if (optionsNavBtn) {
    optionsNavBtn.addEventListener('click', (e) => {
      if (isGhostClickFromModalClose()) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      openOptionsModal('tab-profile');
    });
  }

  if (closeOptionsModalBtn) {
    closeOptionsModalBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      closeOptionsModal();
    });
  }

  // Voice Speech Listeners

  const voiceToggleEl = document.getElementById('voice-speech-toggle');

  if (voiceToggleEl) {

    voiceToggleEl.addEventListener('change', (e) => {

      setVoiceSpeechEnabled(e.target.checked);

    });

  }

  const quickVoiceToggleBtn = document.getElementById('quick-voice-toggle-btn');

  if (quickVoiceToggleBtn) {

    quickVoiceToggleBtn.addEventListener('click', () => {

      setVoiceSpeechEnabled(!isVoiceSpeechEnabled());

    });

  }

  const optionsVoiceToggle = document.getElementById('options-voice-toggle');

  if (optionsVoiceToggle) {

    optionsVoiceToggle.checked = isVoiceSpeechEnabled();

    optionsVoiceToggle.addEventListener('change', () => {

      setVoiceSpeechEnabled(optionsVoiceToggle.checked);

    });

  }

  // Clean Google sign-in active

  updateVoiceSpeechUI();

  if (saveProfileBtn) saveProfileBtn.addEventListener('click', saveUserProfile);

  if (saveGhConfigBtn) saveGhConfigBtn.addEventListener('click', saveGitHubConfig);

  if (syncPendingGhBtn) syncPendingGhBtn.addEventListener('click', syncPendingReportsToGitHub);

  if (copyPublicUrlBtn && optionsPublicUrl) {

    copyPublicUrlBtn.addEventListener('click', () => {

      navigator.clipboard.writeText(optionsPublicUrl.value).then(() => {

        copyPublicUrlBtn.textContent = 'Copied!';

        setTimeout(() => { copyPublicUrlBtn.textContent = 'Copy'; }, 2000);

      });

    });

  }

  if (quickCreateInviteBtn) {

    quickCreateInviteBtn.addEventListener('click', async () => {

      quickCreateInviteBtn.disabled = true;

      quickCreateInviteBtn.textContent = 'Generating...';

      try {

        const res = await fetch('/api/tokens/guest', {

          method: 'POST',

          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),

          body: JSON.stringify({ label: 'Friend Quick Invite' })

        });

        const data = await res.json();

        if (res.ok) {

          const inviteUrl = data.cloudflare_invite_url || data.invite_url || (optionsPublicUrl.value + '/?token=' + data.token);

          if (optionsGeneratedInviteUrl) optionsGeneratedInviteUrl.value = inviteUrl;

          if (optionsNewInviteBox) optionsNewInviteBox.style.display = 'block';

        } else {

          alert('Failed to generate invite token.');

        }

      } catch (e) {

        alert('Network error generating invite.');

      } finally {

        quickCreateInviteBtn.disabled = false;

        quickCreateInviteBtn.textContent = '⚡ GENERATE NEW GUEST INVITE LINK';

      }

    });

  }

  if (optionsCopyGeneratedBtn && optionsGeneratedInviteUrl) {

    optionsCopyGeneratedBtn.addEventListener('click', () => {

      navigator.clipboard.writeText(optionsGeneratedInviteUrl.value).then(() => {

        optionsCopyGeneratedBtn.textContent = 'Copied!';

        setTimeout(() => { optionsCopyGeneratedBtn.textContent = 'Copy'; }, 2000);

      });

    });

  }

  // Hook up drawer host deck items

  const drawerBriefingBtn = document.getElementById('briefing-nav-btn');

  const drawerVaultBtn = document.getElementById('vault-nav-btn');

  const drawerAirdropBtn = document.getElementById('airdrop-nav-btn');

  const drawerGameShieldBtn = document.getElementById('game-shield-btn');

  const drawerCmdBtn = document.getElementById('cmd-palette-btn');

  const drawerInviteBtn = document.getElementById('invite-nav-btn');

  const drawerUsersBtn = document.getElementById('users-nav-btn');

  if (drawerInviteBtn) {

    drawerInviteBtn.addEventListener('click', () => {

      openOptionsModal('tab-invites');

    });

  }

  if (drawerUsersBtn) {

    drawerUsersBtn.addEventListener('click', () => {

      toggleDrawer(false);

      showUsersModal();

    });

  }

  // --------------------------------------------------------------------------

  // 13. BOOTSTRAP INITIALIZATION

  // --------------------------------------------------------------------------

  // ==========================================================================

  // VERCEL INTERFACE GUIDELINES: MODAL ERGONOMICS (ESCAPE & BACKDROP DISMISSAL)

  // ==========================================================================

  document.addEventListener('keydown', (e) => {

    if (e.key === 'Escape') {
      registerModalClosed();
      const overlays = document.querySelectorAll('.modal-overlay');

      overlays.forEach(m => {

        if (m.style.display === 'flex' || m.classList.contains('active')) {

          m.style.display = 'none';

          m.classList.remove('active');

        }

      });

      const lightbox = document.getElementById('image-lightbox');

      if (lightbox) lightbox.style.display = 'none';

    }

  });

  document.querySelectorAll('.modal-overlay').forEach(modal => {

    modal.addEventListener('click', (e) => {

      if (e.target === modal) {
        registerModalClosed();
        modal.style.display = 'none';

        modal.classList.remove('active');

      }

    });

  });

  initOrb();

  fetchVitals();

  initAuthAndRole();

  fetchSessions().then(() => {

    // Switch to active session or the newest session

    if (sessionsList.length > 0) {

      const match = sessionsList.find(s => s.session_id === activeSessionId);

      const target = match ? match : sessionsList[0];

      switchSession(target.session_id, target.title);

    } else {

      createNewSession();

    }

  });

  // Bind Telemetry buttons (Drawer & Options modal)

  const drawerTelemetryBtn = document.getElementById('drawer-token-telemetry-btn');

  if (drawerTelemetryBtn) {

    drawerTelemetryBtn.addEventListener('click', () => {

      toggleDrawer(false);

      toggleTokenModal(true);

      fetchTokenSummary();

    });

  }

  const optionsTelemetryBtn = document.getElementById('options-token-telemetry-btn');

  if (optionsTelemetryBtn) {

    optionsTelemetryBtn.addEventListener('click', () => {

      if (optionsModal) optionsModal.style.display = 'none';

      toggleTokenModal(true);

      fetchTokenSummary();

    });

  }


  // Modal handlers for clean Auth Modal (Close, Token, Guest)
  const closeAuthModalBtn = document.getElementById('close-auth-modal-btn');
  if (closeAuthModalBtn) {
    closeAuthModalBtn.addEventListener('click', () => hideAuthModal());
  }

  const authModalTokenBtn = document.getElementById('auth-modal-token-btn');
  const authModalTokenInput = document.getElementById('auth-modal-token-input');
  if (authModalTokenBtn && authModalTokenInput) {
    authModalTokenBtn.addEventListener('click', async () => {
      const tok = authModalTokenInput.value.trim();
      if (!tok) return;
      authToken = tok;
      localStorage.setItem('libra_token', tok);
      document.cookie = `libra_auth=${tok}; path=/; max-age=2592000; SameSite=Lax`;
      hideAuthModal();
      await initAuthAndRole();
      fetchSessions();
      fetchVitals();
      fetchTokenSummary();
      loadUserProfile();
    });
    authModalTokenInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') authModalTokenBtn.click();
    });
  }

  const authModalGuestBtn = document.getElementById('auth-modal-guest-btn');
  if (authModalGuestBtn) {
    authModalGuestBtn.addEventListener('click', async () => {
      authToken = '';
      localStorage.removeItem('libra_token');
      document.cookie = 'libra_auth=; path=/; max-age=0; SameSite=Lax';
      hideAuthModal();
      await initAuthAndRole();
      fetchSessions();
      fetchVitals();
      fetchTokenSummary();
    });
  }

  const userProfileBadgeEl = document.getElementById('user-profile-badge');
  if (userProfileBadgeEl) {
    userProfileBadgeEl.style.cursor = 'pointer';
    userProfileBadgeEl.addEventListener('click', (e) => {
      if (e.target.closest('#sign-out-btn') || e.target.closest('#manage-users-drawer-btn')) return;
      showAuthModal();
    });
  }

  const headerRoleBadgeEl = document.getElementById('role-badge');
  if (headerRoleBadgeEl) {
    headerRoleBadgeEl.style.cursor = 'pointer';
    headerRoleBadgeEl.addEventListener('click', () => {
      showAuthModal();
    });
  }

  // --------------------------------------------------------------------------
  // ANTIGRAVITY-STYLE SLASH COMMAND POPUP MENU CONTROLLER
  // --------------------------------------------------------------------------
  const slashPopover = document.getElementById('slash-command-popover');
  const slashList = document.getElementById('slash-command-list');
  let selectedSlashIdx = 0;
  let activeSlashMatches = [];

  function updateSlashPopover() {
    if (!slashPopover || !slashList || !promptInput) return;
    const val = promptInput.value;
    if (val.startsWith('/')) {
      const query = val.slice(1).toLowerCase().trim();
      activeSlashMatches = COMMAND_ACTIONS.filter(c => 
        !query || c.shortcut.toLowerCase().includes(query) || c.title.toLowerCase().includes(query) || c.desc.toLowerCase().includes(query)
      );
      if (activeSlashMatches.length > 0) {
        selectedSlashIdx = Math.min(selectedSlashIdx, activeSlashMatches.length - 1);
        slashList.innerHTML = activeSlashMatches.map((c, i) => `
          <div class="cmd-item ${i === selectedSlashIdx ? 'selected' : ''}" data-slash-idx="${i}">
            <div class="cmd-item-left">
              <span class="cmd-item-icon">${c.icon}</span>
              <div>
                <div class="cmd-item-title">${escapeHtml(c.title)}</div>
                <div class="cmd-item-desc">${escapeHtml(c.desc)}</div>
              </div>
            </div>
            <span class="cmd-item-shortcut">${escapeHtml(c.shortcut)}</span>
          </div>
        `).join('');

        slashList.querySelectorAll('.cmd-item').forEach(el => {
          el.addEventListener('click', () => {
            const idx = parseInt(el.getAttribute('data-slash-idx'), 10);
            executeSlashCommand(idx);
          });
        });

        slashPopover.style.display = 'flex';
        return;
      }
    }
    slashPopover.style.display = 'none';
  }

  function executeSlashCommand(idx) {
    const cmd = activeSlashMatches[idx];
    if (!cmd) return;
    if (slashPopover) slashPopover.style.display = 'none';
    if (promptInput) promptInput.value = '';
    cmd.run();
  }

  if (promptInput) {
    promptInput.addEventListener('input', () => updateSlashPopover());
    promptInput.addEventListener('keydown', (e) => {
      if (slashPopover && slashPopover.style.display === 'flex') {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          selectedSlashIdx = (selectedSlashIdx + 1) % activeSlashMatches.length;
          updateSlashPopover();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          selectedSlashIdx = (selectedSlashIdx - 1 + activeSlashMatches.length) % activeSlashMatches.length;
          updateSlashPopover();
        } else if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          executeSlashCommand(selectedSlashIdx);
        } else if (e.key === 'Escape') {
          e.preventDefault();
          slashPopover.style.display = 'none';
        }
      }
    });
  }

})();

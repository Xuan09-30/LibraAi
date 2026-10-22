/**
 * ============================================================================
 * PROJECT LIBRA // PWA CLIENT APPLICATION (PHASE 10)
 * Gemini-Style Multi-Chat, Real-Time Token Telemetry, Three.js Orb & Voice
 * ============================================================================
 */

(function () {
  'use strict';

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
  const sessionListContainer = document.getElementById('session-list');
  const activeThreadTitleEl = document.getElementById('active-thread-title');

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
  const remoteAudio = document.getElementById('remote-audio');

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
    idle: new THREE.Color(0x00f2fe),
    listening: new THREE.Color(0xf59e0b),
    thinking: new THREE.Color(0xd946ef),
    speaking: new THREE.Color(0x00f2fe),
    error: new THREE.Color(0xef4444)
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

  // Smoothly collapse orb when chat is scrolled down
  if (chatContainer && orbSection) {
    chatContainer.addEventListener('scroll', () => {
      if (chatContainer.scrollTop > 50) {
        if (!orbSection.classList.contains('collapsed')) {
          orbSection.classList.add('collapsed');
          setTimeout(onOrbResize, 350);
        }
      } else {
        if (orbSection.classList.contains('collapsed')) {
          orbSection.classList.remove('collapsed');
          setTimeout(onOrbResize, 350);
        }
      }
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

    // Restore fenced code blocks with Copy Button
    codeBlocks.forEach((block, idx) => {
      const escapedCode = escapeHtml(block.code);
      const replacement = `
        <div class="code-block-wrap">
          <div class="code-block-header">
            <span>${block.lang.toUpperCase()}</span>
            <button class="copy-code-btn" data-code="${encodeURIComponent(block.code)}">Copy</button>
          </div>
          <pre><code>${escapedCode}</code></pre>
        </div>
      `;
      processed = processed.replace(`__CODE_BLOCK_${idx}__`, replacement);
    });

    return processed;
  }

  // Delegate copy button clicks
  document.addEventListener('click', (e) => {
    if (e.target && e.target.classList.contains('copy-code-btn')) {
      const encodedCode = e.target.getAttribute('data-code');
      if (encodedCode) {
        const rawCode = decodeURIComponent(encodedCode);
        navigator.clipboard.writeText(rawCode).then(() => {
          const orig = e.target.textContent;
          e.target.textContent = 'Copied!';
          setTimeout(() => { e.target.textContent = orig; }, 1800);
        }).catch(err => {
          console.warn('Clipboard write error:', err);
        });
      }
    }
  });

  // --------------------------------------------------------------------------
  // 6. CHAT RENDERING
  // --------------------------------------------------------------------------
  function appendMessage(text, isUser, meta = {}) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'msg ' + (isUser ? 'msg-user' : 'msg-libra');

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    if (isUser) {
      contentDiv.textContent = text;
    } else {
      contentDiv.innerHTML = formatMarkdown(text);
    }
    msgDiv.appendChild(contentDiv);

    if (!isUser) {
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

      if (meta.token_metrics && meta.token_metrics.eval_count) {
        const tok = document.createElement('span');
        tok.className = 'token-badge';
        const tokPerSec = meta.token_metrics.tokens_per_sec
          ? `${meta.token_metrics.tokens_per_sec.toFixed(1)} tok/s`
          : `${meta.token_metrics.eval_count} tok`;
        tok.textContent = `⚡ ${tokPerSec}`;
        metaDiv.appendChild(tok);
      } else if (meta.token_metrics && meta.token_metrics.fast_path) {
        const tok = document.createElement('span');
        tok.className = 'token-badge';
        tok.textContent = '⚡ FAST-PATH (0 TOK)';
        metaDiv.appendChild(tok);
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
    if (!drawer || !drawerBackdrop) return;
    const shouldOpen = open !== undefined ? open : !drawer.classList.contains('open');
    if (shouldOpen) {
      drawer.classList.add('open');
      drawerBackdrop.classList.add('open');
    } else {
      drawer.classList.remove('open');
      drawerBackdrop.classList.remove('open');
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
        e.stopPropagation();
        renameSession(sess.session_id, sess.title);
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
        e.stopPropagation();
        deleteSession(sess.session_id, sess.title);
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
          appendMessage(`Initialized session "${activeSessionTitle}". How can I help you?`, false);
        } else {
          msgs.forEach((m) => {
            const isUser = m.role === 'user';
            appendMessage(m.content, isUser, {
              action: m.tool_used,
              latency_ms: m.latency_ms,
              token_metrics: {
                eval_count: m.output_tokens,
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

  async function renameSession(sessionId, currentTitle) {
    const updated = prompt('Enter new thread title:', currentTitle || 'New Chat');
    if (!updated || !updated.trim() || updated.trim() === currentTitle) return;

    try {
      const res = await fetch(`/api/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ title: updated.trim() })
      });
      if (res.ok) {
        if (sessionId === activeSessionId) {
          activeSessionTitle = updated.trim();
          if (activeThreadTitleEl) activeThreadTitleEl.textContent = activeSessionTitle;
        }
        await fetchSessions();
      }
    } catch (err) {
      console.warn('Error renaming session:', err);
    }
  }

  async function deleteSession(sessionId, title) {
    if (!confirm(`Delete conversation "${title || 'this thread'}"?`)) return;

    try {
      const res = await fetch(`/api/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' })
      });
      if (res.ok) {
        await fetchSessions();
        if (sessionId === activeSessionId) {
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
    tokenHudText.textContent = `TOKENS: ${formatNumber(sessTotal)}`;
  }

  function populateTokenModal(data) {
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
  // 10. CHAT PROMPT SUBMISSION & KOKORO TTS PLAYBACK
  // --------------------------------------------------------------------------
  async function sendPrompt(text) {
    if (!text || !text.trim()) return;
    const cleanPrompt = text.trim();
    if (promptInput) promptInput.value = '';

    appendMessage(cleanPrompt, true);
    setOrbState('thinking', 'THINKING // LLM REASONING');

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          prompt: cleanPrompt,
          session_id: activeSessionId,
          client_scope: 'remote_web',
          synthesize_audio: true
        })
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
        token_metrics: data.token_metrics
      });

      // Update telemetry & session listing (in case title auto-generated)
      fetchTokenSummary();
      fetchSessions();

      // Audio Playback
      if (data.audio_base64 && remoteAudio) {
        setOrbState('speaking', 'SPEAKING // KOKORO-82M');
        remoteAudio.src = 'data:audio/wav;base64,' + data.audio_base64;
        remoteAudio.play().catch(err => console.warn('Audio play note:', err));
        remoteAudio.onended = () => setOrbState('idle', 'STANDBY // READY');
      } else {
        setOrbState('idle', 'STANDBY // READY');
      }
    } catch (err) {
      appendMessage('Connection Error: Unable to reach Home PC server.', false, { action: 'error' });
      setOrbState('error', 'OFFLINE');
    }
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', () => {
      if (promptInput) sendPrompt(promptInput.value);
    });
  }

  if (promptInput) {
    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendPrompt(promptInput.value);
    });
  }

  // --------------------------------------------------------------------------
  // 11. VOICE MICROPHONE CAPTURE (TAP-TO-SPEAK)
  // --------------------------------------------------------------------------
  async function startRecording() {
    try {
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
      mediaRecorder.stop();
      isRecording = false;
      if (micBtn) micBtn.classList.remove('recording');
      setOrbState('thinking', 'TRANSCRIBING // FASTER-WHISPER');
    }
  }

  if (micBtn) {
    micBtn.addEventListener('click', () => {
      if (!isRecording) startRecording();
      else stopRecording();
    });
  }

  async function uploadVoiceAudio(blob) {
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    formData.append('session_id', activeSessionId);
    formData.append('client_scope', 'remote_web');
    formData.append('synthesize_audio', 'true');

    try {
      const headers = {};
      if (authToken) headers['Authorization'] = 'Bearer ' + authToken;

      const res = await fetch('/api/voice', {
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
        token_metrics: data.token_metrics
      });

      fetchTokenSummary();
      fetchSessions();

      if (data.audio_base64 && remoteAudio) {
        setOrbState('speaking', 'SPEAKING // KOKORO-82M');
        remoteAudio.src = 'data:audio/wav;base64,' + data.audio_base64;
        remoteAudio.play().catch(e => console.warn(e));
        remoteAudio.onended = () => setOrbState('idle', 'STANDBY // READY');
      } else {
        setOrbState('idle', 'STANDBY // READY');
      }
    } catch (err) {
      appendMessage('Voice upload error: ' + err.message, false, { action: 'error' });
      setOrbState('error', 'OFFLINE');
    }
  }

  // --------------------------------------------------------------------------
  // 12. AUTHENTICATION MODAL LOGIC
  // --------------------------------------------------------------------------
  function showAuthModal() {
    if (!authModal) return;
    authModal.style.display = 'flex';
    if (tokenInput) tokenInput.value = authToken;
  }

  if (saveTokenBtn) {
    saveTokenBtn.addEventListener('click', () => {
      if (tokenInput) {
        authToken = tokenInput.value.trim();
        localStorage.setItem('libra_token', authToken);
      }
      if (authModal) authModal.style.display = 'none';
      fetchVitals();
      fetchSessions();
      fetchTokenSummary();
    });
  }

  // --------------------------------------------------------------------------
  // 13. BOOTSTRAP INITIALIZATION
  // --------------------------------------------------------------------------
  initOrb();
  fetchVitals();
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

})();

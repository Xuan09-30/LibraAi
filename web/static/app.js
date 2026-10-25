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
      const isPreviewable = ['html', 'svg', 'xml'].includes((block.lang || '').toLowerCase());
      const previewBtnHtml = isPreviewable
        ? `<button class="preview-code-btn" data-code="${encodeURIComponent(block.code)}">▶ Preview</button>`
        : '';
      const replacement = `
        <div class="code-block-wrap">
          <div class="code-block-header">
            <span>${block.lang.toUpperCase()}</span>
            <div>
              ${previewBtnHtml}
              <button class="copy-code-btn" data-code="${encodeURIComponent(block.code)}">Copy</button>
            </div>
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

  function appendMessage(text, isUser, meta = {}) {
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
    const textNode = document.createElement('div');
    if (isUser) {
      textNode.textContent = text;
    } else {
      textNode.innerHTML = formatMarkdown(text);
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
          appendMessage(`Initialized session "${activeSessionTitle}". How can I help you?`, false);
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

  async function sendPrompt(text) {
    if ((!text || !text.trim()) && !pendingAttachment) return;
    unlockAudio();
    const cleanPrompt = (text || '').trim();
    if (promptInput) promptInput.value = '';

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
        synthesize_audio: true
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

      const textNode = document.createElement('div');
      textNode.className = 'msg-text';
      contentDiv.appendChild(textNode);
      msgDiv.appendChild(contentDiv);

      const metaDiv = document.createElement('div');
      metaDiv.className = 'msg-meta';
      msgDiv.appendChild(metaDiv);

      chatContainer.appendChild(msgDiv);
      chatContainer.scrollTop = chatContainer.scrollHeight;

      let accumulatedText = '';
      const collectedAudioChunks = [];
      let finalTokenMetrics = null;

      const res = await fetch('/api/chat?stream=true', {
        method: 'POST',
        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload)
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
              } else if (data.type === 'token') {
                accumulatedText += data.content;
                textNode.innerHTML = formatMarkdown(accumulatedText);
                chatContainer.scrollTop = chatContainer.scrollHeight;
              } else if (data.type === 'audio') {
                if (data.audio_base64) {
                  collectedAudioChunks.push(data.audio_base64);
                  audioPlayer.enqueue(data.audio_base64);
                }
              } else if (data.type === 'done') {
                finalTokenMetrics = data.token_metrics;
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
            textNode.innerHTML = formatMarkdown(accumulatedText);
          } else if (data.type === 'audio' && data.audio_base64) {
            collectedAudioChunks.push(data.audio_base64);
            audioPlayer.enqueue(data.audio_base64);
          } else if (data.type === 'done') {
            finalTokenMetrics = data.token_metrics;
          }
        } catch (e) {}
      }

      // Render Telemetry Badges
      if (finalTokenMetrics) {
        if (finalTokenMetrics.latency_ms) {
          const lat = document.createElement('span');
          lat.textContent = finalTokenMetrics.latency_ms + 'ms';
          metaDiv.appendChild(lat);
        }

        if (finalTokenMetrics.turn_out || finalTokenMetrics.output_tokens) {
          const tok = document.createElement('span');
          tok.className = 'token-badge';
          const tokSpeed = finalTokenMetrics.tok_per_sec || finalTokenMetrics.tokens_per_sec;
          const outCount = finalTokenMetrics.turn_out || finalTokenMetrics.output_tokens;
          tok.textContent = tokSpeed ? `⚡ ${tokSpeed.toFixed(1)} tok/s` : `⚡ ${outCount} tok`;
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

      chatContainer.scrollTop = chatContainer.scrollHeight;

      // Update telemetry & sidebar threads
      fetchTokenSummary();
      fetchSessions();

      if (!audioPlayer.isPlaying) {
        setOrbState('idle', 'STANDBY // READY');
      }
    } catch (err) {
      console.error('[Chat Error]:', err);
      appendMessage('Connection Error: Unable to reach Home PC server.', false, { action: 'error' });
      setOrbState('error', 'OFFLINE');
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
    formData.append('synthesize_audio', 'true');

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
    speakBriefingBtn.addEventListener('click', () => {
      if (currentBriefingText && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(currentBriefingText);
        u.rate = 1.05;
        window.speechSynthesis.speak(u);
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
        promptForToken();
      }
    } catch (err) {
      console.warn('Failed to fetch auth info:', err);
    }
  }

  function updateRoleBadge(info) {
    const badge = document.getElementById('role-badge');
    const inviteBtn = document.getElementById('invite-nav-btn');
    if (!badge) return;

    if (info.role === 'host') {
      badge.textContent = '👑 HOST';
      badge.className = 'role-badge host';
      badge.title = `Host Owner (${info.email || 'chenxuanchuah@gmail.com'})`;
      if (inviteBtn) inviteBtn.style.display = 'inline-flex';
    } else {
      badge.textContent = `👤 ${info.label || 'GUEST'}`;
      badge.className = 'role-badge guest';
      badge.title = 'Guest Mode: Desktop OS control is restricted to host owner.';
      if (inviteBtn) inviteBtn.style.display = 'none';
      const vaultBtn = document.getElementById('vault-nav-btn');
      if (vaultBtn) vaultBtn.style.display = 'none';
    }
  }

  function promptForToken() {
    const entered = window.prompt("Project Libra Access Protected.\nPlease enter your Access or Guest Token:");
    if (entered) {
      authToken = entered.trim();
      localStorage.setItem('libra_token', authToken);
      document.cookie = `libra_auth=${authToken}; path=/; max-age=2592000; SameSite=Lax`;
      window.location.reload();
    }
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
      if (inviteModal) inviteModal.classList.remove('active');
    });
  }

  async function openInviteModal() {
    if (!inviteModal) return;
    inviteModal.classList.add('active');
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

      gameShieldCards.innerHTML = `
        <div class="token-card highlight">
          <div class="token-card-header">DETECTED GAME</div>
          <div class="token-card-value" style="font-size: 18px; color: ${activeGame ? '#10b981' : '#94a3b8'};">${escapeHtml(gameTitle)}</div>
          <div class="token-card-sub">${escapeHtml(gameSub)}</div>
        </div>
        <div class="token-card">
          <div class="token-card-header">WAKE-WORD SHIELD</div>
          <div class="token-card-value" style="font-size: 18px;">${data.wake_threshold}</div>
          <div class="token-card-sub">${escapeHtml(data.agc_status)}</div>
        </div>
      `;

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
    { icon: '🎮', title: 'Gaming & Audio Shield Control', desc: 'Inspect active game (Valorant, CS2) & lock 100% game volume', shortcut: '/game', run: () => openGameShieldModal() },
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
    const wrap = document.createElement('div');
    wrap.className = 'starter-hero-wrap';
    wrap.innerHTML = `
      <div class="starter-hero-title">⚡ Quick Tactical Actions &amp; Prompts</div>
      <div class="starter-chips-grid">
        <button class="starter-chip-btn" data-prompt="What game am I playing right now?">🎮 What game am I playing right now?</button>
        <button class="starter-chip-btn" data-prompt="Good morning Libra, give me my daily briefing">⚡ Generate my Daily Tactical Briefing</button>
        <button class="starter-chip-btn" data-prompt="What is the current weather and rain forecast?">🌦️ Current weather &amp; rain forecast</button>
        <button class="starter-chip-btn" data-prompt="Check my system vitals and GPU temperature">🖥️ Check RTX GPU temp &amp; system vitals</button>
        <button class="starter-chip-btn" data-action="game-shield">🛡️ Open Gaming &amp; Audio Shield Control</button>
        <button class="starter-chip-btn" data-action="cmd-palette">⌘ Open Command Palette (Ctrl + K)</button>
      </div>
    `;
    wrap.querySelectorAll('.starter-chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const act = btn.getAttribute('data-action');
        const p = btn.getAttribute('data-prompt');
        if (act === 'game-shield') {
          openGameShieldModal();
        } else if (act === 'cmd-palette') {
          openCommandPalette('');
        } else if (p && promptInput && sendBtn) {
          promptInput.value = p;
          sendBtn.click();
        }
      });
    });
    chatContainer.appendChild(wrap);
  }

  // --------------------------------------------------------------------------
  // 13. BOOTSTRAP INITIALIZATION
  // --------------------------------------------------------------------------
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

})();
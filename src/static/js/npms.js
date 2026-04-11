/**
 * NPMS 글로벌 JavaScript
 * 서울시교육청 학교 네트워크 장애관리 시스템
 */

/* ─── CSRF 유틸 ─── */
function getCsrfToken() {
  return document.cookie.split(';')
    .find(c => c.trim().startsWith('csrftoken='))
    ?.split('=')[1] || (typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : '');
}

/* ─── 공통 fetch 래퍼 ─── */
async function apiGet(url, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const full = qs ? `${url}?${qs}` : url;
  const res = await fetch(full, {
    headers: { 'X-CSRFToken': getCsrfToken() }
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}

async function apiPost(url, data = {}) {
  const isFormData = data instanceof FormData;
  const headers = { 'X-CSRFToken': getCsrfToken() };
  if (!isFormData) headers['Content-Type'] = 'application/json';
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: isFormData ? data : JSON.stringify(data)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw err;
  }
  return res.json();
}

async function apiPatch(url, data = {}) {
  const res = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}

async function apiDelete(url) {
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { 'X-CSRFToken': getCsrfToken() }
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.status === 204 ? null : res.json();
}

/* ─── 토스트 알림 ─── */
function showToast(message, type = 'info') {
  const colorMap = {
    success: 'bg-success', error: 'bg-danger',
    warning: 'bg-warning text-dark', info: 'bg-info text-dark'
  };
  const id = `toast-${Date.now()}`;
  const div = document.createElement('div');
  div.innerHTML = `
    <div id="${id}" class="toast align-items-center text-white ${colorMap[type]} border-0 show" role="alert" style="min-width:250px;">
      <div class="d-flex">
        <div class="toast-body" style="white-space:pre-line;">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`;
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;top:60px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }
  container.appendChild(div);
  const duration = (type === 'error') ? 6000 : 4000;
  setTimeout(() => div.remove(), duration);
}

/* ─── 날짜/시간 포맷 ─── */
function formatDateTime(dt) {
  if (!dt) return '-';
  const d = new Date(dt);
  return d.toLocaleString('ko-KR', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
}

function formatDate(dt) {
  if (!dt) return '-';
  return new Date(dt).toLocaleDateString('ko-KR');
}

function timeAgo(dt) {
  const diff = Math.floor((Date.now() - new Date(dt)) / 60000);
  if (diff < 1)  return '방금';
  if (diff < 60) return `${diff}분 전`;
  if (diff < 1440) return `${Math.floor(diff/60)}시간 전`;
  return `${Math.floor(diff/1440)}일 전`;
}

/* ─── 숫자 포맷 ─── */
function numFmt(n) {
  return n != null ? Number(n).toLocaleString() : '-';
}

/* ─── 모바일 사이드바 토글 ─── */
document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar   = document.getElementById('sidebar');
  const overlay   = document.getElementById('sidebar-overlay');
  const mainWrap  = document.getElementById('main-wrapper');

  function openSidebar() {
    sidebar.classList.add('mobile-open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  function closeSidebar() {
    sidebar.classList.remove('mobile-open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  if (toggleBtn && sidebar) {
    // touchend로 즉시 반응 (모바일 300ms 딜레이 제거)
    toggleBtn.addEventListener('touchend', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (window.innerWidth < 992) {
        sidebar.classList.contains('mobile-open') ? closeSidebar() : openSidebar();
      }
    });
    toggleBtn.addEventListener('click', (e) => {
      if (window.innerWidth < 992) {
        e.stopPropagation();
        sidebar.classList.contains('mobile-open') ? closeSidebar() : openSidebar();
      } else {
        sidebar.classList.toggle('collapsed');
        mainWrap?.classList.toggle('expanded');
      }
    });

    // 오버레이 탭 → 닫기
    if (overlay) {
      overlay.addEventListener('touchend', (e) => { e.preventDefault(); closeSidebar(); });
      overlay.addEventListener('click',    ()  => { closeSidebar(); });
    }

    // 사이드바 내 × 닫기 버튼
    const closeBtn = document.getElementById('sidebar-close');
    if (closeBtn) {
      closeBtn.addEventListener('touchend', (e) => { e.preventDefault(); closeSidebar(); });
      closeBtn.addEventListener('click',    ()  => { closeSidebar(); });
    }

    // 메뉴 링크 클릭 시 사이드바 닫고 이동
    sidebar.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth < 992) closeSidebar();
      });
    });
  }
});

/* ─── 디바운스 ─── */
function debounce(fn, delay = 300) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/* ─── 확인 다이얼로그 (공통) ─── */
function confirmAction(message, callback) {
  if (confirm(message)) callback();
}

/* ─── 전자서명 패드 ─── */
class SignaturePad {
  constructor(canvasId) {
    this.canvas  = document.getElementById(canvasId);
    this.ctx     = this.canvas?.getContext('2d');
    this.drawing = false;
    if (!this.canvas) return;
    this.canvas.addEventListener('mousedown',  e => { this.drawing = true; this.ctx.beginPath(); this._move(e); });
    this.canvas.addEventListener('mousemove',  e => { if (this.drawing) this._draw(e); });
    this.canvas.addEventListener('mouseup',    ()=> { this.drawing = false; });
    this.canvas.addEventListener('touchstart', e => { this.drawing = true; this.ctx.beginPath(); this._moveTouch(e); });
    this.canvas.addEventListener('touchmove',  e => { e.preventDefault(); if (this.drawing) this._drawTouch(e); }, {passive:false});
    this.canvas.addEventListener('touchend',   ()=> { this.drawing = false; });
    this.ctx.strokeStyle = '#1e293b';
    this.ctx.lineWidth   = 2;
    this.ctx.lineCap     = 'round';
  }
  _move(e)      { const r = this.canvas.getBoundingClientRect(); this.ctx.moveTo(e.clientX-r.left, e.clientY-r.top); }
  _draw(e)      { const r = this.canvas.getBoundingClientRect(); this.ctx.lineTo(e.clientX-r.left, e.clientY-r.top); this.ctx.stroke(); }
  _moveTouch(e) { const t = e.touches[0]; const r = this.canvas.getBoundingClientRect(); this.ctx.moveTo(t.clientX-r.left, t.clientY-r.top); }
  _drawTouch(e) { const t = e.touches[0]; const r = this.canvas.getBoundingClientRect(); this.ctx.lineTo(t.clientX-r.left, t.clientY-r.top); this.ctx.stroke(); }
  clear()       { this.ctx?.clearRect(0, 0, this.canvas.width, this.canvas.height); }
  toBase64()    { return this.canvas?.toDataURL('image/png'); }
  isEmpty()     {
    const data = this.ctx?.getImageData(0,0,this.canvas.width,this.canvas.height).data;
    return !data || !data.some(v => v !== 0);
  }
}

/* ─── GPS 위치 수집 ─── */
let gpsWatchId = null;

function startGpsTracking() {
  if (!navigator.geolocation) return;
  gpsWatchId = navigator.geolocation.watchPosition(
    pos => {
      apiPost(`${API_BASE}/gps/logs/`, {
        lat:      pos.coords.latitude,
        lng:      pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        speed:    pos.coords.speed,
      }).catch(() => {});
    },
    err => console.warn('GPS error:', err),
    { enableHighAccuracy: true, maximumAge: 30000, timeout: 10000 }
  );
}

function stopGpsTracking() {
  if (gpsWatchId != null) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
  }
}

/* 현장기사는 자동으로 GPS 추적 시작 */
if (typeof USER_ROLE !== 'undefined' && USER_ROLE === 'worker') {
  document.addEventListener('DOMContentLoaded', startGpsTracking);
}

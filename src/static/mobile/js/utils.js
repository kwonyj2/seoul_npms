/**
 * NPMS Mobile 공통 유틸리티
 * mobile/base.html 에서 전역 로드 — 모바일 페이지 전용
 */

/* ─── 모바일 토스트 (화면 하단 중앙) ─── */
function showToastLocal(msg, type) {
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);' +
    'background:' + (type === 'success' ? '#198754' : '#dc3545') + ';color:#fff;' +
    'padding:10px 20px;border-radius:20px;font-size:14px;z-index:9999;' +
    'box-shadow:0 4px 12px rgba(0,0,0,.2);';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2500);
}

/* ─── CSRF 토큰 ─── */
function getCsrfToken() {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
}

/* ─── 날짜 포맷 ─── */
function formatDate(s) {
  return s ? s.substring(0, 10) : '-';
}

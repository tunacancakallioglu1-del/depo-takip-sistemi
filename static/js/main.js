/* ========================================================
   Main.js — Global Utilities
   ======================================================== */

// ── Alert/Notification System ─────────────────────────
function showAlert(type, message, duration = 5000) {
  const alertContainer = document.getElementById('alertContainer');
  if (!alertContainer) return;

  const id = `alert-${Date.now()}`;
  const icons = { success: '✓', danger: '✗', warning: '⚠', info: 'ℹ' };
  const alertHTML = `
    <div id="${id}" class="alert alert-${type} alert-dismissible fade show shadow-sm mb-2" role="alert"
         style="min-width:280px;animation:slideInRight .35s ease">
      <span class="me-2">${icons[type] || '•'}</span>${message}
      <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
    </div>`;
  alertContainer.insertAdjacentHTML('beforeend', alertHTML);

  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }
  }, duration);
}

// ── Loading Spinner ────────────────────────────────────
function setLoading(show) {
  let overlay = document.getElementById('spinnerOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'spinnerOverlay';
    overlay.className = 'spinner-overlay';
    overlay.innerHTML = `
      <div class="text-center">
        <div class="spinner-border text-primary" style="width:3rem;height:3rem" role="status"></div>
        <p class="mt-3 fw-semibold text-primary">İşleniyor...</p>
      </div>`;
    document.body.appendChild(overlay);
  }
  overlay.classList.toggle('active', show);
}

// ── Fetch Helper ───────────────────────────────────────
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    const data = await res.json();
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { basarili: false, mesaj: 'Bağlantı hatası: ' + e.message } };
  }
}

// ── Confirm Dialog ─────────────────────────────────────
function confirmAction(message, onConfirm) {
  if (confirm(message || 'Bu işlemi yapmak istediğinizden emin misiniz?')) {
    onConfirm();
  }
}

// ── File Upload Helper ─────────────────────────────────
function initUploadZone(zoneId, fileInputId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(fileInputId);
  if (!zone || !input) return;

  ['dragenter','dragover'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('dragover'); }));
  ['dragleave','drop'].forEach(ev =>
    zone.addEventListener(ev, () => zone.classList.remove('dragover')));

  zone.addEventListener('drop', e => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) { input.files = e.dataTransfer.files; zone.querySelector('.upload-filename').textContent = file.name; }
  });

  zone.addEventListener('click', () => input.click());

  input.addEventListener('change', () => {
    const fn = zone.querySelector('.upload-filename');
    if (fn && input.files[0]) fn.textContent = input.files[0].name;
  });
}

// ── Pagination ─────────────────────────────────────────
function renderPagination(containerId, currentPage, totalPages, onPage) {
  const container = document.getElementById(containerId);
  if (!container || totalPages <= 1) { if (container) container.innerHTML = ''; return; }

  const pages = [];
  for (let i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
    pages.push(i);
  }

  container.innerHTML = `
    <nav><ul class="pagination pagination-sm justify-content-center mb-0">
      <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" data-page="${currentPage - 1}">‹</a>
      </li>
      ${pages.map(p => `<li class="page-item ${p === currentPage ? 'active' : ''}">
        <a class="page-link" href="#" data-page="${p}">${p}</a>
      </li>`).join('')}
      <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" data-page="${currentPage + 1}">›</a>
      </li>
    </ul></nav>`;

  container.querySelectorAll('.page-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const p = parseInt(link.dataset.page);
      if (p >= 1 && p <= totalPages) onPage(p);
    });
  });
}

// ── Format Helpers ─────────────────────────────────────
function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return isNaN(d) ? dateStr : d.toLocaleDateString('tr-TR');
}

function formatNumber(n) {
  return typeof n === 'number' ? n.toLocaleString('tr-TR') : (n || '-');
}

// ── Init ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (window.Chart) {
    Chart.defaults.animation = false;
  }
  // Add active class to current nav link
  const path = window.location.pathname;
  document.querySelectorAll('.navbar .nav-link').forEach(link => {
    if (link.getAttribute('href') !== '/' && path.startsWith(link.getAttribute('href'))) {
      link.classList.add('active');
    } else if (link.getAttribute('href') === '/' && path === '/') {
      link.classList.add('active');
    }
  });
});

console.log('✓ Depo Operasyon — Main.js yüklendi');

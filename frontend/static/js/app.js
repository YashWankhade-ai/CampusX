/**
 * CampusX Core JS — v1.0
 * Sidebar toggle, drawer, toast, dropdown, modal, keyboard navigation.
 * No external dependencies.
 */

(function () {
  'use strict';

  // ── Sidebar / Drawer ─────────────────────────────────────────
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('drawerOverlay');
  const trigger  = document.getElementById('menuTrigger');

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('open');
    overlay && overlay.classList.add('open');
    overlay && (overlay.setAttribute('aria-hidden', 'false'));
    trigger && trigger.setAttribute('aria-expanded', 'true');
  }

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('open');
    overlay && overlay.classList.remove('open');
    overlay && (overlay.setAttribute('aria-hidden', 'true'));
    trigger && trigger.setAttribute('aria-expanded', 'false');
  }

  trigger  && trigger.addEventListener('click', () => {
    sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
  });
  overlay  && overlay.addEventListener('click', closeSidebar);

  // Close sidebar on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSidebar();
      closeAllDropdowns();
    }
  });


  // ── Toast System ──────────────────────────────────────────────

  window.CampusX = window.CampusX || {};

  /**
   * Show a toast notification.
   * @param {string} message
   * @param {'success'|'error'|'warning'|'info'} type
   * @param {number} duration - ms, default 4000
   */
  window.CampusX.toast = function (message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'status');
    toast.innerHTML = `
      <span class="toast-dot" aria-hidden="true"></span>
      <span>${escapeHtml(message)}</span>
      <button
        onclick="this.parentElement.remove()"
        style="margin-left:auto;background:none;border:none;cursor:pointer;color:var(--cx-text-muted);padding:0;line-height:1;"
        aria-label="Dismiss notification"
      >&times;</button>
    `;

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        if (toast.parentElement) {
          toast.style.opacity = '0';
          toast.style.transform = 'translateX(20px)';
          toast.style.transition = 'opacity 200ms ease, transform 200ms ease';
          setTimeout(() => toast.remove(), 220);
        }
      }, duration);
    }
  };


  // ── Dropdown menus ────────────────────────────────────────────

  function closeAllDropdowns() {
    document.querySelectorAll('[data-dropdown-menu]').forEach(menu => {
      menu.style.display = 'none';
      const trigger = document.querySelector(`[data-dropdown="${menu.dataset.dropdownMenu}"]`);
      trigger && trigger.setAttribute('aria-expanded', 'false');
    });
  }

  document.querySelectorAll('[data-dropdown]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const menuId = btn.dataset.dropdown;
      const menu = document.querySelector(`[data-dropdown-menu="${menuId}"]`);
      if (!menu) return;

      const isOpen = menu.style.display === 'block';
      closeAllDropdowns();

      if (!isOpen) {
        menu.style.display = 'block';
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });

  document.addEventListener('click', closeAllDropdowns);


  // ── Modal ─────────────────────────────────────────────────────

  /**
   * Open a modal by ID.
   */
  window.CampusX.openModal = function (id) {
    const overlay = document.getElementById(id + '-overlay');
    if (!overlay) return;
    overlay.style.display = 'flex';
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    // Focus first focusable element
    const focusable = overlay.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    focusable && focusable.focus();
  };

  window.CampusX.closeModal = function (id) {
    const overlay = document.getElementById(id + '-overlay');
    if (!overlay) return;
    overlay.style.display = 'none';
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  };

  // Close modal on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.style.display = 'none';
        document.body.style.overflow = '';
      }
    });
  });


  // ── Tab panels ────────────────────────────────────────────────

  document.querySelectorAll('.tabs-nav').forEach(nav => {
    nav.addEventListener('click', (e) => {
      const tab = e.target.closest('[data-tab]');
      if (!tab) return;

      const tabs = nav.querySelectorAll('[data-tab]');
      tabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');

      // Show/hide panels
      const group = nav.closest('[data-tabs-group]');
      if (group) {
        const panels = group.querySelectorAll('[data-tab-panel]');
        panels.forEach(p => {
          p.hidden = p.dataset.tabPanel !== tab.dataset.tab;
        });
      }
    });
  });


  // ── Active nav links ──────────────────────────────────────────

  const path = window.location.pathname;
  document.querySelectorAll('.nav-item[href]').forEach(link => {
    if (link.getAttribute('href') === path ||
        (path.startsWith(link.getAttribute('href')) && link.getAttribute('href') !== '/')) {
      link.classList.add('active');
      link.setAttribute('aria-current', 'page');
    }
  });


  // ── Skeleton loader removal ───────────────────────────────────

  window.CampusX.removeSkeleton = function (containerId) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = '';
  };


  // ── Utility ───────────────────────────────────────────────────

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

})();

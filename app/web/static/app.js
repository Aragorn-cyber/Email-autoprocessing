const accountForm = document.querySelector('#account-form');
const scanForm = document.querySelector('#scan-form');
const scanStatus = document.querySelector('#scan-status');
const toast = document.querySelector('#toast');

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('visible');
  window.setTimeout(() => toast.classList.remove('visible'), 2400);
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || '操作失败');
  return payload;
}

function replaceWithBadge(button, className, text) {
  const badge = document.createElement('span');
  badge.className = className;
  badge.textContent = text;
  button.replaceWith(badge);
}

document.querySelectorAll('[data-toggle="account-form"]').forEach((button) => {
  button.addEventListener('click', () => {
    accountForm?.classList.toggle('hidden');
    if (!accountForm?.classList.contains('hidden')) accountForm.querySelector('input')?.focus();
  });
});

accountForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(accountForm).entries());
  payload.imap_port = Number(payload.imap_port);
  payload.scan_window_days = Number(payload.scan_window_days);
  try {
    await apiRequest('/api/accounts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    location.reload();
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelectorAll('.account-update-form').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await apiRequest(`/api/accounts/${form.dataset.accountId}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          scan_window_days: Number(form.elements.scan_window_days.value),
          is_active: form.elements.is_active.checked,
        }),
      });
      showToast('账号设置已保存');
    } catch (error) {
      showToast(error.message);
    }
  });
});

scanForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submitButton = scanForm.querySelector('button[type="submit"]');
  scanStatus.textContent = '正在读取并分析邮件，请稍候…';
  submitButton.disabled = true;
  try {
    const payload = await apiRequest('/api/scans', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({window_days: Number(document.querySelector('#window-days').value)}),
    });
    location.href = `/reports/${payload.report_id}`;
  } catch (error) {
    scanStatus.textContent = error.message;
    submitButton.disabled = false;
  }
});

document.addEventListener('click', async (event) => {
  const bulkMarkButton = event.target.closest('[data-mark-read-section]');
  if (bulkMarkButton) {
    event.preventDefault();
    const section = bulkMarkButton.closest('.mail-ledger, .discard-section');
    if (!section) return;
    const emailIds = Array.from(
      section.querySelectorAll('[data-mail-entry]'),
      (entry) => Number(entry.dataset.mailEntry),
    ).filter((id) => Number.isFinite(id));
    if (emailIds.length === 0) return;
    bulkMarkButton.disabled = true;
    try {
      const payload = await apiRequest('/api/read-mails/bulk', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email_ids: emailIds}),
      });
      section.querySelectorAll('[data-mark-read]').forEach((button) => {
        const badge = document.createElement('span');
        badge.className = 'read-badge';
        badge.textContent = '已加入本地已读';
        button.replaceWith(badge);
      });
      showToast(`已将 ${payload.marked} 封邮件加入本地已读名单`);
    } catch (error) {
      bulkMarkButton.disabled = false;
      showToast(error.message);
    }
    return;
  }

  const removeAllButton = event.target.closest('[data-remove-all-read]');
  if (removeAllButton) {
    removeAllButton.disabled = true;
    try {
      await apiRequest('/api/read-mails', {method: 'DELETE'});
      location.reload();
    } catch (error) {
      removeAllButton.disabled = false;
      showToast(error.message);
    }
    return;
  }

  const markButton = event.target.closest('[data-mark-read]');
  const removeButton = event.target.closest('[data-remove-read]');
  const markImportantButton = event.target.closest('[data-mark-important]');
  const removeImportantButton = event.target.closest('[data-remove-important]');
  const button = markButton || removeButton || markImportantButton || removeImportantButton;
  if (!button) return;
  button.disabled = true;
  try {
    if (markButton) {
      await apiRequest(`/api/read-mails/${markButton.dataset.markRead}`, {method: 'POST'});
      replaceWithBadge(markButton, 'read-badge', '已加入本地已读');
      showToast('已加入本地已读名单');
    } else if (removeButton) {
      await apiRequest(`/api/read-mails/${removeButton.dataset.removeRead}`, {method: 'DELETE'});
      location.reload();
    } else if (markImportantButton) {
      await apiRequest(`/api/important-mails/${markImportantButton.dataset.markImportant}`, {method: 'POST'});
      replaceWithBadge(markImportantButton, 'important-badge', '重要邮件');
      showToast('已标记为重要邮件');
    } else {
      await apiRequest(`/api/important-mails/${removeImportantButton.dataset.removeImportant}`, {method: 'DELETE'});
      location.reload();
    }
  } catch (error) {
    button.disabled = false;
    showToast(error.message);
  }
});

const menuButton = document.querySelector('[data-menu-button]');
const menu = document.querySelector('[data-menu]');
menuButton?.addEventListener('click', () => menu.classList.toggle('open'));

document.querySelectorAll('[data-tabs]').forEach((tabs) => {
  const activateTab = (button) => {
    if (!button) return;
    tabs.querySelectorAll('[data-tab]').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    document.querySelectorAll('[data-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.panel !== button.dataset.tab;
    });
    document.querySelectorAll('[data-current-tab]').forEach((input) => {
      input.value = button.dataset.tab;
    });
  };
  tabs.querySelectorAll('[data-tab]').forEach((button) => {
    button.addEventListener('click', () => activateTab(button));
  });
  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  activateTab(tabs.querySelector(`[data-tab="${requestedTab}"]`) || tabs.querySelector('[data-tab].active'));
});

document.querySelectorAll('[data-month-picker]').forEach((picker) => {
  const monthInput = picker.querySelector('[data-month-value]');
  const monthNumber = picker.querySelector('[data-month-number]');
  const yearInput = picker.querySelector('[data-month-year]');
  const syncMonth = () => {
    const year = String(yearInput?.value || '').padStart(4, '0');
    const month = String(monthNumber?.value || '').padStart(2, '0');
    if (/^\d{4}$/.test(year) && /^(0[1-9]|1[0-2])$/.test(month)) {
      monthInput.value = `${year}-${month}`;
      return true;
    }
    return false;
  };
  picker.addEventListener('submit', (event) => {
    if (!syncMonth()) event.preventDefault();
  });
  picker.querySelectorAll('[data-auto-submit]').forEach((input) => {
    input.addEventListener('change', () => {
      if (syncMonth()) picker.requestSubmit();
    });
  });
});

const statusSelect = document.querySelector('[data-result-status]');
const sets = document.querySelector('[data-sets]');
const forfeit = document.querySelector('[data-forfeit]');
const syncResultFields = () => {
  if (!statusSelect) return;
  sets.hidden = statusSelect.value !== 'completed';
  forfeit.hidden = statusSelect.value !== 'forfeit';
};
statusSelect?.addEventListener('change', syncResultFields);
syncResultFields();

const form = document.querySelector('#match-form');
const evidenceInput = document.querySelector('[data-evidence-files]');
const uploadStatus = document.querySelector('[data-upload-status]');

evidenceInput?.addEventListener('change', () => {
  const count = evidenceInput.files.length;
  uploadStatus.hidden = count === 0;
  uploadStatus.className = 'upload-status';
  uploadStatus.textContent = count ? `Đã chọn ${count} ảnh. Ảnh sẽ được tải lên khi gửi kết quả.` : '';
});

async function uploadEvidence() {
  const files = Array.from(evidenceInput?.files || []);
  if (!files.length) return;
  if (files.length > 6) throw new Error('Mỗi lần chỉ được chọn tối đa 6 ảnh minh chứng.');
  const oversized = files.find((file) => file.size > 12 * 1024 * 1024);
  if (oversized) throw new Error(`${oversized.name} vượt quá giới hạn 12 MB.`);

  uploadStatus.hidden = false;
  uploadStatus.className = 'upload-status uploading';
  uploadStatus.textContent = `Đang tải ${files.length} ảnh lên Google Drive...`;

  const uploadData = new FormData();
  uploadData.append('month', form.elements.month.value);
  files.forEach((file) => uploadData.append('files', file));
  const response = await fetch('/api/evidence', {method: 'POST', body: uploadData});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    uploadStatus.className = 'upload-status error';
    uploadStatus.textContent = result.message || 'Không thể tải ảnh lên Google Drive.';
    throw new Error(uploadStatus.textContent);
  }

  const textarea = form.elements.evidence_urls;
  const currentUrls = textarea.value.split('\n').map((item) => item.trim()).filter(Boolean);
  const uploadedUrls = result.files.map((item) => item.url);
  textarea.value = [...currentUrls, ...uploadedUrls].join('\n');
  evidenceInput.value = '';
  uploadStatus.className = 'upload-status';
  uploadStatus.textContent = `Đã tải ${uploadedUrls.length} ảnh lên Google Drive thành công.`;
}

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  const errorsBox = document.querySelector('[data-form-errors]');
  submit.disabled = true;
  submit.textContent = evidenceInput?.files.length ? 'Đang tải ảnh...' : 'Đang gửi...';
  errorsBox.hidden = true;

  try {
    await uploadEvidence();
    submit.textContent = 'Đang gửi kết quả...';
    const data = Object.fromEntries(new FormData(form).entries());
    delete data.evidence_files;
    form.querySelectorAll('input[type="checkbox"]').forEach((input) => data[input.name] = input.checked);
    data.evidence_urls = (data.evidence_urls || '').split('\n').map(x => x.trim()).filter(Boolean);

    const response = await fetch('/api/matches', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) {
      const messages = result.errors ? Object.values(result.errors) : [result.message || 'Không thể gửi kết quả.'];
      errorsBox.innerHTML = `<b>Vui lòng kiểm tra:</b><ul>${messages.map(x => `<li>${x}</li>`).join('')}</ul>`;
      errorsBox.hidden = false;
      errorsBox.scrollIntoView({behavior: 'smooth', block: 'center'});
      return;
    }
    document.querySelector('[data-match-code]').textContent = result.match_code;
    document.querySelector('#success-dialog').showModal();
  } catch (error) {
    errorsBox.textContent = error.message || 'Không kết nối được máy chủ. Vui lòng thử lại.';
    errorsBox.hidden = false;
  } finally {
    submit.disabled = false;
    submit.innerHTML = 'Gửi kết quả để BTC duyệt <span>→</span>';
  }
});

document.querySelector('[data-new-match]')?.addEventListener('click', () => {
  document.querySelector('#success-dialog').close();
  form.reset();
  syncResultFields();
  window.scrollTo({top: 0, behavior: 'smooth'});
});

const drawApp = document.querySelector('[data-draw-app]');
if (drawApp) {
  const tasks = JSON.parse(document.querySelector('#draw-tasks-data')?.textContent || '[]');
  const canvas = drawApp.querySelector('[data-prize-wheel]');
  const context = canvas.getContext('2d');
  const spinButton = drawApp.querySelector('[data-spin-wheel]');
  const spinStatus = drawApp.querySelector('[data-spin-status]');
  const taskTitle = drawApp.querySelector('[data-draw-title]');
  const taskAward = drawApp.querySelector('[data-draw-award]');
  const taskDescription = drawApp.querySelector('[data-draw-description]');
  const manualTask = drawApp.querySelector('[data-manual-task]');
  const manualCandidate = drawApp.querySelector('[data-manual-candidate]');
  const candidateList = drawApp.querySelector('[data-candidate-list]');
  const winnerDialog = document.querySelector('[data-winner-dialog]');
  const palette = ['#dff4ff', '#8fd8f7', '#c9efff', '#67c4ec', '#eaf8ff', '#a8e2fa'];
  let activeTask = tasks[0];
  let rotation = 0;
  let spinning = false;

  const candidateNames = (task) => task.candidates.map((item) => item.name);
  const fitName = (name) => name.length > 22 ? `${name.slice(0, 20)}…` : name;
  const drawWheel = () => {
    const names = candidateNames(activeTask);
    const size = canvas.width;
    const center = size / 2;
    const radius = center - 18;
    const arc = Math.PI * 2 / names.length;
    context.clearRect(0, 0, size, size);
    context.save();
    context.translate(center, center);
    context.rotate(rotation);
    names.forEach((name, index) => {
      const start = -Math.PI / 2 + index * arc;
      context.beginPath();
      context.moveTo(0, 0);
      context.arc(0, 0, radius, start, start + arc);
      context.closePath();
      context.fillStyle = palette[index % palette.length];
      context.fill();
      context.strokeStyle = '#ffffff';
      context.lineWidth = 5;
      context.stroke();

      context.save();
      context.rotate(start + arc / 2);
      context.textAlign = 'right';
      context.textBaseline = 'middle';
      context.fillStyle = '#124f72';
      context.font = `700 ${names.length > 8 ? 20 : 25}px "Segoe UI", Arial`;
      context.fillText(fitName(name), radius - 32, 0);
      context.restore();
    });
    context.beginPath();
    context.arc(0, 0, radius, 0, Math.PI * 2);
    context.strokeStyle = '#ffffff';
    context.lineWidth = 12;
    context.stroke();
    context.restore();
  };

  const populateTask = (taskKey) => {
    activeTask = tasks.find((task) => task.key === taskKey) || tasks[0];
    rotation = 0;
    taskTitle.textContent = activeTask.title;
    taskAward.textContent = `${activeTask.award_title.toUpperCase()} · ${activeTask.slots} SUẤT CÒN LẠI`;
    taskDescription.textContent = activeTask.description;
    drawApp.querySelectorAll('[data-draw-task]').forEach((button) => {
      button.classList.toggle('active', button.dataset.drawTask === activeTask.key);
    });
    manualTask.value = activeTask.key;
    manualCandidate.replaceChildren();
    candidateList.replaceChildren();
    candidateNames(activeTask).forEach((name, index) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      manualCandidate.append(option);
      const chip = document.createElement('span');
      const dot = document.createElement('i');
      dot.style.setProperty('--candidate-color', palette[index % palette.length]);
      chip.append(dot, document.createTextNode(name));
      candidateList.append(chip);
    });
    drawWheel();
  };

  tasks.forEach((task) => {
    const option = document.createElement('option');
    option.value = task.key;
    option.textContent = `${task.award_title} (${task.candidates.length} người)`;
    manualTask.append(option);
  });
  drawApp.querySelectorAll('[data-draw-task]').forEach((button) => {
    button.addEventListener('click', () => !spinning && populateTask(button.dataset.drawTask));
  });
  manualTask.addEventListener('change', () => !spinning && populateTask(manualTask.value));

  const addConfetti = () => {
    const container = winnerDialog.querySelector('[data-confetti]');
    container.innerHTML = '';
    for (let index = 0; index < 38; index += 1) {
      const piece = document.createElement('i');
      piece.style.setProperty('--x', `${Math.random() * 100}%`);
      piece.style.setProperty('--delay', `${Math.random() * .7}s`);
      piece.style.setProperty('--spin', `${360 + Math.random() * 720}deg`);
      piece.style.setProperty('--confetti', palette[index % palette.length]);
      container.append(piece);
    }
  };

  const animateToWinner = (winner) => new Promise((resolve) => {
    const names = candidateNames(activeTask);
    const winnerIndex = names.findIndex((name) => name === winner);
    const arc = Math.PI * 2 / names.length;
    const normalized = ((rotation % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
    const desired = ((Math.PI * 2 - ((winnerIndex + .5) * arc)) + Math.PI * 2) % (Math.PI * 2);
    const correction = (desired - normalized + Math.PI * 2) % (Math.PI * 2);
    const startRotation = rotation;
    const targetRotation = rotation + Math.PI * 2 * 7 + correction;
    const startedAt = performance.now();
    const duration = 5600;
    const tick = (now) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - progress, 5);
      rotation = startRotation + (targetRotation - startRotation) * eased;
      drawWheel();
      if (progress < 1) requestAnimationFrame(tick);
      else resolve();
    };
    requestAnimationFrame(tick);
  });

  spinButton.addEventListener('click', async () => {
    if (spinning) return;
    spinning = true;
    spinButton.disabled = true;
    spinButton.classList.add('spinning');
    spinStatus.textContent = 'Đang xác định kết quả...';
    try {
      const response = await fetch('/admin/boc-tham/quay', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({month: document.querySelector('[data-month-value]').value, draw_key: activeTask.key}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Không thể bốc thăm.');
      await animateToWinner(result.winner);
      winnerDialog.querySelector('[data-winner-name]').textContent = result.winner;
      winnerDialog.querySelector('[data-winner-title]').textContent = result.title;
      addConfetti();
      winnerDialog.showModal();
    } catch (error) {
      alert(error.message);
      spinning = false;
      spinButton.disabled = false;
      spinButton.classList.remove('spinning');
      spinStatus.textContent = 'Chạm vào vòng quay để thử lại';
    }
  });
  document.querySelector('[data-finish-draw]')?.addEventListener('click', () => window.location.reload());
  populateTask(activeTask.key);
}

setTimeout(() => document.querySelectorAll('.flash').forEach((item) => item.remove()), 4500);

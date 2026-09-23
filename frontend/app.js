// Percepta Frontend Application Logic
const API_BASE = '/api';

const state = {
  token: localStorage.getItem('percepta_token'),
  user: null,
  activeTab: 'tab-dashboard',
  cameras: [],
  recordingsTree: [],
  selectedFile: null,
  pollTimer: null,
  logTimer: null
};

// --- Initialization & Lucide Icons ---
document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  setupEventListeners();
  checkAuth();
});

function refreshIcons() {
  setTimeout(() => lucide.createIcons(), 50);
}

// --- Authentication ---
function checkAuth() {
  if (!state.token) {
    showLoginModal();
    return;
  }

  fetch(`${API_BASE}/auth/me`, {
    headers: { 'Authorization': `Bearer ${state.token}` }
  })
  .then(res => {
    if (!res.ok) throw new Error('Unauthenticated');
    return res.json();
  })
  .then(user => {
    state.user = user;
    document.getElementById('nav-username').textContent = user.username;
    document.getElementById('nav-role').textContent = user.role;
    hideLoginModal();
    startApp();
  })
  .catch(() => {
    localStorage.removeItem('percepta_token');
    state.token = null;
    showLoginModal();
  });
}

function showLoginModal() {
  document.getElementById('login-modal').classList.remove('hidden');
}

function hideLoginModal() {
  document.getElementById('login-modal').classList.add('hidden');
}

function startApp() {
  loadDashboardData();
  startPeriodicPolling();
}

function startPeriodicPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    fetchSystemStats();
  }, 3000);
}

// --- Navigation Tabs ---
function switchTab(tabId) {
  state.activeTab = tabId;

  document.querySelectorAll('.nav-link').forEach(btn => {
    if (btn.getAttribute('data-tab') === tabId) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  document.querySelectorAll('.tab-content').forEach(section => {
    if (section.id === tabId) {
      section.classList.remove('hidden');
    } else {
      section.classList.add('hidden');
    }
  });

  refreshIcons();

  // Load tab-specific data
  if (tabId === 'tab-dashboard') loadDashboardData();
  if (tabId === 'tab-recordings') loadRecordings();
  if (tabId === 'tab-cameras') loadCameras();
  if (tabId === 'tab-settings') loadSettings();
  if (tabId === 'tab-github') loadGitHubSettings();
  if (tabId === 'tab-logs') {
    loadLogs();
    startLogPolling();
  } else {
    stopLogPolling();
  }
  if (tabId === 'tab-users') loadUsers();
}

// --- Fetch Helper with JWT ---
async function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  options.headers = headers;

  const res = await fetch(url, options);
  if (res.status === 401) {
    localStorage.removeItem('percepta_token');
    state.token = null;
    showLoginModal();
    throw new Error('Session expired.');
  }
  return res;
}

// --- System & Resource Stats (Raspberry Pi Safeguard) ---
async function fetchSystemStats() {
  try {
    const res = await apiFetch(`${API_BASE}/system/stats`);
    if (!res.ok) return;
    const data = await res.json();

    // RAM stats
    const ram = data.ram;
    const ramPct = ram.used_percent;
    const ramLimit = ram.limit_percent;

    document.getElementById('top-ram-val').textContent = `${ramPct}% / ${ramLimit}%`;
    const ramBar = document.getElementById('top-ram-bar');
    ramBar.style.width = `${Math.min(ramPct, 100)}%`;

    const ramHealth = document.getElementById('stat-ram-health');
    if (ramPct >= ramLimit) {
      ramBar.className = 'h-full bg-red-500 transition-all duration-500';
      if (ramHealth) {
        ramHealth.textContent = `Throttling (${ramPct}%)`;
        ramHealth.className = 'text-2xl font-bold text-red-400';
      }
    } else {
      ramBar.className = 'h-full bg-emerald-500 transition-all duration-500';
      if (ramHealth) {
        ramHealth.textContent = `Safe (<${ramLimit}%)`;
        ramHealth.className = 'text-2xl font-bold text-emerald-400';
      }
    }

    // Disk stats
    const disk = data.disk;
    document.getElementById('top-disk-val').textContent = `${disk.free_gb} GB Free`;
    const diskBar = document.getElementById('top-disk-bar');
    diskBar.style.width = `${disk.used_percent}%`;
    const statDiskFree = document.getElementById('stat-disk-free');
    if (statDiskFree) statDiskFree.textContent = `${disk.free_gb} GB`;

    // Sync status badge
    const sync = data.sync_status;
    const syncMsg = document.getElementById('sync-msg');
    const syncDot = document.getElementById('sync-dot');

    if (sync.is_running) {
      syncMsg.textContent = `${sync.message || 'Syncing...'}`;
      syncDot.className = 'w-2 h-2 rounded-full bg-blue-500 animate-ping';
    } else {
      syncMsg.textContent = 'Sync: Idle';
      syncDot.className = 'w-2 h-2 rounded-full bg-emerald-500';
    }

  } catch (err) {
    console.error('Stats poll error:', err);
  }
}

// --- Dashboard ---
async function loadDashboardData() {
  await fetchSystemStats();
  try {
    const [camsRes, recRes] = await Promise.all([
      apiFetch(`${API_BASE}/cameras`),
      apiFetch(`${API_BASE}/storage/browse`)
    ]);

    if (camsRes.ok) {
      const cams = await camsRes.json();
      state.cameras = cams;
      document.getElementById('stat-cameras-count').textContent = cams.length;
      renderDashboardCameras(cams);
    }

    if (recRes.ok) {
      const rec = await recRes.json();
      document.getElementById('stat-days-count').textContent = rec.tree ? rec.tree.length : 0;
    }
  } catch (err) {
    console.error('Dashboard load error:', err);
  }
}

function renderDashboardCameras(cams) {
  const container = document.getElementById('dash-cameras-list');
  if (!cams.length) {
    container.innerHTML = `
      <div class="col-span-full py-8 text-center text-xs text-slate-500">
        No cameras added yet. Click <strong>Cameras</strong> in the sidebar to add your first camera.
      </div>
    `;
    return;
  }

  container.innerHTML = cams.map(cam => `
    <div class="bg-slate-900 border border-darkborder rounded-xl p-4 flex flex-col justify-between">
      <div>
        <div class="flex items-center justify-between mb-2">
          <h4 class="font-bold text-sm text-slate-200">${cam.name}</h4>
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${cam.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700 text-slate-400'}">
            ${cam.enabled ? 'ENABLED' : 'DISABLED'}
          </span>
        </div>
        <p class="text-xs text-slate-400 font-mono mb-2">${cam.ip}</p>
        <p class="text-[11px] text-slate-400">Status: <span class="text-slate-300 font-medium">${cam.last_status || 'idle'}</span></p>
        <p class="text-[11px] text-slate-500">Last Sync: ${cam.last_sync ? new Date(cam.last_sync).toLocaleString() : 'Never'}</p>
      </div>
      <div class="mt-4 pt-3 border-t border-darkborder flex justify-end">
        <button onclick="triggerCameraSync(${cam.id})" class="bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5">
          <i data-lucide="refresh-cw" class="w-3 h-3"></i>
          <span>Sync Now</span>
        </button>
      </div>
    </div>
  `).join('');
  refreshIcons();
}

// --- Recordings Tree & Video Player ---
async function loadRecordings() {
  const container = document.getElementById('recordings-tree-container');
  container.innerHTML = '<div class="text-center py-12 text-slate-500 text-xs">Loading footage directory...</div>';

  try {
    const res = await apiFetch(`${API_BASE}/storage/browse`);
    if (!res.ok) throw new Error('Failed to load recordings');
    const data = await res.json();
    state.recordingsTree = data.tree || [];

    renderRecordingsTree(state.recordingsTree, data.archives || []);
  } catch (err) {
    container.innerHTML = `<div class="text-center py-12 text-red-400 text-xs">Error loading recordings: ${err.message}</div>`;
  }
}

function renderRecordingsTree(datesList, archivesList) {
  const container = document.getElementById('recordings-tree-container');
  if (!datesList.length && !archivesList.length) {
    container.innerHTML = `
      <div class="text-center py-12 text-slate-500 text-xs">
        No recordings downloaded yet. Run a sync or wait for the scheduled time.
      </div>
    `;
    return;
  }

  let html = '';

  // Dates tree
  datesList.forEach((dateGroup, dIdx) => {
    html += `
      <div class="mb-3">
        <div class="flex items-center justify-between p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800/80 cursor-pointer font-semibold text-xs text-slate-300" onclick="toggleTreeCollapse('date-${dIdx}')">
          <div class="flex items-center gap-2">
            <i data-lucide="calendar" class="w-3.5 h-3.5 text-blue-400"></i>
            <span>${dateGroup.date}</span>
            <span class="text-[10px] text-slate-500 font-normal">(${dateGroup.total_files} clips, ${dateGroup.total_size_mb} MB)</span>
          </div>
          <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-500"></i>
        </div>

        <div id="date-${dIdx}" class="tree-node-date mt-1 space-y-2">
          ${dateGroup.cameras.map((camGroup, cIdx) => `
            <div>
              <div class="flex items-center gap-2 py-1 px-2 font-medium text-xs text-slate-400">
                <i data-lucide="camera" class="w-3 h-3 text-slate-500"></i>
                <span class="text-slate-300 font-semibold">${camGroup.name}</span>
                <span class="text-[10px] text-slate-500">(${camGroup.total_files} clips)</span>
              </div>
              <div class="pl-4 space-y-1 mt-1">
                ${camGroup.files.map(file => `
                  <div 
                    class="tree-file-item border border-transparent p-2 rounded-lg flex items-center justify-between cursor-pointer transition-colors text-xs text-slate-400"
                    onclick="selectVideo('${dateGroup.date}', '${camGroup.name}', '${file.name}', '${file.time_label}', ${file.size_mb})"
                  >
                    <div class="flex items-center gap-2 truncate">
                      <i data-lucide="film" class="w-3 h-3 text-blue-400 shrink-0"></i>
                      <span class="truncate text-slate-300">${file.time_label}</span>
                    </div>
                    <span class="text-[10px] text-slate-500 shrink-0 ml-2">${file.size_mb} MB</span>
                  </div>
                `).join('')}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  });

  // Archives section if any
  if (archivesList.length) {
    html += `
      <div class="mt-6 pt-4 border-t border-darkborder">
        <h4 class="text-xs font-bold uppercase text-purple-400 mb-2 flex items-center gap-1.5">
          <i data-lucide="archive" class="w-3.5 h-3.5"></i>
          <span>Weekly ZIP Archives (${archivesList.length})</span>
        </h4>
        <div class="space-y-1">
          ${archivesList.map(a => `
            <div class="flex items-center justify-between p-2 rounded-lg bg-slate-900 border border-darkborder text-xs">
              <div class="flex items-center gap-2 truncate">
                <i data-lucide="file-archive" class="w-3.5 h-3.5 text-purple-400 shrink-0"></i>
                <span class="truncate text-slate-300">${a.name}</span>
              </div>
              <a href="${API_BASE}/storage/archive/download/${a.name}" class="text-blue-400 hover:text-blue-300 font-medium ml-2 shrink-0">
                Download (${a.size_mb} MB)
              </a>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
  refreshIcons();
}

function toggleTreeCollapse(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.classList.toggle('hidden');
}

function selectVideo(dateStr, camName, fileName, timeLabel, sizeMb) {
  state.selectedFile = { dateStr, camName, fileName };

  document.getElementById('player-title').textContent = `${camName} - ${timeLabel}`;
  document.getElementById('player-subtitle').textContent = `Date: ${dateStr} • File: ${fileName} • ${sizeMb} MB`;
  document.getElementById('player-time-range').textContent = timeLabel;

  // Setup streaming URL
  const streamUrl = `${API_BASE}/storage/stream/${dateStr}/${camName}/${fileName}`;
  const videoPlayer = document.getElementById('main-video-player');
  const placeholder = document.getElementById('video-placeholder');

  videoPlayer.src = streamUrl;
  placeholder.classList.add('hidden');
  videoPlayer.load();
  videoPlayer.play().catch(e => console.log('Autoplay prevented:', e));

  // Action buttons
  const dlBtn = document.getElementById('btn-download-clip');
  dlBtn.href = `${API_BASE}/storage/download/${dateStr}/${camName}/${fileName}`;
  dlBtn.classList.remove('hidden');

  const delBtn = document.getElementById('btn-delete-clip');
  delBtn.classList.remove('hidden');
  delBtn.onclick = () => deleteClip(dateStr, camName, fileName);

  refreshIcons();
}

async function deleteClip(dateStr, camName, fileName) {
  if (!confirm(`Are you sure you want to delete ${fileName}?`)) return;

  try {
    const res = await apiFetch(`${API_BASE}/storage/file/${dateStr}/${camName}/${fileName}`, {
      method: 'DELETE'
    });
    if (res.ok) {
      loadRecordings();
      document.getElementById('player-title').textContent = 'No footage selected';
      document.getElementById('player-subtitle').textContent = 'Select a clip from the tree to play';
      document.getElementById('main-video-player').src = '';
      document.getElementById('video-placeholder').classList.remove('hidden');
      document.getElementById('btn-download-clip').classList.add('hidden');
      document.getElementById('btn-delete-clip').classList.add('hidden');
    }
  } catch (err) {
    alert('Failed to delete file: ' + err.message);
  }
}

// --- Cameras Management ---
async function loadCameras() {
  const tbody = document.getElementById('cameras-table-body');
  try {
    const res = await apiFetch(`${API_BASE}/cameras`);
    if (!res.ok) throw new Error('Failed to load cameras');
    const cams = await res.json();
    state.cameras = cams;

    if (!cams.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="px-5 py-8 text-center text-slate-500">
            No cameras registered. Click <strong>Add Tapo Camera</strong> above to add one.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = cams.map(c => `
      <tr class="hover:bg-slate-800/40 transition-colors">
        <td class="px-5 py-3.5 font-bold text-slate-200">${c.name}</td>
        <td class="px-5 py-3.5 font-mono text-slate-400">${c.ip}</td>
        <td class="px-5 py-3.5 text-slate-400">${c.window_size} pkts</td>
        <td class="px-5 py-3.5">
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${c.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700 text-slate-400'}">
            ${c.enabled ? 'Active' : 'Disabled'}
          </span>
          <span class="text-[11px] text-slate-500 block mt-0.5">${c.last_status || 'idle'}</span>
        </td>
        <td class="px-5 py-3.5 text-slate-400">
          ${c.last_sync ? new Date(c.last_sync).toLocaleString() : 'Never'}
        </td>
        <td class="px-5 py-3.5 text-right space-x-2">
          <button onclick="triggerCameraSync(${c.id})" title="Sync Now" class="bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors">
            Sync
          </button>
          <button onclick="openEditCameraModal(${c.id})" class="p-1 hover:text-blue-400 text-slate-400 transition-colors">
            <i data-lucide="edit-3" class="w-4 h-4"></i>
          </button>
          <button onclick="deleteCamera(${c.id})" class="p-1 hover:text-red-400 text-slate-400 transition-colors">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `).join('');
    refreshIcons();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-5 py-8 text-center text-red-400">${err.message}</td></tr>`;
  }
}

function openAddCameraModal() {
  document.getElementById('camera-modal-title').textContent = 'Add Tapo Camera';
  document.getElementById('cam-id').value = '';
  document.getElementById('cam-name').value = '';
  document.getElementById('cam-ip').value = '';
  document.getElementById('cam-cloud-password').value = '';
  document.getElementById('cam-user').value = 'admin';
  document.getElementById('cam-password').value = '';
  document.getElementById('cam-window-size').value = '50';
  document.getElementById('cam-enabled').checked = true;
  document.getElementById('cam-test-result').classList.add('hidden');
  document.getElementById('camera-modal').classList.remove('hidden');
  refreshIcons();
}

function openEditCameraModal(camId) {
  const cam = state.cameras.find(c => c.id === camId);
  if (!cam) return;

  document.getElementById('camera-modal-title').textContent = 'Edit Tapo Camera';
  document.getElementById('cam-id').value = cam.id;
  document.getElementById('cam-name').value = cam.name;
  document.getElementById('cam-ip').value = cam.ip;
  document.getElementById('cam-cloud-password').value = ''; // leave blank to keep unchanged
  document.getElementById('cam-cloud-password').required = false;
  document.getElementById('cam-user').value = cam.user || 'admin';
  document.getElementById('cam-password').value = '';
  document.getElementById('cam-window-size').value = cam.window_size || 50;
  document.getElementById('cam-enabled').checked = cam.enabled;
  document.getElementById('cam-test-result').classList.add('hidden');
  document.getElementById('camera-modal').classList.remove('hidden');
  refreshIcons();
}

async function triggerCameraSync(camId) {
  try {
    const res = await apiFetch(`${API_BASE}/cameras/${camId}/sync`, { method: 'POST' });
    const data = await res.json();
    alert(data.message || 'Sync initiated!');
    fetchSystemStats();
  } catch (err) {
    alert('Failed to trigger sync: ' + err.message);
  }
}

async function triggerAllSync() {
  try {
    const res = await apiFetch(`${API_BASE}/cameras/sync-all`, { method: 'POST' });
    const data = await res.json();
    alert(data.message || 'Sequential sync initiated across all cameras!');
    fetchSystemStats();
  } catch (err) {
    alert('Failed to trigger sync: ' + err.message);
  }
}

async function deleteCamera(camId) {
  if (!confirm('Are you sure you want to delete this camera configuration? Footage on disk will NOT be deleted.')) return;
  try {
    const res = await apiFetch(`${API_BASE}/cameras/${camId}`, { method: 'DELETE' });
    if (res.ok) {
      loadCameras();
    }
  } catch (err) {
    alert('Failed to delete camera: ' + err.message);
  }
}

// --- Settings ---
async function loadSettings() {
  try {
    const res = await apiFetch(`${API_BASE}/settings`);
    if (!res.ok) throw new Error('Failed to load settings');
    const s = await res.json();

    document.getElementById('setting-storage-path').value = s.storage_path;
    document.getElementById('setting-ram-limit').value = s.ram_limit_pct;
    document.getElementById('label-ram-limit').textContent = `${s.ram_limit_pct}%`;
    document.getElementById('setting-schedule-enabled').checked = s.schedule_enabled;
    document.getElementById('setting-schedule-mode').value = s.schedule_mode;
    document.getElementById('setting-schedule-time').value = s.schedule_time;
    document.getElementById('setting-schedule-interval').value = s.schedule_interval_hours;
    document.getElementById('setting-weekly-zip').checked = s.weekly_zip_enabled;
    document.getElementById('setting-retention-days').value = s.retention_days;

    toggleScheduleModeVisibility(s.schedule_mode);
  } catch (err) {
    console.error('Settings load error:', err);
  }
}

function toggleScheduleModeVisibility(mode) {
  const wrapTime = document.getElementById('wrap-schedule-time');
  const wrapInterval = document.getElementById('wrap-schedule-interval');
  if (mode === 'interval') {
    wrapTime.classList.add('hidden');
    wrapInterval.classList.remove('hidden');
  } else {
    wrapTime.classList.remove('hidden');
    wrapInterval.classList.add('hidden');
  }
}

// --- GitHub Backup ---
async function loadGitHubSettings() {
  try {
    const res = await apiFetch(`${API_BASE}/settings`);
    if (!res.ok) return;
    const s = await res.json();

    document.getElementById('gh-backup-enabled').checked = s.github_backup_enabled;
    document.getElementById('gh-repo-url').value = s.github_repo_url;
    document.getElementById('gh-token').placeholder = s.has_github_token ? `Current: ${s.github_token}` : 'ghp_••••••••••••••••••••••••••••••••••••';
    document.getElementById('gh-token').value = '';
    document.getElementById('gh-branch').value = s.github_branch || 'main';
    document.getElementById('gh-last-time').textContent = s.last_github_backup || 'Never';
  } catch (err) {
    console.error('GitHub settings load error:', err);
  }
}

async function triggerGitHubBackupNow() {
  const btn = document.getElementById('btn-backup-github-now');
  const originalText = btn.innerHTML;
  btn.innerHTML = '<span>Backing up...</span>';
  btn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/settings/github/backup-now`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      alert('GitHub backup completed successfully!\n' + data.message);
      loadGitHubSettings();
    } else {
      alert('GitHub backup failed:\n' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Error running backup: ' + err.message);
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
    refreshIcons();
  }
}

// --- System Logs ---
async function loadLogs() {
  const container = document.getElementById('log-terminal');
  const level = document.getElementById('log-filter-level').value;

  try {
    const url = `${API_BASE}/system/logs?lines=200${level ? `&level=${level}` : ''}`;
    const res = await apiFetch(url);
    if (!res.ok) throw new Error('Failed to fetch logs');
    const data = await res.json();

    if (!data.logs || !data.logs.length) {
      container.innerHTML = `<div class="text-slate-500">No logs found in ${data.log_file}</div>`;
      return;
    }

    container.innerHTML = data.logs.map(line => {
      let cls = 'text-slate-300';
      if (line.includes('[INFO]')) cls = 'log-info';
      if (line.includes('[WARNING]')) cls = 'log-warning';
      if (line.includes('[ERROR]')) cls = 'log-error';
      return `<div class="${cls} leading-5">${escapeHtml(line)}</div>`;
    }).join('');

    container.scrollTop = container.scrollHeight;
  } catch (err) {
    container.innerHTML = `<div class="text-red-400">Error loading logs: ${err.message}</div>`;
  }
}

function startLogPolling() {
  if (state.logTimer) clearInterval(state.logTimer);
  state.logTimer = setInterval(() => {
    if (state.activeTab === 'tab-logs') {
      loadLogs();
    }
  }, 4000);
}

function stopLogPolling() {
  if (state.logTimer) {
    clearInterval(state.logTimer);
    state.logTimer = null;
  }
}

// --- Users Management ---
async function loadUsers() {
  const tbody = document.getElementById('users-table-body');
  try {
    const res = await apiFetch(`${API_BASE}/users`);
    if (!res.ok) throw new Error('Failed to load users');
    const users = await res.json();

    tbody.innerHTML = users.map(u => `
      <tr class="hover:bg-slate-800/40 transition-colors">
        <td class="px-5 py-3.5 font-bold text-slate-200">${u.username}</td>
        <td class="px-5 py-3.5"><span class="px-2 py-0.5 rounded text-[10px] uppercase font-semibold bg-slate-800 text-slate-300">${u.role}</span></td>
        <td class="px-5 py-3.5 text-slate-400">${new Date(u.created_at).toLocaleDateString()}</td>
        <td class="px-5 py-3.5 text-right">
          ${u.id !== state.user.id ? `
            <button onclick="deleteUserAccount(${u.id}, '${u.username}')" class="text-slate-400 hover:text-red-400 p-1 transition-colors">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          ` : '<span class="text-[10px] text-slate-500 italic">Current User</span>'}
        </td>
      </tr>
    `).join('');
    refreshIcons();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="px-5 py-8 text-center text-red-400">${err.message}</td></tr>`;
  }
}

async function deleteUserAccount(userId, username) {
  if (!confirm(`Delete user '${username}'?`)) return;
  try {
    const res = await apiFetch(`${API_BASE}/users/${userId}`, { method: 'DELETE' });
    if (res.ok) loadUsers();
  } catch (err) {
    alert('Failed to delete user: ' + err.message);
  }
}

// --- Helpers ---
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- Setup Event Listeners ---
function setupEventListeners() {
  // Navigation Tabs
  document.querySelectorAll('.nav-link').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.getAttribute('data-tab'));
    });
  });

  // Logout
  document.getElementById('btn-logout').addEventListener('click', () => {
    localStorage.removeItem('percepta_token');
    state.token = null;
    state.user = null;
    showLoginModal();
  });

  // Login Form
  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errDiv = document.getElementById('login-error');
    errDiv.classList.add('hidden');

    const formData = new FormData();
    formData.append('username', document.getElementById('login-username').value.trim());
    formData.append('password', document.getElementById('login-password').value);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Login failed');
      }

      const data = await res.json();
      state.token = data.access_token;
      localStorage.setItem('percepta_token', data.access_token);
      checkAuth();
    } catch (err) {
      errDiv.textContent = err.message;
      errDiv.classList.remove('hidden');
    }
  });

  // Dashboard Sync All Button
  document.getElementById('btn-sync-all-now').addEventListener('click', triggerAllSync);

  // Recordings Refresh
  document.getElementById('btn-refresh-recordings').addEventListener('click', loadRecordings);

  // Playback speed
  document.getElementById('playback-speed').addEventListener('change', (e) => {
    const video = document.getElementById('main-video-player');
    video.playbackRate = parseFloat(e.target.value);
  });

  // Add Camera Modal triggers
  document.getElementById('btn-open-add-camera').addEventListener('click', openAddCameraModal);
  document.getElementById('btn-close-camera-modal').addEventListener('click', () => {
    document.getElementById('camera-modal').classList.add('hidden');
  });
  document.getElementById('btn-cancel-cam-modal').addEventListener('click', () => {
    document.getElementById('camera-modal').classList.add('hidden');
  });

  // Test Camera Connection Button
  document.getElementById('btn-test-camera').addEventListener('click', async () => {
    const ip = document.getElementById('cam-ip').value.trim();
    const cloudPass = document.getElementById('cam-cloud-password').value;
    const user = document.getElementById('cam-user').value.trim() || 'admin';
    const pass = document.getElementById('cam-password').value;

    const resultDiv = document.getElementById('cam-test-result');
    resultDiv.className = 'text-xs p-2.5 rounded-xl bg-blue-950/40 text-blue-300 border border-blue-800/50';
    resultDiv.textContent = 'Testing connection to camera...';
    resultDiv.classList.remove('hidden');

    try {
      const res = await apiFetch(`${API_BASE}/cameras/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip, cloud_password: cloudPass, user, password: pass })
      });
      const data = await res.json();
      if (data.success) {
        resultDiv.className = 'text-xs p-2.5 rounded-xl bg-emerald-950/40 text-emerald-300 border border-emerald-800/50';
        resultDiv.textContent = `Success! Detected: ${data.device_name} (Model: ${data.model}, MAC: ${data.mac})`;
      } else {
        resultDiv.className = 'text-xs p-2.5 rounded-xl bg-red-950/40 text-red-300 border border-red-800/50';
        resultDiv.textContent = `Connection Failed: ${data.error}`;
      }
    } catch (err) {
      resultDiv.className = 'text-xs p-2.5 rounded-xl bg-red-950/40 text-red-300 border border-red-800/50';
      resultDiv.textContent = `Error: ${err.message}`;
    }
  });

  // Camera Form Submit (Add or Edit)
  document.getElementById('camera-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const camId = document.getElementById('cam-id').value;
    const payload = {
      name: document.getElementById('cam-name').value.trim(),
      ip: document.getElementById('cam-ip').value.trim(),
      cloud_password: document.getElementById('cam-cloud-password').value,
      user: document.getElementById('cam-user').value.trim() || 'admin',
      password: document.getElementById('cam-password').value,
      window_size: parseInt(document.getElementById('cam-window-size').value, 10) || 50,
      enabled: document.getElementById('cam-enabled').checked
    };

    try {
      let res;
      if (camId) {
        res = await apiFetch(`${API_BASE}/cameras/${camId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        res = await apiFetch(`${API_BASE}/cameras`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Save failed');
      }

      document.getElementById('camera-modal').classList.add('hidden');
      loadCameras();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  });

  // Settings Schedule Mode Switcher
  document.getElementById('setting-schedule-mode').addEventListener('change', (e) => {
    toggleScheduleModeVisibility(e.target.value);
  });

  // RAM limit slider label
  document.getElementById('setting-ram-limit').addEventListener('input', (e) => {
    document.getElementById('label-ram-limit').textContent = `${e.target.value}%`;
  });

  // Settings Form Submit
  document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      storage_path: document.getElementById('setting-storage-path').value.trim(),
      schedule_time: document.getElementById('setting-schedule-time').value,
      schedule_enabled: document.getElementById('setting-schedule-enabled').checked,
      schedule_mode: document.getElementById('setting-schedule-mode').value,
      schedule_interval_hours: parseInt(document.getElementById('setting-schedule-interval').value, 10) || 6,
      ram_limit_pct: parseInt(document.getElementById('setting-ram-limit').value, 10) || 90,
      retention_days: parseInt(document.getElementById('setting-retention-days').value, 10) || 30,
      weekly_zip_enabled: document.getElementById('setting-weekly-zip').checked,
      weekly_zip_day: 6,
      github_repo_url: document.getElementById('gh-repo-url') ? document.getElementById('gh-repo-url').value.trim() : '',
      github_token: document.getElementById('gh-token') ? document.getElementById('gh-token').value.trim() : '',
      github_branch: document.getElementById('gh-branch') ? document.getElementById('gh-branch').value.trim() : 'main',
      github_backup_enabled: document.getElementById('gh-backup-enabled') ? document.getElementById('gh-backup-enabled').checked : true
    };

    try {
      const res = await apiFetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Failed to update settings');
      alert('Settings saved and scheduler updated!');
    } catch (err) {
      alert('Error: ' + err.message);
    }
  });

  // Manual Archive & Purge buttons
  document.getElementById('btn-manual-archive').addEventListener('click', async () => {
    if (!confirm('Compress footage older than 7 days into weekly ZIP archives now?')) return;
    try {
      const res = await apiFetch(`${API_BASE}/storage/trigger-archive`, { method: 'POST' });
      const data = await res.json();
      alert(`Archive complete! Compressed ${data.archived_folders} folder(s).`);
    } catch (err) {
      alert('Archive failed: ' + err.message);
    }
  });

  document.getElementById('btn-manual-cleanup').addEventListener('click', async () => {
    if (!confirm('Purge all footages and archives older than retention threshold now?')) return;
    try {
      const res = await apiFetch(`${API_BASE}/storage/trigger-cleanup`, { method: 'POST' });
      const data = await res.json();
      alert(`Cleanup complete! Deleted ${data.deleted_items} old item(s).`);
    } catch (err) {
      alert('Cleanup failed: ' + err.message);
    }
  });

  // GitHub Form Submit
  document.getElementById('github-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      storage_path: document.getElementById('setting-storage-path').value.trim() || '/storage',
      schedule_time: document.getElementById('setting-schedule-time').value || '02:00',
      schedule_enabled: document.getElementById('setting-schedule-enabled').checked,
      schedule_mode: document.getElementById('setting-schedule-mode').value || 'daily',
      schedule_interval_hours: parseInt(document.getElementById('setting-schedule-interval').value, 10) || 6,
      ram_limit_pct: parseInt(document.getElementById('setting-ram-limit').value, 10) || 90,
      retention_days: parseInt(document.getElementById('setting-retention-days').value, 10) || 30,
      weekly_zip_enabled: document.getElementById('setting-weekly-zip').checked,
      weekly_zip_day: 6,
      github_repo_url: document.getElementById('gh-repo-url').value.trim(),
      github_token: document.getElementById('gh-token').value.trim(),
      github_branch: document.getElementById('gh-branch').value.trim() || 'main',
      github_backup_enabled: document.getElementById('gh-backup-enabled').checked
    };

    try {
      const res = await apiFetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Failed to update GitHub settings');
      alert('GitHub settings saved!');
      loadGitHubSettings();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  });

  // Backup Now button
  document.getElementById('btn-backup-github-now').addEventListener('click', triggerGitHubBackupNow);

  // System Logs buttons
  document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);
  document.getElementById('log-filter-level').addEventListener('change', loadLogs);
  document.getElementById('btn-clear-logs').addEventListener('click', async () => {
    if (!confirm('Clear all logs on the disk?')) return;
    try {
      await apiFetch(`${API_BASE}/system/logs`, { method: 'DELETE' });
      loadLogs();
    } catch (err) {
      alert('Failed to clear logs: ' + err.message);
    }
  });

  // User Management
  document.getElementById('btn-open-add-user').addEventListener('click', () => {
    document.getElementById('user-name-input').value = '';
    document.getElementById('user-password-input').value = '';
    document.getElementById('user-modal').classList.remove('hidden');
  });

  document.getElementById('btn-close-user-modal').addEventListener('click', () => {
    document.getElementById('user-modal').classList.add('hidden');
  });
  document.getElementById('btn-cancel-user-modal').addEventListener('click', () => {
    document.getElementById('user-modal').classList.add('hidden');
  });

  document.getElementById('user-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      username: document.getElementById('user-name-input').value.trim(),
      password: document.getElementById('user-password-input').value,
      role: document.getElementById('user-role-input').value
    };

    try {
      const res = await apiFetch(`${API_BASE}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create user');
      }
      document.getElementById('user-modal').classList.add('hidden');
      loadUsers();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  });

  // Change Password Form
  document.getElementById('change-pwd-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      old_password: document.getElementById('pwd-old').value,
      new_password: document.getElementById('pwd-new').value
    };

    try {
      const res = await apiFetch(`${API_BASE}/users/${state.user.id}/password`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to change password');
      }
      alert('Password updated successfully!');
      document.getElementById('change-pwd-form').reset();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  });
}

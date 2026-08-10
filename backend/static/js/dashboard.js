// Toast Notification System
class Toast {
    static show(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        else if (type === 'error') icon = 'fa-exclamation-circle';
        else if (type === 'warning') icon = 'fa-exclamation-triangle';

        toast.innerHTML = `
            <i class="fa-solid ${icon} toast-icon"></i>
            <div class="toast-content">${message}</div>
        `;

        container.appendChild(toast);
        
        setTimeout(() => { toast.classList.add('show'); }, 10);

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => { toast.remove(); }, 400);
        }, 4000);
    }
}

// Global Variables
let currentTab = 'live-camera';
let activeStreamInterval = null;
let registrationStream = null;
let registrationBase64Images = []; // Array to store multiple captured face images (base64)
let registeringFromUnknownCropId = null; // Track if we are registering an employee from gallery crop
let registeringFromUnknownCropUrl = null;
let charts = {};
let currentAnalyticsRange = 'week';
let activeCameraId = null;
let cameraDevices = [];

// Initialize Page
document.addEventListener('DOMContentLoaded', () => {
    initLiveClock();
    initHeader();
    initTimeDropdowns(); // Populate AM/PM shift hour options
    initTabs();
    initDateFilters();
    initResizers();
    
    const savedTheme = localStorage.getItem('workpulse-theme') || 'neon';
    setTheme(savedTheme);
    
    if (window.USER.isAuthenticated) {
        loadCameraDevices().then(() => {
            if (currentTab === 'live-camera') {
                startLiveDashboardPolling();
            }
        });
    } else {
        if (currentTab === 'live-camera') {
            startLiveDashboardPolling();
        }
    }
});

function initLiveClock() {
    const clockDisplay = document.getElementById('clock-display');
    const updateClock = () => {
        const now = new Date();
        clockDisplay.textContent = now.toLocaleTimeString('en-US', { hour12: true });
    };
    updateClock();
    setInterval(updateClock, 1000);
}

function initHeader() {
    const headerActions = document.getElementById('header-actions');
    const usernameDisplay = document.getElementById('username-display');
    const profileChip = document.querySelector('.profile-chip');
    
    if (window.USER.isAuthenticated) {
        usernameDisplay.textContent = window.USER.username;
        if (profileChip) profileChip.setAttribute('onclick', "switchTab('account')");
        headerActions.innerHTML = `
            <button class="btn btn-sm btn-muted" onclick="logoutAdmin()">
                <i class="fa-solid fa-right-from-bracket"></i> Logout
            </button>
        `;
    } else {
        usernameDisplay.textContent = 'Guest';
        if (profileChip) profileChip.setAttribute('onclick', "window.location.href='/auth'");
        headerActions.innerHTML = `
            <a href="/auth" class="btn btn-sm btn-primary">
                <i class="fa-solid fa-right-to-bracket"></i> Account
            </a>
        `;
    }
}

function initTabs() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.getAttribute('data-tab');
            switchTab(tabName);
        });
    });

    const accountTabLink = document.querySelector('.nav-item[data-tab="account"]');
    if (accountTabLink) {
        if (!window.USER.isAuthenticated) {
            accountTabLink.style.display = 'none';
        } else {
            accountTabLink.style.display = 'flex';
        }
    }

    // Fix Authentication State propagation & overlay toggles
    const guestOverlays = [
        'unknown-guest-overlay',
        'staff-guest-overlay',
        'analytics-guest-overlay',
        'reports-guest-overlay',
        'settings-guest-overlay',
        'account-guest-overlay'
    ];

    if (!window.USER.isAuthenticated) {
        guestOverlays.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.display = 'flex';
                const parent = el.closest('.tab-panel');
                if (parent) parent.classList.add('guest-locked');
            }
        });
    } else {
        guestOverlays.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.display = 'none';
                const parent = el.closest('.tab-panel');
                if (parent) parent.classList.remove('guest-locked');
            }
        });
    }
}

function switchTab(tabName) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-tab') === tabName) {
            item.classList.add('active');
        }
    });

    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    
    const activePanel = document.getElementById(`tab-${tabName}`);
    if (activePanel) {
        activePanel.classList.add('active');
    }

    const titles = {
        'live-camera': 'Live Channel Surveillance',
        'unknown-gallery': 'Unknown Faces Gallery',
        'staff': 'Staff Directory',
        'analytics': 'Analytics Hub',
        'ai-reports': 'AI Intelligence',
        'settings': 'Control Settings',
        'account': 'My Account Settings'
    };
    document.getElementById('page-title').textContent = titles[tabName] || 'Dashboard';
    
    if (tabName === 'account') {
        loadUserProfileData();
    }
    currentTab = tabName;

    // Control Polling
    if (tabName !== 'live-camera') {
        stopLiveDashboardPolling();
        if (activeStreamInterval) {
            stopCameraStream();
            Toast.show("Stream paused while navigating.", "info");
        }
    } else {
        startLiveDashboardPolling();
    }

    if (window.USER.isAuthenticated) {
        if (tabName === 'unknown-gallery') {
            loadUnknownFaces();
        } else if (tabName === 'staff') {
            loadStaffList();
            loadAttendanceLogs();
        } else if (tabName === 'analytics') {
            loadAnalytics();
        } else if (tabName === 'settings') {
            loadSettings();
        }
    }
}

function initDateFilters() {
    const today = new Date();
    const lastWeek = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000);
    const lastMonth = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
    
    const formatDate = (date) => date.toISOString().split('T')[0];
    
    document.getElementById('analytics-start-date').value = formatDate(lastWeek);
    document.getElementById('analytics-end-date').value = formatDate(today);
    
    document.getElementById('report-start-date').value = formatDate(lastMonth);
    document.getElementById('report-end-date').value = formatDate(today);
}

// ==========================================
// CAMERA STREAM & POLLING
// ==========================================
async function startCameraStream() {
    if (!window.USER.isAuthenticated) {
        document.getElementById('camera-stream').src = '/api/camera/feed';
        document.getElementById('btn-start-camera').disabled = true;
        document.getElementById('btn-stop-camera').disabled = false;
        document.getElementById('stream-overlay').style.display = 'none';
        document.getElementById('live-indicator').classList.add('active');
        return;
    }
    try {
        const response = await fetch('/api/camera/start', { method: 'POST' });
        if (response.ok) {
            document.getElementById('camera-stream').src = '/api/camera/feed';
            document.getElementById('btn-start-camera').disabled = true;
            document.getElementById('btn-stop-camera').disabled = false;
            document.getElementById('stream-overlay').style.display = 'none';
            document.getElementById('live-indicator').classList.add('active');
            Toast.show("Camera link established.", "success");
        }
    } catch (e) {
        console.error(e);
    }
}

async function stopCameraStream() {
    document.getElementById('camera-stream').src = '';
    document.getElementById('btn-start-camera').disabled = false;
    document.getElementById('btn-stop-camera').disabled = true;
    document.getElementById('stream-overlay').style.display = 'flex';
    document.getElementById('live-indicator').classList.remove('active');
    
    if (!window.USER.isAuthenticated) return;
    try {
        await fetch('/api/camera/stop', { method: 'POST' });
        Toast.show("Camera link closed.", "info");
    } catch (e) {
        console.error(e);
    }
}

async function triggerManualCapture() {
    try {
        const response = await fetch('/api/camera/manual-capture', { method: 'POST' });
        if (response.ok) {
            const data = await response.json();
            Toast.show(data.message, "success");
            setTimeout(() => {
                if (typeof loadUnknownFaces === 'function') {
                    loadUnknownFaces();
                }
            }, 800);
        } else {
            const err = await response.json();
            Toast.show(err.error || "Capture request failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error sending capture request.", "error");
    }
}

function startLiveDashboardPolling() {
    if (!window.USER.isAuthenticated) return;
    const poll = async () => {
        try {
            const response = await fetch('/api/camera/dashboard_live');
            if (response.ok) {
                const data = await response.json();
                renderLiveDashboard(data);
            }
        } catch (e) {
            console.error(e);
        }
    };
    poll();
    activeStreamInterval = setInterval(poll, 2000);
}

function stopLiveDashboardPolling() {
    if (activeStreamInterval) {
        clearInterval(activeStreamInterval);
        activeStreamInterval = null;
    }
}

function renderLiveDashboard(data) {
    // KPIs
    document.getElementById('kpi-current-employees').textContent = data.kpis.current_employees;
    document.getElementById('kpi-customers').textContent = data.kpis.customers;
    document.getElementById('kpi-current-unknowns').textContent = data.kpis.current_unknowns;
    if (document.getElementById('kpi-unknown-entries-today')) {
        document.getElementById('kpi-unknown-entries-today').textContent = data.kpis.unknown_entries_today || 0;
    }
    document.getElementById('kpi-working-employees').textContent = data.kpis.working_employees;
    document.getElementById('kpi-idle-employees').textContent = data.kpis.idle_employees;
    document.getElementById('kpi-phone-alerts').textContent = data.kpis.phone_alerts;
    document.getElementById('kpi-security-alerts').textContent = data.kpis.security_alerts;
    if (document.getElementById('kpi-restricted-breaches')) {
        document.getElementById('kpi-restricted-breaches').textContent = data.kpis.restricted_breaches || 0;
    }
    document.getElementById('kpi-accuracy').textContent = `${data.kpis.recognition_accuracy}%`;
    document.getElementById('kpi-cam-status').textContent = data.kpis.camera_status;
    
    const camStatus = document.getElementById('kpi-cam-status');
    const isCamOnline = data.kpis.camera_status === 'Online';
    if (isCamOnline) {
        camStatus.className = "kpi-val text-success";
    } else {
        camStatus.className = "kpi-val text-muted";
    }
    updateSurveillanceStatus(isCamOnline);

    // Toggle Clear All Alerts Button
    const clearAlertsBtn = document.getElementById('btn-clear-all-alerts');
    if (clearAlertsBtn) {
        clearAlertsBtn.style.display = (!data.alerts || data.alerts.length === 0) ? 'none' : 'block';
    }

    // Sidebar Alerts empty states
    const alertsList = document.getElementById('live-alerts-list');
    if (!data.alerts || data.alerts.length === 0) {
        alertsList.innerHTML = `
            <div class="empty-list-placeholder" style="padding:20px; text-align:center;">
                <i class="fa-regular fa-bell-slash" style="font-size:24px; color:var(--text-muted); margin-bottom:8px;"></i>
                <p style="font-size:11px; color:var(--text-muted);">No active alerts logged.</p>
            </div>
        `;
    } else {
        alertsList.innerHTML = data.alerts.map(a => {
            const hasFace = a.face_crop_path;
            const hasDuration = a.type === 'restricted_zone_intrusion' && a.duration !== undefined;
            return `
                <div class="alert-card-item ${a.severity}" style="position: relative; overflow: hidden; padding: 10px; margin-bottom: 8px; border-radius: 6px;">
                    <button onclick="deleteAlertEvent(${a.id})" style="position: absolute; top: 8px; right: 8px; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 11px; transition: color 0.2s; z-index: 5;" onmouseover="this.style.color='var(--error)'" onmouseout="this.style.color='var(--text-muted)'">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                    <div class="alert-meta" style="padding-right: 18px;">
                        <span>${a.type.toUpperCase().replace(/_/g, ' ')}</span>
                        <span>${a.timestamp}</span>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 6px; align-items: flex-start;">
                        ${hasFace ? `<img src="${a.face_crop_path}" style="width: 44px; height: 44px; border-radius: 4px; object-fit: cover; border: 1px solid var(--border-color); flex-shrink: 0;" alt="Face">` : ''}
                        <div style="flex-grow: 1;">
                            <div style="font-weight: 500; font-size: 13px; line-height: 1.4;">${a.description}</div>
                            ${hasDuration ? `
                                <div style="font-size: 11px; margin-top: 4px; color: var(--accent); font-weight: 600;">
                                    <i class="fa-solid fa-clock"></i> Duration: ${a.duration}s
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    ${a.snapshot_path ? `<img src="${a.snapshot_path}" class="alert-snapshot-crop" style="margin-top: 8px; width: 100%; border-radius: 4px; display: block; object-fit: cover; max-height: 120px;" alt="Snapshot">` : ''}
                </div>
            `;
        }).join('');
    }

    // Active Employees Directory Table Empty states
    const empTable = document.getElementById('live-employees-table-body');
    if (!data.active_employees || data.active_employees.length === 0) {
        empTable.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 15px; font-size:11px;">No employees checked in.</td></tr>`;
    } else {
        empTable.innerHTML = data.active_employees.map(att => {
            let nameHtml = `<strong>${att.name}</strong>`;
            if (att.is_overtime) {
                nameHtml += ` <span class="status-badge error" style="background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 8px; padding: 1px 4px; vertical-align: middle; margin-left: 4px; font-weight: 700; text-transform: uppercase; border-radius: 4px;">Overtime</span>`;
            }
            return `
                <tr>
                    <td>${nameHtml}<br><span style="font-size: 10px; color: var(--text-muted);">${att.position}</span></td>
                    <td>${att.department}</td>
                    <td><span class="status-badge ${att.state.toLowerCase()}">${att.state}</span></td>
                    <td style="font-variant-numeric: tabular-nums;">${att.check_in}</td>
                    <td style="font-weight: 600; color: ${att.score >= 80 ? 'var(--success)' : 'var(--error)'};">${att.score}%</td>
                </tr>
            `;
        }).join('');
    }

    // Chronological Activity Timeline empty states
    const timelineList = document.getElementById('activity-timeline-list');
    if (!data.timeline || data.timeline.length === 0) {
        timelineList.innerHTML = `
            <div class="empty-list-placeholder" style="padding:20px; text-align:center;">
                <i class="fa-solid fa-list-check" style="font-size:24px; color:var(--text-muted); margin-bottom:8px;"></i>
                <p style="font-size:11px; color:var(--text-muted);">No timeline events logged yet today.</p>
            </div>
        `;
    } else {
        timelineList.innerHTML = data.timeline.map(t => `
            <div class="timeline-item">
                <span class="timeline-dot ${t.severity}"></span>
                <div style="font-weight: 500;">${t.message}</div>
                <div class="timeline-time">${t.time}</div>
            </div>
        `).join('');
    }

    // Unknown Face thumbnails row empty states
    const unknownRow = document.getElementById('unknown-preview-row');
    const badge = document.getElementById('sidebar-unknown-badge');
    const totalU = data.kpis.total_unknowns || 0;
    if (badge) {
        if (totalU === 0) {
            badge.style.display = 'none';
            badge.textContent = '0';
        } else {
            badge.style.display = 'inline-block';
            badge.textContent = totalU;
        }
    }
    
    if (!data.unknowns_preview || data.unknowns_preview.length === 0) {
        unknownRow.innerHTML = `<div class="empty-row-placeholder" style="font-size:11px; color:var(--text-muted); width:100%; text-align:center; padding:10px;">No unknown profiles saved.</div>`;
    } else {
        unknownRow.innerHTML = data.unknowns_preview.map(u => `
            <img src="${u.face_path}" class="unknown-preview-tile" onclick="switchTab('unknown-gallery')" title="Seen ${u.appearances} times">
        `).join('');
    }

    // Mini Chart (Active vs Idle)
    renderQuickOperationsChart(data.kpis.working_employees, data.kpis.idle_employees);
}

function renderQuickOperationsChart(working, idle) {
    const ctx = document.getElementById('chart-quick-operations').getContext('2d');
    if (charts.quick) {
        charts.quick.data.datasets[0].data = [working, idle];
        charts.quick.update();
        return;
    }
    charts.quick = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Working', 'Idle'],
            datasets: [{
                data: [working, idle],
                backgroundColor: ['#10b981', '#f59e0b'],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.05)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#8e9bb0', font: { size: 9 } } }
            }
        }
    });
}

// ==========================================
// UNKNOWN FACE GALLERY
// ==========================================
async function loadUnknownFaces() {
    try {
        const response = await fetch('/api/employees/unknown-faces');
        if (response.ok) {
            const data = await response.json();
            renderUnknownGallery(data);
        }
    } catch (e) {
        console.error(e);
    }
}

function renderUnknownGallery(unknowns) {
    // Toggle Clear All Profiles Button
    const clearBtn = document.getElementById('btn-clear-all-unknowns');
    if (clearBtn) {
        clearBtn.style.display = (!unknowns || unknowns.length === 0) ? 'none' : 'block';
    }

    // Update sidebar badge
    const badge = document.getElementById('sidebar-unknown-badge');
    if (badge) {
        if (!unknowns || unknowns.length === 0) {
            badge.style.display = 'none';
            badge.textContent = '0';
        } else {
            badge.style.display = 'inline-block';
            badge.textContent = unknowns.length;
        }
    }

    const grid = document.getElementById('unknown-gallery-grid');
    if (!unknowns || unknowns.length === 0) {
        grid.innerHTML = `
            <div class="empty-list-placeholder" style="grid-column: 1/-1; padding: 50px; text-align: center; width:100%;">
                <i class="fa-regular fa-face-smile" style="font-size:48px; color:var(--text-muted); margin-bottom:15px;"></i>
                <h3 style="color:var(--text-primary);">No unknown faces registered</h3>
                <p style="color:var(--text-muted); max-width:400px; margin:8px auto 0;">All clear. Unrecognized visitors will show up here automatically.</p>
            </div>
        `;
        return;
    }
    grid.innerHTML = unknowns.map(u => {
        let badgeStyle = 'background: var(--text-muted); color: #fff; box-shadow: 0 0 8px rgba(0,0,0,0.3);';
        if (u.event_type === 'restricted_zone_intrusion') {
            badgeStyle = 'background: var(--error); color: #fff; box-shadow: 0 0 8px var(--error);';
        } else if (u.event_type === 'phone_usage') {
            badgeStyle = 'background: var(--error); color: #fff; box-shadow: 0 0 8px var(--error);';
        } else if (u.event_type === 'manual_capture') {
            badgeStyle = 'background: var(--info); color: #fff; box-shadow: 0 0 8px var(--info);';
        } else if (u.event_type === 'long_presence') {
            badgeStyle = 'background: var(--warning); color: #000; box-shadow: 0 0 8px var(--warning);';
        }
        
        return `
            <div class="unknown-gallery-card" style="position: relative;">
                <span class="badge" style="position: absolute; top: 10px; right: 10px; font-size: 9px; border-radius: 4px; ${badgeStyle}">
                    ${u.reason || 'Unrecognized Visitor'}
                </span>
                <span class="badge" style="position: absolute; top: 10px; left: 10px; font-size: 9px; border-radius: 4px; background: rgba(0,0,0,0.6); color: #fff;">
                    Apps: ${u.appearances}
                </span>
                <img src="${u.face_path}" class="unknown-gallery-crop" alt="Face crop" style="margin-top: 10px;">
                <div class="unknown-gallery-meta" style="font-size: 11px; padding: 10px 14px 2px; line-height: 1.4;">
                    <div style="color: var(--text-muted);"><i class="fa-solid fa-clock"></i> ${u.timestamp}</div>
                    <div style="color: var(--text-muted); margin-top: 2px;"><i class="fa-solid fa-camera"></i> ${u.camera_name || 'Main Camera'}</div>
                </div>
                <div class="unknown-gallery-actions" style="padding: 6px 14px 14px; display: flex; gap: 6px;">
                    <button class="btn btn-sm btn-primary" onclick="registerUnknownFaceCrop(${u.id}, '${u.face_path}')" style="flex: 1;">
                        Register
                    </button>
                    <button class="btn btn-sm btn-muted" onclick="deleteUnknownFace(${u.id})" style="flex: 1;">
                        Delete
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function registerUnknownFaceCrop(id, facePath) {
    registeringFromUnknownCropId = id;
    registeringFromUnknownCropUrl = facePath;
    
    document.getElementById('employee-modal-title').textContent = 'Register Profile from Crop';
    document.getElementById('employee-id').value = '';
    document.getElementById('employee-name').value = '';
    document.getElementById('employee-position').value = '';
    
    document.getElementById('employee-uniform-color').value = 'None';
    document.getElementById('employee-uniform-type').value = '';
    document.getElementById('employee-apron-color').value = 'None';
    document.getElementById('employee-hat').checked = false;
    
    registrationBase64Images = [];
    
    const previewGrid = document.getElementById('registration-face-previews');
    previewGrid.innerHTML = `
        <div class="crop-preview-card">
            <img src="${facePath}">
        </div>
    `;
    
    document.getElementById('registration-video').style.display = 'none';
    document.getElementById('video-overlay-msg').style.display = 'flex';
    document.getElementById('btn-start-reg-cam').style.display = 'inline-flex';
    document.getElementById('btn-capture-reg').disabled = true;
    
    document.getElementById('employee-modal').classList.add('active');
}

async function deleteUnknownFace(id) {
    try {
        const response = await fetch(`/api/employees/unknown-faces/${id}`, { method: 'DELETE' });
        if (response.ok) {
            Toast.show("Unknown face cropped log removed.", "success");
            loadUnknownFaces();
        }
    } catch (e) {
        console.error(e);
    }
}

// ==========================================
// STAFF CRUD
// ==========================================
async function loadStaffList() {
    try {
        const response = await fetch('/api/employees');
        if (response.ok) {
            const data = await response.json();
            renderStaffTable(data);
        }
    } catch (e) {
        console.error(e);
    }
}

function renderStaffTable(staff) {
    const tbody = document.getElementById('staff-table-body');
    if (!staff || staff.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 40px;">
                    <i class="fa-solid fa-users" style="font-size:32px; color:var(--text-muted); margin-bottom:12px; display:block;"></i>
                    <strong>No employees registered</strong>
                    <p style="font-size:11px; color:var(--text-muted); margin-top:5px;">Click "Add Employee" to register face templates.</p>
                </td>
            </tr>
        `;
        return;
    }
    tbody.innerHTML = staff.map(emp => `
        <tr>
            <td><strong>${emp.name}</strong></td>
            <td>${emp.position}</td>
            <td>${emp.department}</td>
            <td><span style="display:inline-block; width:10px; height:10px; background:${emp.uniform_color.toLowerCase()}; border-radius:50%; margin-right:4px;"></span> ${emp.uniform_color}</td>
            <td>
                <span class="reg-dot ${emp.face_registered ? 'registered' : 'unregistered'}">
                    ${emp.face_registered ? 'Registered' : 'No face template'}
                </span>
            </td>
            <td>${emp.created_at}</td>
            <td style="font-weight: 600; color: ${emp.avg_productivity >= 80 ? 'var(--success)' : 'var(--error)'}">${emp.avg_productivity}%</td>
            <td>
                <button class="btn btn-sm btn-info" onclick="viewEmployeeProfile(${emp.id})">
                    <i class="fa-solid fa-address-card"></i> Profile
                </button>
                <button class="btn btn-sm btn-muted" onclick="openEditEmployeeModal(${JSON.stringify(emp).replace(/"/g, '&quot;')})">
                    <i class="fa-solid fa-pen"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger" onclick="openDeleteEmployeeModal(${emp.id}, '${emp.name.replace(/'/g, "\\'")}')">
                    <i class="fa-solid fa-trash"></i> Delete
                </button>
            </td>
        </tr>
    `).join('');
}

function searchStaff() {
    const q = document.getElementById('staff-search-input').value.trim();
    fetch(`/api/employees/search?q=${encodeURIComponent(q)}`)
        .then(res => res.json())
        .then(data => renderStaffTable(data))
        .catch(e => console.error(e));
}

// Multi-shot captures logic with camera lock release and step guidance
let wasSurveillanceRunningBeforeReg = false;
const registrationSteps = [
    "Step 1/5: Please look directly at the camera.",
    "Step 2/5: Turn your head slightly to the LEFT.",
    "Step 3/5: Turn your head slightly to the RIGHT.",
    "Step 4/5: Tilt your head slightly UPWARDS.",
    "Step 5/5: Tilt your head slightly DOWNWARDS."
];

async function getMediaStream(constraints) {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        return await navigator.mediaDevices.getUserMedia(constraints);
    }
    const legacyGetUserMedia = navigator.getUserMedia || 
                              navigator.webkitGetUserMedia || 
                              navigator.mozGetUserMedia || 
                              navigator.msGetUserMedia;
    if (!legacyGetUserMedia) {
        throw new Error("Camera acquisition is blocked by your browser on insecure (non-HTTPS/non-localhost) local connections. Please access the dashboard via 'localhost' or configure HTTPS.");
    }
    return new Promise((resolve, reject) => {
        legacyGetUserMedia.call(navigator, constraints, resolve, reject);
    });
}

async function startRegistrationCamera() {
    const liveIndicator = document.getElementById('live-indicator');
    if (liveIndicator && liveIndicator.classList.contains('active')) {
        wasSurveillanceRunningBeforeReg = true;
        Toast.show("Releasing main surveillance stream to unlock hardware...", "info");
        await stopCameraStream();
        await new Promise(resolve => setTimeout(resolve, 800));
    }
    
    try {
        const stream = await getMediaStream({ video: { width: 320, height: 240 } });
        registrationStream = stream;
        const video = document.getElementById('registration-video');
        video.srcObject = stream;
        video.style.display = 'block';
        document.getElementById('video-overlay-msg').style.display = 'none';
        document.getElementById('btn-start-reg-cam').style.display = 'none';
        document.getElementById('btn-capture-reg').disabled = false;
        
        // Reset to step 1
        document.getElementById('registration-prompt-text').textContent = registrationSteps[0];
        Toast.show("Registration preview camera active.", "success");
    } catch (e) {
        console.error(e);
        Toast.show("Error opening camera: " + e.message, "error");
    }
}

function captureRegistrationFace() {
    const currentCount = registrationBase64Images.length;
    if (currentCount >= 5) {
        Toast.show("All 5 face templates registered.", "warning");
        return;
    }
    const video = document.getElementById('registration-video');
    const canvas = document.getElementById('registration-canvas');
    if (!video.srcObject) return;
    
    canvas.width = 320;
    canvas.height = 240;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    const base64Img = canvas.toDataURL('image/jpeg');
    registrationBase64Images.push(base64Img);
    
    renderRegistrationFacePreviews();
    Toast.show(`Angle #${currentCount + 1} captured!`, "success");
    
    const nextCount = registrationBase64Images.length;
    if (nextCount < 5) {
        document.getElementById('registration-prompt-text').textContent = registrationSteps[nextCount];
    } else {
        document.getElementById('registration-prompt-text').textContent = "FaceID collection complete! Click Clear or Save Profile.";
        document.getElementById('btn-capture-reg').disabled = true;
        stopRegistrationCamera();
    }
}

function renderRegistrationFacePreviews() {
    const grid = document.getElementById('registration-face-previews');
    grid.innerHTML = registrationBase64Images.map((img, idx) => `
        <div class="crop-preview-card">
            <img src="${img}">
            <button type="button" class="crop-preview-remove" onclick="removeRegistrationSnap(${idx})">&times;</button>
        </div>
    `).join('');
}

function removeRegistrationSnap(idx) {
    registrationBase64Images.splice(idx, 1);
    renderRegistrationFacePreviews();
    const currentCount = registrationBase64Images.length;
    if (currentCount < 5) {
        document.getElementById('registration-prompt-text').textContent = registrationSteps[currentCount];
        document.getElementById('btn-capture-reg').disabled = false;
        if (!registrationStream) {
            startRegistrationCamera();
        }
    }
}

function clearRegistrationSnaps() {
    registrationBase64Images = [];
    renderRegistrationFacePreviews();
    document.getElementById('registration-prompt-text').textContent = registrationSteps[0];
    document.getElementById('btn-capture-reg').disabled = false;
    if (!registrationStream) {
        startRegistrationCamera();
    }
}

function openAddEmployeeModal() {
    registeringFromUnknownCropId = null;
    registeringFromUnknownCropUrl = null;
    
    document.getElementById('employee-modal-title').textContent = 'Register Employee Profile';
    document.getElementById('employee-id').value = '';
    document.getElementById('employee-name').value = '';
    document.getElementById('employee-position').value = '';
    document.getElementById('employee-department').value = 'Operations';
    
    document.getElementById('employee-uniform-color').value = 'None';
    document.getElementById('employee-uniform-type').value = '';
    document.getElementById('employee-apron-color').value = 'None';
    document.getElementById('employee-hat').checked = false;
    document.getElementById('employee-shift-start').value = '09:00';
    document.getElementById('employee-shift-end').value = '17:00';
    
    registrationBase64Images = [];
    renderRegistrationFacePreviews();
    
    document.getElementById('registration-video').style.display = 'none';
    document.getElementById('video-overlay-msg').style.display = 'flex';
    document.getElementById('btn-start-reg-cam').style.display = 'inline-flex';
    document.getElementById('btn-capture-reg').disabled = true;
    
    document.getElementById('employee-modal').classList.add('active');
}

function openEditEmployeeModal(emp) {
    registeringFromUnknownCropId = null;
    registeringFromUnknownCropUrl = null;
    
    document.getElementById('employee-modal-title').textContent = 'Update Employee Profile';
    document.getElementById('employee-id').value = emp.id;
    document.getElementById('employee-name').value = emp.name;
    document.getElementById('employee-position').value = emp.position;
    document.getElementById('employee-department').value = emp.department || 'Operations';
    
    document.getElementById('employee-uniform-color').value = emp.uniform_color || 'None';
    document.getElementById('employee-uniform-type').value = emp.uniform_type || '';
    document.getElementById('employee-apron-color').value = emp.apron_color || 'None';
    document.getElementById('employee-hat').checked = emp.hat || false;
    document.getElementById('employee-shift-start').value = emp.shift_start || '09:00';
    document.getElementById('employee-shift-end').value = emp.shift_end || '17:00';
    
    registrationBase64Images = [];
    renderRegistrationFacePreviews();
    
    document.getElementById('registration-video').style.display = 'none';
    document.getElementById('video-overlay-msg').style.display = 'flex';
    document.getElementById('btn-start-reg-cam').style.display = 'inline-flex';
    document.getElementById('btn-capture-reg').disabled = true;
    
    document.getElementById('employee-modal').classList.add('active');
}

function closeEmployeeModal() {
    stopRegistrationCamera();
    document.getElementById('employee-modal').classList.remove('active');
    if (wasSurveillanceRunningBeforeReg) {
        wasSurveillanceRunningBeforeReg = false;
        setTimeout(() => {
            startCameraStream();
        }, 500);
    }
}

function stopRegistrationCamera() {
    if (registrationStream) {
        registrationStream.getTracks().forEach(track => track.stop());
        registrationStream = null;
    }
}

async function handleEmployeeSubmit(event) {
    event.preventDefault();
    const id = document.getElementById('employee-id').value;
    const name = document.getElementById('employee-name').value.trim();
    const position = document.getElementById('employee-position').value.trim();
    const department = document.getElementById('employee-department').value;
    
    const uniform_color = document.getElementById('employee-uniform-color').value;
    const uniform_type = document.getElementById('employee-uniform-type').value.trim();
    const apron_color = document.getElementById('employee-apron-color').value;
    const hat = document.getElementById('employee-hat').checked;
    const shift_start = document.getElementById('employee-shift-start').value;
    const shift_end = document.getElementById('employee-shift-end').value;

    if (!name || !position) return;

    if (shift_start === shift_end) {
        Toast.show("Invalid shift timings: Shift start and end cannot be identical.", "warning");
        return;
    }

    let payload = {
        name,
        position,
        department,
        uniform_color,
        uniform_type,
        apron_color,
        hat,
        shift_start,
        shift_end
    };

    if (registeringFromUnknownCropId) {
        try {
            const response = await fetch(`/api/employees/unknown-faces/${registeringFromUnknownCropId}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (response.ok) {
                Toast.show("Employee registered from crop template.", "success");
                closeEmployeeModal();
                switchTab('staff');
            }
        } catch (e) {
            console.error(e);
        }
        return;
    }

    payload.image = registrationBase64Images.length > 0 ? registrationBase64Images[0] : '';
    payload.extra_images = registrationBase64Images.slice(1);

    const url = id ? `/api/employees/${id}` : '/api/employees/add';
    const method = id ? 'PUT' : 'POST';

    try {
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            Toast.show(id ? "Profile modified." : "Employee profile registered.", "success");
            closeEmployeeModal();
            loadStaffList();
        }
    } catch (e) {
        console.error(e);
    }
}

function openDeleteEmployeeModal(id, name) {
    document.getElementById('delete-employee-id-val').value = id;
    document.getElementById('delete-employee-name-display').textContent = name;
    document.getElementById('delete-employee-modal').classList.add('active');
}
function closeDeleteEmployeeModal() {
    document.getElementById('delete-employee-modal').classList.remove('active');
}
async function confirmDeleteEmployee() {
    const id = document.getElementById('delete-employee-id-val').value;
    try {
        const response = await fetch(`/api/employees/${id}`, { method: 'DELETE' });
        if (response.ok) {
            Toast.show("Employee permanently purged.", "success");
            closeDeleteEmployeeModal();
            loadStaffList();
        }
    } catch (e) {
        console.error(e);
    }
}

// Profiles
async function viewEmployeeProfile(id) {
    try {
        const response = await fetch(`/api/employees/${id}/profile`);
        if (response.ok) {
            const data = await response.json();
            
            document.getElementById('profile-name-header').textContent = `${data.name}'s Profile File`;
            document.getElementById('profile-name').textContent = data.name;
            document.getElementById('profile-position').textContent = data.position;
            document.getElementById('profile-dept').textContent = data.department;
            
            document.getElementById('profile-stat-days').textContent = data.stats.total_days;
            document.getElementById('profile-stat-productivity').textContent = `${data.stats.average_productivity}%`;
            document.getElementById('profile-stat-late').textContent = `${data.stats.late_percentage}%`;
            document.getElementById('profile-stat-idle').textContent = `${data.stats.idle_percentage}%`;
            
            document.getElementById('profile-stat-hrs-daily').textContent = data.stats.daily_hours;
            document.getElementById('profile-stat-hrs-weekly').textContent = data.stats.weekly_hours;
            document.getElementById('profile-stat-hrs-monthly').textContent = data.stats.monthly_hours;

            const chips = document.getElementById('profile-uniform-chips-view');
            chips.innerHTML = `
                <span class="uniform-spec-chip">Shirt: ${data.uniform_color}</span>
                <span class="uniform-spec-chip">Type: ${data.uniform_type}</span>
                <span class="uniform-spec-chip">Apron: ${data.apron_color}</span>
                <span class="uniform-spec-chip">Hat: ${data.hat ? 'Yes' : 'No'}</span>
            `;

            const thumbnails = document.getElementById('profile-face-samples-row');
            if (data.face_samples.length === 0) {
                thumbnails.innerHTML = `<span style="font-size:10px; color:var(--text-muted);">None</span>`;
            } else {
                thumbnails.innerHTML = data.face_samples.map(path => `
                    <img src="${path}" class="profile-face-thumbnail" alt="Face sample">
                `).join('');
            }

            const tbody = document.getElementById('profile-table-body');
            tbody.innerHTML = data.attendance.map(row => `
                <tr>
                    <td>${row.date ? row.date.substring(5) : '-'}</td>
                    <td>${row.check_in ? row.check_in.substring(0, 5) : '-'}</td>
                    <td>${row.check_out ? row.check_out.substring(0, 5) : '-'}</td>
                    <td style="font-weight: 600; color: ${row.score >= 80 ? 'var(--success)' : 'var(--error)'}">${row.score}%</td>
                </tr>
            `).join('');

            const tTimeline = document.getElementById('profile-timeline-body');
            tTimeline.innerHTML = data.timeline.map(t => `
                <div class="timeline-item">
                    <span class="timeline-dot ${t.severity}"></span>
                    <div>${t.message}</div>
                    <div class="timeline-time">${t.date.substring(5)} ${t.time}</div>
                </div>
            `).join('');

            renderProfileWeeklyChart(data.weekly_attendance);
            document.getElementById('profile-modal').classList.add('active');
        }
    } catch (e) {
        console.error(e);
    }
}

function renderProfileWeeklyChart(weeklyData) {
    const ctx = document.getElementById('profile-attendance-chart').getContext('2d');
    if (charts.profileWeekly) charts.profileWeekly.destroy();
    
    charts.profileWeekly = new Chart(ctx, {
        type: 'line',
        data: {
            labels: weeklyData.map(w => w.day),
            datasets: [{
                data: weeklyData.map(w => w.hours),
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.02)' }, ticks: { color: '#8e9bb0', font: { size: 9 } } },
                x: { grid: { display: false }, ticks: { color: '#8e9bb0', font: { size: 9 } } }
            }
        }
    });
}
function closeProfileModal() {
    document.getElementById('profile-modal').classList.remove('active');
}

// ==========================================
// ANALYTICS & CHARTS
// ==========================================
function setAnalyticsRange(range) {
    currentAnalyticsRange = range;
    document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`preset-${range}`).classList.add('active');
    
    const customDates = document.getElementById('analytics-custom-dates');
    if (range === 'custom') {
        customDates.style.display = 'flex';
    } else {
        customDates.style.display = 'none';
        loadAnalytics();
    }
}

async function loadAnalytics() {
    const range = currentAnalyticsRange;
    const startDate = document.getElementById('analytics-start-date').value;
    const endDate = document.getElementById('analytics-end-date').value;
    
    let url = `/api/analytics/dashboard?range=${range}`;
    if (range === 'custom') {
        url += `&start_date=${startDate}&end_date=${endDate}`;
    }
    
    try {
        const response = await fetch(url);
        if (response.ok) {
            const data = await response.json();
            
            // Toggle Professional Empty State if no analytics are returned
            if (!data.hours_worked || data.hours_worked.length === 0) {
                document.getElementById('analytics-charts-grid').style.display = 'none';
                document.getElementById('analytics-empty-state').style.display = 'flex';
                
                document.getElementById('stat-active-employees').textContent = '0';
                document.getElementById('stat-attendance-rate').textContent = '0%';
                document.getElementById('stat-avg-productivity').textContent = '0%';
                document.getElementById('stat-security-events').textContent = '0';
                
                if (document.getElementById('metrics-zone-breaches')) {
                    document.getElementById('metrics-zone-breaches').textContent = '0';
                }
                if (document.getElementById('metrics-zone-avg-duration')) {
                    document.getElementById('metrics-zone-avg-duration').textContent = '0s';
                }
                if (document.getElementById('table-zone-breaches-body')) {
                    document.getElementById('table-zone-breaches-body').innerHTML = `
                        <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">No breaches recorded.</td></tr>
                    `;
                }
                
                const topList = document.getElementById('list-top-performers');
                const bottomList = document.getElementById('list-needs-improvement');
                topList.innerHTML = `<li class="empty-list-placeholder" style="padding: 10px; color:var(--text-muted); font-size:11px;">No performers logged.</li>`;
                bottomList.innerHTML = `<li class="empty-list-placeholder" style="padding: 10px; color:var(--text-muted); font-size:11px;">No records logged.</li>`;
            } else {
                document.getElementById('analytics-charts-grid').style.display = 'grid';
                document.getElementById('analytics-empty-state').style.display = 'none';
                
                document.getElementById('stat-active-employees').textContent = data.summary.active_employees;
                document.getElementById('stat-attendance-rate').textContent = `${data.summary.attendance_rate}%`;
                document.getElementById('stat-avg-productivity').textContent = `${data.summary.avg_productivity}%`;
                document.getElementById('stat-security-events').textContent = data.security_events;
                
                // Populate breaches stats
                if (document.getElementById('metrics-zone-breaches')) {
                    document.getElementById('metrics-zone-breaches').textContent = data.restricted_zones.total_breaches;
                }
                if (document.getElementById('metrics-zone-avg-duration')) {
                    document.getElementById('metrics-zone-avg-duration').textContent = `${data.restricted_zones.average_duration}s`;
                }
                
                // Populate breaches table
                const breachesTable = document.getElementById('table-zone-breaches-body');
                if (breachesTable) {
                    const breaches = data.restricted_zones.recent_breaches;
                    if (!breaches || breaches.length === 0) {
                        breachesTable.innerHTML = `
                            <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">No breaches recorded.</td></tr>
                        `;
                    } else {
                        breachesTable.innerHTML = breaches.map(b => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text-secondary);">
                                <td style="padding: 10px;">
                                    ${b.face_crop_path ? `<img src="${b.face_crop_path}" style="width: 36px; height: 36px; border-radius: 4px; object-fit: cover; border: 1px solid var(--border-color);" alt="Face">` : `<i class="fa-solid fa-user-secret" style="font-size: 20px; color: var(--text-muted);"></i>`}
                                </td>
                                <td style="padding: 10px; font-weight: 600;">${b.name}</td>
                                <td style="padding: 10px;"><span style="color: var(--error); font-weight: 500;">${b.zone_name}</span></td>
                                <td style="padding: 10px; font-variant-numeric: tabular-nums;">${b.timestamp}</td>
                                <td style="padding: 10px; font-variant-numeric: tabular-nums; font-weight: 600;">${b.duration}s</td>
                                <td style="padding: 10px;">
                                    ${b.snapshot_path ? `<a href="${b.snapshot_path}" target="_blank" style="color: var(--accent); text-decoration: none;"><i class="fa-solid fa-image"></i> View</a>` : '-'}
                                </td>
                            </tr>
                        `).join('');
                    }
                }
                
                renderAnalyticsCharts(data);
                renderRankings(data.rankings);
            }
        }
    } catch (e) {
        console.error(e);
    }
}

function renderAnalyticsCharts(data) {
    const chartKeys = ['hours', 'prod', 'checkin', 'activity', 'dept', 'customer', 'trends', 'accuracy', 'zoneBreaches'];
    chartKeys.forEach(key => { if (charts[key]) charts[key].destroy(); });

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#8e9bb0' } },
            x: { grid: { display: false }, ticks: { color: '#8e9bb0' } }
        }
    };

    charts.hours = new Chart(document.getElementById('chart-hours-worked').getContext('2d'), {
        type: 'bar',
        data: {
            labels: data.hours_worked.map(d => d.date.substring(5)),
            datasets: [{
                data: data.hours_worked.map(d => d.hours),
                backgroundColor: 'rgba(99, 102, 241, 0.65)',
                borderColor: '#6366f1',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: options
    });

    charts.prod = new Chart(document.getElementById('chart-productivity').getContext('2d'), {
        type: 'line',
        data: {
            labels: data.productivity_trend.map(d => d.date.substring(5)),
            datasets: [{
                data: data.productivity_trend.map(d => d.score),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.3
            }]
        },
        options: { ...options, scales: { ...options.scales, y: { ...options.scales.y, min: 0, max: 100 } } }
    });

    charts.checkin = new Chart(document.getElementById('chart-checkin').getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: ['Late', 'On-Time'],
            datasets: [{
                data: [data.late_vs_ontime.late, data.late_vs_ontime.on_time],
                backgroundColor: ['#ef4444', '#10b981'],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.05)'
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { color: '#8e9bb0' } } } }
    });

    charts.activity = new Chart(document.getElementById('chart-activity').getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: ['Active hours', 'Idle hours'],
            datasets: [{
                data: [data.active_vs_idle.active, data.active_vs_idle.idle],
                backgroundColor: ['#6366f1', '#f59e0b'],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.05)'
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { color: '#8e9bb0' } } } }
    });

    charts.dept = new Chart(document.getElementById('chart-department-productivity').getContext('2d'), {
        type: 'bar',
        data: {
            labels: data.department_productivity.map(d => d.department),
            datasets: [{
                data: data.department_productivity.map(d => d.score),
                backgroundColor: 'rgba(59, 130, 246, 0.65)',
                borderColor: '#3b82f6',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#8e9bb0' } },
                y: { grid: { display: false }, ticks: { color: '#8e9bb0' } }
            }
        }
    });

    charts.customer = new Chart(document.getElementById('chart-customer-count').getContext('2d'), {
        type: 'line',
        data: {
            labels: data.customer_count.map(d => d.date.substring(5)),
            datasets: [{
                data: data.customer_count.map(d => d.count),
                borderColor: '#818cf8',
                backgroundColor: 'rgba(129, 140, 248, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.2
            }]
        },
        options: options
    });

    charts.trends = new Chart(document.getElementById('chart-alert-trends').getContext('2d'), {
        type: 'bar',
        data: {
            labels: data.alert_trends.map(d => d.date.substring(5)),
            datasets: [{
                data: data.alert_trends.map(d => d.count),
                backgroundColor: 'rgba(239, 68, 68, 0.65)',
                borderColor: '#ef4444',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: options
    });

    charts.accuracy = new Chart(document.getElementById('chart-recognition-accuracy').getContext('2d'), {
        type: 'line',
        data: {
            labels: data.recognition_accuracy.map(d => d.date.substring(5)),
            datasets: [{
                data: data.recognition_accuracy.map(d => d.accuracy),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.3
            }]
        },
        options: { ...options, scales: { ...options.scales, y: { ...options.scales.y, min: 0, max: 100 } } }
    });

    const zBreachesData = data.restricted_zones.breaches_by_zone || [];
    charts.zoneBreaches = new Chart(document.getElementById('chart-zone-breaches').getContext('2d'), {
        type: 'pie',
        data: {
            labels: zBreachesData.map(z => z.zone),
            datasets: [{
                data: zBreachesData.map(z => z.count),
                backgroundColor: [
                    '#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#6366f1', '#ec4899', '#8b5cf6'
                ],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.05)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'right',
                    labels: { color: '#8e9bb0', font: { family: 'Outfit', size: 11 } }
                }
            }
        }
    });
}

function renderRankings(rankings) {
    const topList = document.getElementById('list-top-performers');
    const bottomList = document.getElementById('list-needs-improvement');
    
    if (rankings.top.length === 0) {
        topList.innerHTML = `<li class="empty-list-placeholder" style="padding: 10px; font-size:11px;">No records.</li>`;
    } else {
        topList.innerHTML = rankings.top.map(emp => `
            <li class="ranking-item">
                <div>
                    <span class="ranking-name">${emp.name}</span>
                    <span class="ranking-role"> (${emp.position})</span>
                </div>
                <span class="ranking-score">${emp.avg_score}%</span>
            </li>
        `).join('');
    }
    
    if (rankings.needs_improvement.length === 0) {
        bottomList.innerHTML = `<li class="empty-list-placeholder" style="padding: 10px; color: var(--success); font-size:11px;"><i class="fa-solid fa-circle-check"></i> All scores above 80%!</li>`;
    } else {
        bottomList.innerHTML = rankings.needs_improvement.map(emp => `
            <li class="ranking-item">
                <div>
                    <span class="ranking-name">${emp.name}</span>
                    <span class="ranking-role"> (${emp.position})</span>
                </div>
                <span class="ranking-score">${emp.avg_score}%</span>
            </li>
        `).join('');
    }
}

// ==========================================
// REPORTS
// ==========================================
async function generateReportSummary() {
    const startDate = document.getElementById('report-start-date').value;
    const endDate = document.getElementById('report-end-date').value;
    const scope = document.getElementById('report-scope').value;
    let scopeId = '';
    let scopeName = '';
    
    if (scope === 'employee') {
        const empSelect = document.getElementById('report-target-employee');
        scopeId = empSelect.value;
        scopeName = empSelect.options[empSelect.selectedIndex]?.text || '';
    } else if (scope === 'department') {
        const deptSelect = document.getElementById('report-target-department');
        scopeId = deptSelect.value;
        scopeName = `Department: ${deptSelect.value}`;
    } else {
        scopeName = 'All Employees';
    }
    
    Toast.show("Analyzing report statistics...", "info");
    try {
        const url = `/api/reports/summary?start_date=${startDate}&end_date=${endDate}&scope=${scope}&scope_id=${scopeId}`;
        const response = await fetch(url);
        if (response.ok) {
            const data = await response.json();
            
            document.getElementById('report-date-range').textContent = `${data.start_date} to ${data.end_date}`;
            document.getElementById('report-scope-display').textContent = scopeName;
            document.getElementById('report-generated-date').textContent = new Date().toLocaleString();
            
            document.getElementById('rep-val-attendance').textContent = `${data.attendance_rate}%`;
            document.getElementById('rep-val-productivity').textContent = `${data.avg_productivity}%`;
            document.getElementById('rep-val-late').textContent = data.security_events;
            
            document.getElementById('report-text-summary').textContent = data.summary;
            document.getElementById('report-text-analysis').textContent = data.analysis;
            
            document.getElementById('report-bullets-recommendations').innerHTML = data.recommendations.map(rec => `
                <li>${rec}</li>
            `).join('');
            
            document.getElementById('report-display').style.display = 'block';
            Toast.show("Analysis report generated.", "success");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Failed to analyze reports.", "error");
    }
}

function downloadReportPDF() {
    const startDate = document.getElementById('report-start-date').value;
    const endDate = document.getElementById('report-end-date').value;
    const scope = document.getElementById('report-scope').value;
    let scopeId = '';
    if (scope === 'employee') {
        scopeId = document.getElementById('report-target-employee').value;
    } else if (scope === 'department') {
        scopeId = document.getElementById('report-target-department').value;
    }
    Toast.show("Exporting ReportLab PDF...", "info");
    window.location.href = `/api/reports/pdf?start_date=${startDate}&end_date=${endDate}&scope=${scope}&scope_id=${scopeId}`;
}

function handleReportScopeChange() {
    const scope = document.getElementById('report-scope').value;
    const empGroup = document.getElementById('report-employee-group');
    const deptGroup = document.getElementById('report-department-group');
    
    if (scope === 'employee') {
        empGroup.style.display = 'block';
        deptGroup.style.display = 'none';
        populateReportEmployees();
    } else if (scope === 'department') {
        empGroup.style.display = 'none';
        deptGroup.style.display = 'block';
    } else {
        empGroup.style.display = 'none';
        deptGroup.style.display = 'none';
    }
}

async function populateReportEmployees() {
    const select = document.getElementById('report-target-employee');
    if (!select) return;
    try {
        const response = await fetch('/api/employees');
        if (response.ok) {
            const data = await response.json();
            select.innerHTML = data.map(e => `
                <option value="${e.id}">${e.name} (${e.position})</option>
            `).join('');
        }
    } catch (e) {
        console.error(e);
    }
}

// ==========================================
// SETTINGS
// ==========================================
async function loadSettings() {
    try {
        const response = await fetch('/api/settings/all');
        if (response.ok) {
            const data = await response.json();
            document.getElementById('settings-company-name').value = data.company_name;
            document.getElementById('rules-start-time').value = data.work_hours_start;
            document.getElementById('rules-end-time').value = data.work_hours_end;
            document.getElementById('rules-late-threshold').value = data.late_threshold;
            document.getElementById('rules-break-duration').value = data.break_duration;
            document.getElementById('rules-idle-timeout').value = data.idle_timeout;
            document.getElementById('rules-checkout-timeout').value = data.checkout_timeout;
            document.getElementById('rules-recognition-threshold').value = data.recognition_threshold;
            document.getElementById('rules-camera-settings').value = data.camera_settings;
            document.getElementById('rules-camera-fps').value = data.camera_fps;
            document.getElementById('rules-camera-resolution').value = data.camera_resolution;
            document.getElementById('rules-alert-sensitivity').value = data.alert_sensitivity;
            document.getElementById('rules-enable-camera-zones').checked = data.enable_camera_zones;
            document.getElementById('rules-unknown-capture-policy').value = data.unknown_face_capture_policy || 'events_only';
        }
    } catch (e) {
        console.error(e);
    }
}

async function saveSettingsAll(event) {
    event.preventDefault();
    
    const company_name = document.getElementById('settings-company-name').value.trim();
    const work_hours_start = document.getElementById('rules-start-time').value;
    const work_hours_end = document.getElementById('rules-end-time').value;
    const late_threshold = parseInt(document.getElementById('rules-late-threshold').value) || 0;
    const break_duration = parseInt(document.getElementById('rules-break-duration').value) || 0;
    const idle_timeout = parseInt(document.getElementById('rules-idle-timeout').value) || 15;
    const checkout_timeout = parseInt(document.getElementById('rules-checkout-timeout').value) || 15;
    const recognition_threshold = parseFloat(document.getElementById('rules-recognition-threshold').value) || 85.0;
    const camera_settings = document.getElementById('rules-camera-settings').value;
    const camera_fps = parseInt(document.getElementById('rules-camera-fps').value) || 20;
    const camera_resolution = document.getElementById('rules-camera-resolution').value;
    const alert_sensitivity = document.getElementById('rules-alert-sensitivity').value;
    const enable_camera_zones = document.getElementById('rules-enable-camera-zones').checked;
    const unknown_face_capture_policy = document.getElementById('rules-unknown-capture-policy').value;

    if (!company_name) return;

    const payload = {
        company_name, work_hours_start, work_hours_end, late_threshold, break_duration,
        idle_timeout, checkout_timeout, recognition_threshold, camera_settings, camera_fps,
        camera_resolution, alert_sensitivity, enable_camera_zones, unknown_face_capture_policy
    };

    try {
        const response = await fetch('/api/settings/all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            window.USER.companyName = company_name;
            Toast.show("Operational parameters saved.", "success");
        }
    } catch (e) {
        console.error(e);
    }
}

function setTheme(themeName) {
    const body = document.body;
    body.className = '';
    if (themeName === 'monochrome') {
        body.classList.add('theme-monochrome');
    }
    localStorage.setItem('workpulse-theme', themeName);
    
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.remove('active');
        if (themeName === 'neon' && btn.textContent.includes('Neon')) btn.classList.add('active');
        else if (themeName === 'monochrome' && btn.textContent.includes('Monochrome')) btn.classList.add('active');
    });
}

// Account Purge Confirmation
function openDeleteAccountModal() {
    document.getElementById('delete-password-verify').value = '';
    document.getElementById('double-confirm-checkbox').checked = false;
    document.getElementById('delete-account-modal').classList.add('active');
}
function closeDeleteAccountModal() {
    document.getElementById('delete-account-modal').classList.remove('active');
}
async function handleDeleteAccountConfirm(event) {
    event.preventDefault();
    const password = document.getElementById('delete-password-verify').value;
    const doubleConfirm = document.getElementById('double-confirm-checkbox').checked;
    
    if (!password || !doubleConfirm) return;
    try {
        const response = await fetch('/api/auth/delete-account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        if (response.ok) {
            Toast.show("Account purged. Redirecting...", "success");
            closeDeleteAccountModal();
            setTimeout(() => { window.location.href = '/auth'; }, 1500);
        } else {
            Toast.show("Purge authorization failed. Incorrect password.", "error");
        }
    } catch (e) {
        console.error(e);
    }
}

// Admin logout
async function logoutAdmin() {
    try {
        const response = await fetch('/api/auth/logout', { method: 'POST' });
        if (response.ok) {
            Toast.show("Logged out successfully.", "success");
            setTimeout(() => { window.location.reload(); }, 1000);
        }
    } catch (e) {
        console.error(e);
    }
}

// Stop camera streams and polling when page is hidden or unloaded
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopLiveDashboardPolling();
        stopCameraStream();
    } else {
        if (currentTab === 'live-camera') {
            startLiveDashboardPolling();
        }
    }
});

window.addEventListener('beforeunload', () => {
    if (window.USER.isAuthenticated) {
        // Use keepalive fetch to release camera resource synchronously
        fetch('/api/camera/stop', { method: 'POST', keepalive: true }).catch(e => console.error(e));
    }
});

function toggleFullscreen() {
    const video = document.getElementById('camera-stream');
    if (!document.fullscreenElement) {
        video.requestFullscreen().catch(err => {
            Toast.show(`Fullscreen error: ${err.message}`, "error");
        });
    } else {
        document.exitFullscreen();
    }
}

function initResizers() {
    // 1. Middle Resizer (Camera vs Alerts)
    const midResizer = document.getElementById('mid-resizer');
    const cameraCard = document.querySelector('.camera-card');
    if (midResizer && cameraCard) {
        setupDragResize(midResizer, cameraCard);
    }

    // 2. Bottom Resizer 1 (Personnel vs Timeline)
    const botResizer1 = document.getElementById('bottom-resizer-1');
    const botCard1 = document.getElementById('bottom-card-1');
    if (botResizer1 && botCard1) {
        setupDragResize(botResizer1, botCard1);
    }

    // 3. Bottom Resizer 2 (Timeline vs Unknowns)
    const botResizer2 = document.getElementById('bottom-resizer-2');
    const botCard2 = document.getElementById('bottom-card-2');
    if (botResizer2 && botCard2) {
        setupDragResize(botResizer2, botCard2);
    }

    // 4. Vertical Tier Resizer (Middle vs Bottom Tier)
    const vertResizer = document.getElementById('vertical-tier-resizer');
    const midGrid = document.querySelector('.surveillance-middle-grid');
    if (vertResizer && midGrid) {
        setupDragResizeHeight(vertResizer, midGrid);
    }
}

function setupDragResize(resizer, targetElement) {
    let startX, startWidth;
    
    resizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        resizer.classList.add('dragging');
        startX = e.clientX;
        startWidth = targetElement.getBoundingClientRect().width;
        
        const onMouseMove = (moveEvent) => {
            const deltaX = moveEvent.clientX - startX;
            const newWidth = Math.max(180, startWidth + deltaX);
            targetElement.style.width = `${newWidth}px`;
            targetElement.style.flexGrow = '0'; // prevent auto stretch/collapse
        };
        
        const onMouseUp = () => {
            resizer.classList.remove('dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

function setupDragResizeHeight(resizer, targetElement) {
    let startY, startHeight;
    
    resizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        resizer.classList.add('dragging');
        startY = e.clientY;
        startHeight = targetElement.getBoundingClientRect().height;
        
        const onMouseMove = (moveEvent) => {
            const deltaY = moveEvent.clientY - startY;
            const newHeight = Math.max(200, startHeight + deltaY);
            targetElement.style.height = `${newHeight}px`;
            targetElement.style.minHeight = '0'; // override CSS min-height
        };
        
        const onMouseUp = () => {
            resizer.classList.remove('dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

async function handleRegistrationFilesUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    if (registrationBase64Images.length + files.length > 5) {
        Toast.show("Maximum of 5 snaps total can be registered.", "warning");
    }
    
    const countToLoad = Math.min(files.length, 5 - registrationBase64Images.length);
    for (let i = 0; i < countToLoad; i++) {
        const file = files[i];
        const base64 = await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.readAsDataURL(file);
        });
        registrationBase64Images.push(base64);
    }
    
    renderRegistrationFacePreviews();
    Toast.show(`Uploaded ${countToLoad} photo templates.`, "success");
    
    const currentCount = registrationBase64Images.length;
    if (currentCount < 5) {
        document.getElementById('registration-prompt-text').textContent = registrationSteps[currentCount];
        document.getElementById('btn-capture-reg').disabled = false;
    } else {
        document.getElementById('registration-prompt-text').textContent = "FaceID collection complete! Click Clear or Save Profile.";
        document.getElementById('btn-capture-reg').disabled = true;
        stopRegistrationCamera();
    }
}

// ==========================================
// MY ACCOUNT PROFILE INTEGRATION
// ==========================================
let isApiKeyVisible = false;

async function loadUserProfileData() {
    try {
        const response = await fetch('/api/auth/profile');
        if (!response.ok) return;
        const data = await response.json();
        
        document.getElementById('account-fullname').value = data.full_name || '';
        document.getElementById('account-username').value = data.username || '';
        document.getElementById('account-email').value = data.email || '';
        document.getElementById('account-phone').value = data.phone || '';
        document.getElementById('account-company').value = data.company_name || '';
        document.getElementById('account-timezone').value = data.timezone || 'UTC';
        document.getElementById('account-pref-email').checked = data.email_notifications;
        document.getElementById('account-api-key-field').value = data.api_key || '';
        
        // Update user global object
        window.USER.companyName = data.company_name;
        window.USER.username = data.username;
        document.getElementById('username-display').textContent = data.full_name || data.username;
        
        // Avatar rendering
        const avatarPreview = document.getElementById('account-avatar-preview');
        const headerAvatar = document.getElementById('header-avatar-container');
        if (data.profile_picture) {
            avatarPreview.innerHTML = `<img src="${data.profile_picture}" alt="Profile avatar">`;
            headerAvatar.innerHTML = `<img src="${data.profile_picture}" alt="Avatar" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        } else {
            avatarPreview.innerHTML = `<i class="fa-solid fa-user-shield default-avatar-icon"></i>`;
            headerAvatar.innerHTML = `<i class="fa-solid fa-user-shield"></i>`;
        }
    } catch (e) {
        console.error("Error loading user profile:", e);
    }
}

async function saveUserProfileDetails() {
    const fullName = document.getElementById('account-fullname').value.trim();
    const email = document.getElementById('account-email').value.trim();
    const phone = document.getElementById('account-phone').value.trim();
    const company = document.getElementById('account-company').value.trim();
    const timezone = document.getElementById('account-timezone').value;
    const emailNotifications = document.getElementById('account-pref-email').checked;
    
    if (!email) {
        Toast.show("Email address is required.", "error");
        return;
    }
    
    try {
        const response = await fetch('/api/auth/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                full_name: fullName,
                phone: phone,
                company_name: company,
                timezone: timezone,
                email_notifications: emailNotifications
            })
        });
        
        if (response.ok) {
            const res = await response.json();
            Toast.show(res.message, "success");
            loadUserProfileData();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Save profile failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error saving profile details.", "error");
    }
}

async function saveUserProfilePassword() {
    const currentPassword = document.getElementById('account-pwd-current').value;
    const newPassword = document.getElementById('account-pwd-new').value;
    const confirmPassword = document.getElementById('account-pwd-confirm').value;
    
    if (!currentPassword || !newPassword || !confirmPassword) {
        Toast.show("Please fill in all password fields.", "error");
        return;
    }
    
    try {
        const response = await fetch('/api/auth/profile/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });
        
        if (response.ok) {
            const res = await response.json();
            Toast.show(res.message, "success");
            
            // Clear password fields
            document.getElementById('account-pwd-current').value = '';
            document.getElementById('account-pwd-new').value = '';
            document.getElementById('account-pwd-confirm').value = '';
        } else {
            const err = await response.json();
            Toast.show(err.error || "Password update failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error updating password.", "error");
    }
}

async function saveUserNotificationPrefs() {
    // Notify preferences are bundled into saveUserProfileDetails
    await saveUserProfileDetails();
}

async function handleAvatarUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/auth/profile/picture', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const res = await response.json();
            Toast.show(res.message, "success");
            loadUserProfileData();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Avatar upload failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error uploading avatar image.", "error");
    }
}

function toggleApiKeyVisibility() {
    const keyField = document.getElementById('account-api-key-field');
    const toggleBtn = document.getElementById('btn-toggle-key-visibility');
    isApiKeyVisible = !isApiKeyVisible;
    if (isApiKeyVisible) {
        keyField.type = 'text';
        toggleBtn.innerHTML = `<i class="fa-solid fa-eye-slash"></i>`;
    } else {
        keyField.type = 'password';
        toggleBtn.innerHTML = `<i class="fa-solid fa-eye"></i>`;
    }
}

function copyApiKeyToClipboard() {
    const keyField = document.getElementById('account-api-key-field');
    if (!keyField.value || keyField.value === 'wp_live_empty_key_placeholder') {
        Toast.show("No API key available.", "error");
        return;
    }
    
    navigator.clipboard.writeText(keyField.value)
        .then(() => {
            Toast.show("API key copied to clipboard.", "success");
        })
        .catch(err => {
            console.error("Clipboard copy failed: ", err);
            Toast.show("Failed to copy API key.", "error");
        });
}

async function rotateUserIntegrationKey() {
    if (!confirm("Are you sure you want to rotate your developer API Key? Any external service integrations using the current key will lose access immediately.")) {
        return;
    }
    
    try {
        const response = await fetch('/api/auth/profile/api-key', { method: 'POST' });
        if (response.ok) {
            const res = await response.json();
            Toast.show(res.message, "success");
            document.getElementById('account-api-key-field').value = res.api_key;
        } else {
            const err = await response.json();
            Toast.show(err.error || "API Key rotation failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error rotating API Key.", "error");
    }
}

// ==========================================
// RESTRICTED ZONE INTRUSION DRAWING CANVAS
// ==========================================
let isZonesDrawingMode = false;
let zoneDrawnPoints = [];
let savedZones = [];

function toggleZonesDrawingMode() {
    const canvas = document.getElementById('zone-drawing-canvas');
    const panel = document.getElementById('zone-drawing-panel');
    const btn = document.getElementById('btn-zones-config');
    
    if (!canvas || !panel || !btn) return;
    
    isZonesDrawingMode = !isZonesDrawingMode;
    
    if (isZonesDrawingMode) {
        btn.classList.add('btn-success');
        btn.classList.remove('btn-muted');
        panel.style.display = 'flex';
        canvas.style.pointerEvents = 'auto';
        zoneDrawnPoints = [];
        loadSavedZones();
        
        // Bind events
        canvas.addEventListener('mousedown', handleZoneCanvasMouseDown);
        window.addEventListener('resize', resizeZoneCanvas);
        // Initial resize
        setTimeout(resizeZoneCanvas, 100);
        Toast.show("Drawing mode enabled. Click on the camera feed to draw points of the restricted polygon.", "info");
    } else {
        btn.classList.remove('btn-success');
        btn.classList.add('btn-muted');
        panel.style.display = 'none';
        canvas.style.pointerEvents = 'none';
        
        // Unbind events
        canvas.removeEventListener('mousedown', handleZoneCanvasMouseDown);
        window.removeEventListener('resize', resizeZoneCanvas);
        
        // Clear canvas visual
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        Toast.show("Drawing mode closed.", "info");
    }
}

function resizeZoneCanvas() {
    const canvas = document.getElementById('zone-drawing-canvas');
    const img = document.getElementById('camera-stream');
    if (canvas && img) {
        canvas.width = img.clientWidth || 640;
        canvas.height = img.clientHeight || 480;
        drawAllZones();
    }
}

function handleZoneCanvasMouseDown(event) {
    if (!isZonesDrawingMode) return;
    const canvas = document.getElementById('zone-drawing-canvas');
    if (!canvas) return;
    
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    
    zoneDrawnPoints.push([x, y]);
    drawAllZones();
}

function clearDrawnPoints() {
    zoneDrawnPoints = [];
    drawAllZones();
}

async function loadSavedZones() {
    try {
        const url = activeCameraId ? `/api/camera/restricted-zones?camera_id=${activeCameraId}` : '/api/camera/restricted-zones';
        const response = await fetch(url);
        if (response.ok) {
            savedZones = await response.json();
            drawAllZones();
        }
    } catch (e) {
        console.error("Error loading zones:", e);
    }
}

function drawAllZones() {
    const canvas = document.getElementById('zone-drawing-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const w = canvas.width;
    const h = canvas.height;
    
    // 1. Draw saved zones
    savedZones.forEach(zone => {
        const pts = zone.points;
        if (!pts || pts.length < 3) return;
        
        ctx.beginPath();
        ctx.moveTo(pts[0][0] * w, pts[0][1] * h);
        for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0] * w, pts[i][1] * h);
        }
        ctx.closePath();
        
        // Draw filled zone
        ctx.fillStyle = 'rgba(99, 102, 241, 0.15)'; // Indigo/Blue translucent
        ctx.fill();
        
        // Draw border line
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Label zone
        ctx.fillStyle = '#6366f1';
        ctx.font = '10px Outfit';
        ctx.fillText(zone.name, pts[0][0] * w + 5, pts[0][1] * h - 5);
    });
    
    // 2. Draw currently drawing points
    if (zoneDrawnPoints.length > 0) {
        ctx.beginPath();
        ctx.moveTo(zoneDrawnPoints[0][0] * w, zoneDrawnPoints[0][1] * h);
        for (let i = 1; i < zoneDrawnPoints.length; i++) {
            ctx.lineTo(zoneDrawnPoints[i][0] * w, zoneDrawnPoints[i][1] * h);
        }
        
        // Draw path line (in green)
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Draw red circles for points
        zoneDrawnPoints.forEach((pt, index) => {
            ctx.beginPath();
            ctx.arc(pt[0] * w, pt[1] * h, 4, 0, 2 * Math.PI);
            ctx.fillStyle = '#ef4444';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 1;
            ctx.stroke();
            
            // Draw number
            ctx.fillStyle = '#fff';
            ctx.font = '9px Outfit';
            ctx.fillText(index + 1, pt[0] * w + 6, pt[1] * h - 4);
        });
    }
}

async function saveDrawnZone() {
    const nameInput = document.getElementById('zone-name-input');
    const name = nameInput ? nameInput.value.trim() : '';
    
    if (!name) {
        Toast.show("Please enter a name for the restricted zone.", "warning");
        return;
    }
    if (zoneDrawnPoints.length < 3) {
        Toast.show("Please draw at least 3 points before saving.", "warning");
        return;
    }
    
    try {
        const response = await fetch('/api/camera/restricted-zones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                points: zoneDrawnPoints,
                camera_id: activeCameraId
            })
        });
        
        if (response.ok) {
            Toast.show(`Restricted zone "${name}" successfully registered!`, "success");
            if (nameInput) nameInput.value = '';
            zoneDrawnPoints = [];
            loadSavedZones();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Could not save zone.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection error.", "error");
    }
}

async function resetAllDrawnZones() {
    if (!await showCustomConfirm("Delete All Zones", "Are you sure you want to delete all restricted zones?")) return;
    try {
        const response = await fetch('/api/camera/restricted-zones/all', { method: 'DELETE' });
        if (response.ok) {
            Toast.show("All restricted zones have been deleted.", "success");
            savedZones = [];
            zoneDrawnPoints = [];
            drawAllZones();
        }
    } catch (e) {
        console.error(e);
    }
}

async function triggerDashboardRefresh() {
    try {
        const response = await fetch('/api/camera/dashboard_live');
        if (response.ok) {
            const data = await response.json();
            renderLiveDashboard(data);
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteAlertEvent(id) {
    try {
        const response = await fetch(`/api/camera/alerts/${id}`, { method: 'DELETE' });
        if (response.ok) {
            Toast.show("Alert log deleted successfully.", "success");
            triggerDashboardRefresh();
        } else {
            Toast.show("Could not delete alert.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection error.", "error");
    }
}

async function deleteAllAlerts() {
    if (!await showCustomConfirm("Clear All Alerts", "Are you sure you want to clear all alerts? This cannot be undone.")) return;
    try {
        const response = await fetch('/api/camera/alerts/all', { method: 'DELETE' });
        if (response.ok) {
            Toast.show("All alerts cleared successfully.", "success");
            triggerDashboardRefresh();
        } else {
            Toast.show("Could not clear alerts.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection error.", "error");
    }
}

async function deleteAllUnknownFaces() {
    if (!await showCustomConfirm("Clear All Profiles", "Are you sure you want to clear all unknown face logs? This will delete all cropped files.")) return;
    try {
        const response = await fetch('/api/employees/unknown-faces/all', { method: 'DELETE' });
        if (response.ok) {
            Toast.show("All unidentified profiles cleared.", "success");
            loadUnknownFaces();
        } else {
            Toast.show("Could not clear profiles.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection error.", "error");
    }
}

function formatDurationFriendly(seconds) {
    if (seconds === undefined || seconds === null || seconds <= 0) return "0s";
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (seconds < 3600) {
        return `${mins}m ${secs}s`;
    }
    const hrs = Math.floor(seconds / 3600);
    const remMins = Math.floor((seconds % 3600) / 60);
    return `${hrs}h ${remMins}m`;
}

async function loadAttendanceLogs() {
    if (!window.USER.isAuthenticated) return;
    try {
        const response = await fetch('/api/employees/attendance-logs');
        if (response.ok) {
            const data = await response.json();
            const tbody = document.getElementById('attendance-logs-table-body');
            if (tbody) {
                if (!data || data.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 20px;">No historical shift logs found.</td>
                        </tr>
                    `;
                } else {
                    tbody.innerHTML = data.map(log => `
                        <tr>
                            <td><strong>${log.name}</strong><br><span style="font-size:10px; color:var(--text-muted);">${log.position}</span></td>
                            <td style="font-variant-numeric: tabular-nums;">${log.date}</td>
                            <td style="font-variant-numeric: tabular-nums;">${log.check_in}</td>
                            <td style="font-variant-numeric: tabular-nums;">${log.check_out}</td>
                            <td style="font-variant-numeric: tabular-nums; font-weight:500;">${formatDurationFriendly(log.active_time_raw)}</td>
                            <td style="font-variant-numeric: tabular-nums;">${formatDurationFriendly(log.idle_time_raw)}</td>
                            <td style="font-variant-numeric: tabular-nums; color:var(--error);">${formatDurationFriendly(log.phone_time_raw)}</td>
                            <td>
                                <span class="reg-dot ${log.late === 'Late' ? 'unregistered' : 'registered'}">
                                    ${log.late}
                                </span>
                            </td>
                            <td style="font-weight: 600; color: ${log.score >= 80 ? 'var(--success)' : 'var(--error)'}">${log.score}%</td>
                        </tr>
                    `).join('');
                }
            }
        }
    } catch (e) {
        console.error("Error loading attendance history:", e);
    }
}

function initTimeDropdowns() {
    const populate = (selectId) => {
        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '';
        for (let h = 0; h < 24; h++) {
            for (let m = 0; m < 60; m += 30) {
                const hour12 = h % 12 === 0 ? 12 : h % 12;
                const ampm = h >= 12 ? 'PM' : 'AM';
                const minStr = m === 0 ? '00' : '30';
                const timeText = `${hour12}:${minStr} ${ampm}`;
                
                const valHour = h.toString().padStart(2, '0');
                const valMin = m.toString().padStart(2, '0');
                const timeValue = `${valHour}:${valMin}`;
                
                const option = document.createElement('option');
                option.value = timeValue;
                option.textContent = timeText;
                select.appendChild(option);
            }
        }
    };
    populate('rules-start-time');
    populate('rules-end-time');
    populate('employee-shift-start');
    populate('employee-shift-end');
}

function updateSurveillanceStatus(isActive) {
    const dot = document.getElementById('sidebar-surveillance-dot');
    const text = document.getElementById('sidebar-surveillance-text');
    if (!dot || !text) return;
    if (isActive) {
        dot.classList.remove('inactive');
        text.textContent = 'Surveillance Active';
        text.style.color = '';
    } else {
        dot.classList.add('inactive');
        text.textContent = 'Surveillance Inactive';
        text.style.color = 'var(--text-muted)';
    }
}

function showCustomConfirm(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-confirm-modal');
        const titleEl = document.getElementById('confirm-title');
        const messageEl = document.getElementById('confirm-message');
        const btnCancel = document.getElementById('btn-confirm-cancel');
        const btnProceed = document.getElementById('btn-confirm-proceed');
        
        if (!modal || !titleEl || !messageEl || !btnCancel || !btnProceed) {
            resolve(confirm(message));
            return;
        }
        
        titleEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: var(--warning);"></i> ${title}`;
        messageEl.textContent = message;
        
        modal.style.display = 'flex';
        
        const cleanup = (value) => {
            modal.style.display = 'none';
            btnCancel.removeEventListener('click', onCancel);
            btnProceed.removeEventListener('click', onProceed);
            resolve(value);
        };
        
        const onCancel = () => cleanup(false);
        const onProceed = () => cleanup(true);
        
        btnCancel.addEventListener('click', onCancel);
        btnProceed.addEventListener('click', onProceed);
    });
}

// ==========================================
// MULTI-CAMERA INTERACTION LOGIC
// ==========================================
async function loadCameraDevices() {
    try {
        const response = await fetch('/api/camera/devices');
        if (response.ok) {
            cameraDevices = await response.json();
            if (cameraDevices.length > 0 && activeCameraId === null) {
                activeCameraId = cameraDevices[0].id;
            }
            renderCameraDevices();
            // Sync current active camera state to UI
            if (activeCameraId !== null) {
                selectActiveCamera(activeCameraId);
            }
        }
    } catch (e) {
        console.error("Error loading camera devices:", e);
    }
}

function renderCameraDevices() {
    // 1. Render Live Selector list
    const liveList = document.getElementById('live-camera-list');
    if (liveList) {
        liveList.innerHTML = cameraDevices.map(cam => `
            <div class="camera-list-item ${cam.id === activeCameraId ? 'active' : ''}" onclick="selectActiveCamera(${cam.id})">
                <div class="cam-info">
                    <span class="cam-name">${cam.name}</span>
                    <span class="cam-src">Source: ${cam.source}</span>
                </div>
                <span class="cam-badge ${cam.is_running ? 'online' : 'offline'}">${cam.is_running ? 'Active' : 'Offline'}</span>
            </div>
        `).join('');
    }

    // 2. Render Settings CRUD table
    const settingsTableBody = document.getElementById('camera-settings-table-body');
    if (settingsTableBody) {
        settingsTableBody.innerHTML = cameraDevices.map(cam => `
            <tr>
                <td style="font-weight: 600; color: #fff; padding: 12px;">${cam.name}</td>
                <td style="padding: 12px;"><code style="color: var(--accent); font-family: monospace;">${cam.source}</code></td>
                <td style="padding: 12px;">${cam.resolution}</td>
                <td style="padding: 12px;">${cam.fps} FPS</td>
                <td style="padding: 12px;">
                    <span class="badge ${cam.is_running ? 'badge-success' : 'badge-danger'}" style="font-size:11px; padding: 4px 8px; border-radius:4px;">
                        ${cam.is_running ? 'Online & Streaming' : 'Offline'}
                    </span>
                </td>
                <td style="padding: 12px;">
                    <button class="btn btn-sm btn-muted" onclick="openEditCameraModal(${cam.id})" style="padding: 4px 8px; font-size:11px;"><i class="fa-solid fa-pen-to-square"></i> Edit</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteCameraDevice(${cam.id})" style="padding: 4px 8px; font-size:11px;"><i class="fa-solid fa-trash-can"></i> Delete</button>
                </td>
            </tr>
        `).join('');
    }
}

function selectActiveCamera(cameraId) {
    activeCameraId = cameraId;
    
    // Update active highlight classes in live selector list
    const items = document.querySelectorAll('.camera-list-item');
    items.forEach(item => item.classList.remove('active'));
    
    const activeItem = Array.from(items).find(item => item.getAttribute('onclick').includes(cameraId));
    if (activeItem) activeItem.classList.add('active');

    const cam = cameraDevices.find(c => c.id === cameraId);
    if (cam) {
        const streamImg = document.getElementById('camera-stream');
        const streamOverlay = document.getElementById('stream-overlay');
        const btnStart = document.getElementById('btn-start-camera');
        const btnStop = document.getElementById('btn-stop-camera');
        const statusKPI = document.getElementById('kpi-cam-status');
        const liveIndicator = document.getElementById('live-indicator');
        
        if (cam.is_running) {
            if (streamImg) streamImg.src = `/api/camera/feed?camera_id=${cam.id}&t=${Date.now()}`;
            if (streamOverlay) streamOverlay.style.display = 'none';
            if (btnStart) btnStart.disabled = true;
            if (btnStop) btnStop.disabled = false;
            if (statusKPI) {
                statusKPI.textContent = 'Online';
                statusKPI.className = 'kpi-val text-success';
            }
            if (liveIndicator) liveIndicator.classList.add('active');
        } else {
            if (streamImg) streamImg.src = '';
            if (streamOverlay) streamOverlay.style.display = 'flex';
            if (btnStart) btnStart.disabled = false;
            if (btnStop) btnStop.disabled = true;
            if (statusKPI) {
                statusKPI.textContent = 'Offline';
                statusKPI.className = 'kpi-val text-danger';
            }
            if (liveIndicator) liveIndicator.classList.remove('active');
        }
        
        // Reload restricted zones specific to this camera
        loadSavedZones();
    }
}

async function startCameraStream() {
    if (activeCameraId === null) {
        Toast.show("No active camera selected.", "error");
        return;
    }
    
    try {
        const response = await fetch('/api/camera/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: activeCameraId })
        });
        
        if (response.ok) {
            Toast.show("Camera channel stream started.", "success");
            await loadCameraDevices();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Failed to start camera.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error starting camera link.", "error");
    }
}

async function stopCameraStream() {
    if (activeCameraId === null) {
        Toast.show("No active camera selected.", "error");
        return;
    }
    
    try {
        const response = await fetch('/api/camera/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: activeCameraId })
        });
        
        if (response.ok) {
            Toast.show("Camera channel stream stopped.", "success");
            await loadCameraDevices();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Failed to stop camera.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error stopping camera link.", "error");
    }
}

function toggleCustomCameraSourceInput() {
    const select = document.getElementById('camera-source-select');
    const customGroup = document.getElementById('camera-custom-source-group');
    const input = document.getElementById('camera-source-input');
    if (select.value === 'custom') {
        customGroup.style.display = 'block';
        input.setAttribute('required', 'true');
    } else {
        customGroup.style.display = 'none';
        input.removeAttribute('required');
        input.value = '';
    }
}

async function populateSystemCameras(selectedSource = '') {
    const select = document.getElementById('camera-source-select');
    const customGroup = document.getElementById('camera-custom-source-group');
    const input = document.getElementById('camera-source-input');
    
    // Reset options
    select.innerHTML = '<option value="">-- Scanning connected devices... --</option>';
    customGroup.style.display = 'none';
    input.value = '';
    
    try {
        const res = await fetch('/api/camera/system_devices');
        if (res.ok) {
            const data = await res.json();
            select.innerHTML = '';
            
            let matched = false;
            if (data.devices && data.devices.length > 0) {
                data.devices.forEach(device => {
                    const opt = document.createElement('option');
                    opt.value = device.index;
                    opt.textContent = `${device.name} (Index ${device.index})`;
                    select.appendChild(opt);
                    if (selectedSource !== '' && selectedSource === device.index) {
                        opt.selected = true;
                        matched = true;
                    }
                });
            }
            
            // Add custom source option
            const optCustom = document.createElement('option');
            optCustom.value = 'custom';
            optCustom.textContent = 'Custom Source (IP Stream / RTSP / Video File)';
            select.appendChild(optCustom);
            
            if (selectedSource !== '') {
                if (!matched) {
                    optCustom.selected = true;
                    customGroup.style.display = 'block';
                    input.value = selectedSource;
                    input.setAttribute('required', 'true');
                } else {
                    customGroup.style.display = 'none';
                    input.value = '';
                    input.removeAttribute('required');
                }
            } else {
                // Default to first index if adding new
                if (select.options.length > 1) {
                    select.selectedIndex = 0;
                } else {
                    optCustom.selected = true;
                }
                toggleCustomCameraSourceInput();
            }
        }
    } catch (err) {
        console.error("Error scanning cameras:", err);
        select.innerHTML = '<option value="custom" selected>Custom Source (IP Stream / RTSP / Video File)</option>';
        toggleCustomCameraSourceInput();
        if (selectedSource !== '') {
            input.value = selectedSource;
        }
    }
}

function openAddCameraModal() {
    document.getElementById('camera-device-id').value = '';
    document.getElementById('camera-name-input').value = '';
    document.getElementById('camera-source-input').value = '';
    document.getElementById('camera-resolution-input').value = '640x480';
    document.getElementById('camera-fps-input').value = '20';
    
    document.getElementById('camera-modal-title').innerHTML = `<i class="fa-solid fa-video"></i> Add Camera Channel`;
    document.getElementById('camera-modal').classList.add('active');
    
    populateSystemCameras('');
}

function openEditCameraModal(cameraId) {
    const cam = cameraDevices.find(c => c.id === cameraId);
    if (!cam) return;
    
    document.getElementById('camera-device-id').value = cam.id;
    document.getElementById('camera-name-input').value = cam.name;
    document.getElementById('camera-source-input').value = cam.source;
    document.getElementById('camera-resolution-input').value = cam.resolution || '640x480';
    document.getElementById('camera-fps-input').value = cam.fps || '20';
    
    document.getElementById('camera-modal-title').innerHTML = `<i class="fa-solid fa-video"></i> Edit Camera Channel`;
    document.getElementById('camera-modal').classList.add('active');
    
    populateSystemCameras(cam.source);
}

function closeCameraModal() {
    document.getElementById('camera-modal').classList.remove('active');
}

async function saveCameraDevice(event) {
    event.preventDefault();
    const id = document.getElementById('camera-device-id').value;
    const name = document.getElementById('camera-name-input').value.trim();
    
    const select = document.getElementById('camera-source-select');
    let source = '';
    if (select.value === 'custom') {
        source = document.getElementById('camera-source-input').value.trim();
    } else {
        source = select.value;
    }
    
    const resolution = document.getElementById('camera-resolution-input').value;
    const fps = document.getElementById('camera-fps-input').value;
    
    if (!name || !source) {
        Toast.show("Please fill out name and select camera fields.", "warning");
        return;
    }
    
    const url = id ? `/api/camera/devices/${id}` : '/api/camera/devices';
    const method = id ? 'PUT' : 'POST';
    
    try {
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, source, resolution, fps })
        });
        
        if (response.ok) {
            const res = await response.json();
            Toast.show(res.message, "success");
            closeCameraModal();
            await loadCameraDevices();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Save camera device failed.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error saving camera device parameters.", "error");
    }
}

async function deleteCameraDevice(cameraId) {
    const cam = cameraDevices.find(c => c.id === cameraId);
    if (!cam) return;
    
    const confirmDelete = await showCustomConfirm(
        "Delete Camera",
        `Are you sure you want to permanently delete camera "${cam.name}"? All custom zones drawn for this camera will be lost.`
    );
    if (!confirmDelete) return;
    
    try {
        const response = await fetch(`/api/camera/devices/${cameraId}`, { method: 'DELETE' });
        if (response.ok) {
            Toast.show("Camera device removed.", "success");
            // If the deleted camera was the active one, reset it to null so loadCameraDevices selects a new one
            if (activeCameraId === cameraId) {
                activeCameraId = null;
            }
            await loadCameraDevices();
        } else {
            const err = await response.json();
            Toast.show(err.error || "Could not delete camera.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Error deleting camera device.", "error");
    }
}

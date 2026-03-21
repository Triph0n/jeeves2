let ws;
let isOffline = false;
const statusDot = document.querySelector('.dot');
const statusText = document.getElementById('connection-status');
const jeevesStateText = document.getElementById('jeeves-state');
const avatarContainer = document.getElementById('avatar-container');
const transcriptText = document.getElementById('transcript-text');
const commandInput = document.getElementById('command-input');
const sendBtn = document.getElementById('send-btn');
const shutdownBtn = document.getElementById('shutdown-btn');
const mediaContainer = document.getElementById('media-container');
const mediaList = document.getElementById('media-list');
const clearMediaBtn = document.getElementById('clear-media-btn');
const tasksList = document.getElementById('tasks-list');
const refreshTasksBtn = document.getElementById('refresh-tasks-btn');

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        statusDot.classList.add('connected');
        statusText.textContent = 'Připojeno';
        console.log('Connected to Mission Control WS');
    };

    ws.onclose = () => {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Odpojeno - Připojování...';
        console.log('Disconnected. Reconnecting in 3s...');
        setState('offline', 'Offline');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleBackendEvent(data);
        } catch (e) {
            console.error('Failed to parse WS message:', e);
        }
    };
}

function setState(stateClass, labelText) {
    // Remove all state classes
    avatarContainer.classList.remove('state-listening', 'state-thinking', 'state-speaking');

    if (stateClass !== 'offline' && stateClass !== 'idle') {
        avatarContainer.classList.add(`state-${stateClass}`);
    }

    jeevesStateText.textContent = labelText;

    // Change textual color dynamically if needed based on state
    if (stateClass === 'thinking') {
        jeevesStateText.style.color = '#b026ff';
    } else if (stateClass === 'speaking') {
        jeevesStateText.style.color = 'var(--ok-color)';
    } else if (stateClass === 'listening') {
        jeevesStateText.style.color = 'var(--accent)';
    } else {
        jeevesStateText.style.color = 'var(--text-muted)';
    }
}

function setButtonToWakeup() {
    isOffline = true;
    shutdownBtn.textContent = '📞 Zavolat Jeevese';
    shutdownBtn.classList.remove('danger-btn');
    shutdownBtn.classList.add('wakeup-btn');
}

function setButtonToShutdown() {
    isOffline = false;
    shutdownBtn.textContent = '📴 Vypnout Jeevese';
    shutdownBtn.classList.remove('wakeup-btn');
    shutdownBtn.classList.add('danger-btn');
}

function handleBackendEvent(data) {
    console.log("Event:", data);

    if (data.type === 'state_change') {
        const stateMapping = {
            'listening': 'Poslouchám',
            'thinking': 'Zpracovávám...',
            'speaking': 'Mluvím',
            'idle': 'Připraven',
            'offline': 'Odpojeno'
        };
        setState(data.state, stateMapping[data.state] || 'Neznámý stav');

        // When Jeeves comes back online, reset button
        if (data.state === 'listening' && isOffline) {
            setButtonToShutdown();
        }
    }

    if (data.type === 'jeeves_dismissed') {
        setButtonToWakeup();
    }

    if (data.type === 'action_log') {
        transcriptText.textContent = data.message;
        transcriptText.style.color = '#ffffff';

        // Return to muted color after 5 seconds
        setTimeout(() => {
            if (transcriptText.textContent === data.message) {
                transcriptText.style.color = '#8a92a6';
            }
        }, 5000);
    }

    if (data.type === 'media_content') {
        const { mediaType, url, title } = data;
        const itemName = title || (mediaType === 'image' ? 'Obrázek' : 'Odkaz');
        
        const mediaItem = document.createElement('div');
        mediaItem.className = 'media-item';

        if (mediaType === 'image') {
            mediaItem.innerHTML = `
                <div class="media-item-content">
                    <span class="media-item-title">${itemName}</span>
                    <a href="${url}" target="_blank">
                        <img src="${url}" class="media-item-image" alt="Sdílený obrázek">
                    </a>
                </div>
            `;
        } else {
            // treat as link
            mediaItem.innerHTML = `
                <div class="media-item-icon">🔗</div>
                <div class="media-item-content">
                    <span class="media-item-title">${itemName}</span>
                    <a href="${url}" target="_blank" class="media-item-link">${url}</a>
                </div>
            `;
        }
        
        // Show container and append to top
        mediaContainer.style.display = 'flex';
        mediaList.prepend(mediaItem);
    }
}

function sendCommand() {
    const text = commandInput.value.trim();
    if (text && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: "user_command",
            text: text
        }));
        commandInput.value = '';
    }
}

async function shutdownJeeves() {
    if (confirm('Opravdu chcete Vypnout Jeevese?')) {
        try {
            await fetch('/api/shutdown', { method: 'POST' });
            setState('offline', 'Vypínání...');
            setButtonToWakeup();
        } catch (e) {
            console.error('Failed to send shutdown command:', e);
        }
    }
}

async function wakeupJeeves() {
    try {
        await fetch('/api/wakeup', { method: 'POST' });
        setState('offline', 'Volám Jeevese...');
        transcriptText.textContent = 'Probouzím Jeevese, chvíli strpení...';
    } catch (e) {
        console.error('Failed to send wakeup command:', e);
    }
}

// Initialize
window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();

    sendBtn.addEventListener('click', sendCommand);
    shutdownBtn.addEventListener('click', () => {
        if (isOffline) {
            wakeupJeeves();
        } else {
            shutdownJeeves();
        }
    });

    commandInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendCommand();
        }
    });

    clearMediaBtn.addEventListener('click', () => {
        mediaList.innerHTML = '';
        mediaContainer.style.display = 'none';
    });

    refreshTasksBtn.addEventListener('click', () => {
        refreshTasksBtn.style.transform = 'rotate(180deg)';
        setTimeout(() => refreshTasksBtn.style.transform = 'none', 300);
        fetchTasks();
    });

    // Attach button listeners
    if (refreshTasksBtn) {
        refreshTasksBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Zabraneni sbaleni detailu
            fetchTasks();
        });
    }

    if (refreshVacanciesBtn) {
        refreshVacanciesBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            refreshVacanciesBtn.style.transform = 'rotate(180deg)';
            setTimeout(() => refreshVacanciesBtn.style.transform = 'none', 300);
            fetchVacancies();
        });
    }

    // Start salary panel API polling
    fetchCostData();
    setInterval(fetchCostData, 10000);

    // Initial load
    fetchTasks();
    fetchVacancies();

    // Mavis Library launch button
    const launchMavisBtn = document.getElementById('launch-mavis-btn');
    const mavisBtnStatus = document.getElementById('mavis-btn-status');
    if (launchMavisBtn) {
        launchMavisBtn.addEventListener('click', async () => {
            launchMavisBtn.disabled = true;
            mavisBtnStatus.textContent = 'Spouštím server...';
            mavisBtnStatus.style.color = '#c9a84c';
            try {
                const res = await fetch('/api/launch_mavis', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'ok') {
                    mavisBtnStatus.textContent = '✓ Otevřeno v prohlížeči';
                    mavisBtnStatus.style.color = '#10b981';
                } else {
                    mavisBtnStatus.textContent = 'Chyba: ' + (data.detail || 'Neznámá chyba');
                    mavisBtnStatus.style.color = '#ff3366';
                }
            } catch (e) {
                mavisBtnStatus.textContent = 'Chyba připojení';
                mavisBtnStatus.style.color = '#ff3366';
            } finally {
                launchMavisBtn.disabled = false;
                setTimeout(() => {
                    mavisBtnStatus.textContent = 'Sci-Fi · localhost:8777';
                    mavisBtnStatus.style.color = '';
                }, 4000);
            }
        });
    }
});

// ============================================================
// Tasks Panel
// ============================================================
async function fetchTasks() {
    try {
        tasksList.innerHTML = '<p class="no-items">Načítám úkoly...</p>';
        const res = await fetch('/api/tasks');
        if (!res.ok) throw new Error('Failed to load tasks');
        const data = await res.json();
        renderTasks(data.tasks);
    } catch (e) {
        console.error(e);
        tasksList.innerHTML = '<p class="no-items" style="color: #ff3366;">Chyba při načítání úkolů.</p>';
    }
}

function renderTasks(tasks) {
    if (!tasks || tasks.length === 0) {
        tasksList.innerHTML = '<p class="no-items">Vše hotovo! Žádné úkoly k zobrazení.</p>';
        return;
    }

    tasksList.innerHTML = tasks.map(t => {
        const title = t.title || 'Nepojmenovaný úkol';
        let notesHtml = '';
        if (t.notes) {
            notesHtml = `<div class="task-notes">${t.notes}</div>`;
        }
        
        let dueHtml = '';
        if (t.due) {
            const dueDate = new Date(t.due).toLocaleDateString('cs-CZ');
            dueHtml = `<div class="task-notes" style="color: var(--accent);">Termín: ${dueDate}</div>`;
        }

        return `
            <div class="border-l-2 border-brand-gold pl-3 mb-3">
                <p class="text-sm font-medium text-white">${title}</p>
                ${notesHtml ? `<p class="text-xs text-brand-emerald">${t.notes}</p>` : ''}
                ${t.due ? `<p class="text-[10px] text-gray-500 uppercase">${new Date(t.due).toLocaleDateString('cs-CZ')}</p>` : ''}
            </div>
        `;
    }).join('');
}

// ============================================================
// Salary Panel — API Cost Tracking
// ============================================================

const USD_TO_CZK = 23.5; // Approximate conversion rate

function formatUsd(amount) {
    if (amount < 0.001) return '$0.000';
    if (amount < 1) return '$' + amount.toFixed(4);
    return '$' + amount.toFixed(3);
}

function formatCzk(usd) {
    const czk = usd * USD_TO_CZK;
    return '≈ ' + czk.toFixed(2) + ' Kč';
}

function formatTokens(count) {
    if (count >= 1_000_000) return (count / 1_000_000).toFixed(1) + 'M';
    if (count >= 1_000) return (count / 1_000).toFixed(1) + 'k';
    return count.toString();
}

function formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatSessionDate(isoString) {
    const d = new Date(isoString);
    return d.toLocaleDateString('cs-CZ', { day: '2-digit', month: '2-digit' }) + ' ' +
           d.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
}

async function fetchCostData() {
    try {
        const res = await fetch('/api/costs');
        if (!res.ok) return;
        const data = await res.json();
        updateSalaryPanel(data);
    } catch (e) {
        // Silently fail — server might not be ready yet
    }
}

function updateSalaryPanel(data) {
    // Monthly totals
    const mt = data.monthly_totals || {};
    document.getElementById('monthly-cost').textContent = formatUsd(mt.cost_usd || 0);
    document.getElementById('monthly-czk').textContent = formatCzk(mt.cost_usd || 0);
    document.getElementById('input-tokens').textContent = formatTokens(mt.input_tokens || 0);
    document.getElementById('output-tokens').textContent = formatTokens(mt.output_tokens || 0);
    document.getElementById('session-count').textContent = data.session_count || 0;

    // Current session
    const csPanel = document.getElementById('current-session-panel');
    if (data.current_session) {
        csPanel.style.display = 'flex';
        document.getElementById('session-duration').textContent = formatDuration(data.current_session.duration_sec || 0);
        document.getElementById('session-cost').textContent = formatUsd(data.current_session.cost_usd || 0);
    } else {
        csPanel.style.display = 'none';
    }

    // Recent sessions
    const sessionsList = document.getElementById('sessions-list');
    const sessions = data.recent_sessions || [];
    if (sessions.length === 0) {
        sessionsList.innerHTML = '<p class="no-sessions">Žádná data</p>';
    } else {
        sessionsList.innerHTML = sessions.slice().reverse().map(s => `
            <div class="flex justify-between items-center py-1 border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors px-1 rounded">
                <span class="w-1/3">${formatSessionDate(s.start)}</span>
                <span class="w-1/4 text-center">${formatTokens(s.input_tokens || 0)}↑ / ${formatTokens(s.output_tokens || 0)}↓</span>
                <span class="w-1/4 text-right text-brand-gold">${formatUsd(s.cost_usd || 0)}</span>
            </div>
        `).join('');
    }

    // Past months
    const pastMonths = data.past_months || [];
    const pmSection = document.getElementById('past-months-section');
    if (pastMonths.length > 0) {
        pmSection.style.display = 'block';
        document.getElementById('past-months-list').innerHTML = pastMonths.slice().reverse().map(pm => `
            <div class="flex justify-between items-center py-1 border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors px-1 rounded">
                <span class="w-1/3">${pm.month}</span>
                <span class="w-1/4 text-center">${pm.session_count || 0} sess</span>
                <span class="w-1/4 text-right text-brand-gold">${formatUsd(pm.cost_usd || 0)}</span>
            </div>
        `).join('');
    } else {
        pmSection.style.display = 'none';
    }
}

// ============================================================
// Vacancies Panel
// ============================================================

const muvacListElement = document.getElementById('muvac-list');
const musikzeitungListElement = document.getElementById('musikzeitung-list');
const vacanciesLoading = document.getElementById('vacancies-loading');
const vacanciesError = document.getElementById('vacancies-error');
const refreshVacanciesBtn = document.getElementById('refresh-vacancies-btn');

async function fetchVacancies() {
    if (!vacanciesLoading) return;
    vacanciesLoading.style.display = 'block';
    vacanciesError.style.display = 'none';
        
    try {
        const response = await fetch('/api/vacancies');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
            
        if (data.error) {
            throw new Error(data.error);
        }
            
        renderVacanciesList(muvacListElement, data.muvac, "Žádná nová místa na Muvac.");
        renderVacanciesList(musikzeitungListElement, data.musikzeitung, "Žádná nová místa na Musikzeitung.");
            
    } catch (error) {
        console.error("Failed to fetch vacancies:", error);
        if(vacanciesError) {
            vacanciesError.textContent = "Chyba při načítání nabídek: " + error.message;
            vacanciesError.style.display = 'block';
        }
    } finally {
        if(vacanciesLoading) vacanciesLoading.style.display = 'none';
    }
}

function renderVacanciesList(containerElement, items, emptyMessage) {
    if (!containerElement) return;
    containerElement.innerHTML = '';
        
    if (!items || items.length === 0) {
        containerElement.innerHTML = `<p class="no-items">${emptyMessage}</p>`;
        return;
    }

    items.forEach(item => {
        const aElem = document.createElement('a');
        aElem.className = 'vacancy-item';
        aElem.href = item.url;
        aElem.target = '_blank';
        aElem.rel = "noopener noreferrer";
            
        const titleElem = document.createElement('div');
        titleElem.className = 'vacancy-title';
        titleElem.textContent = item.title;
        aElem.appendChild(titleElem);

        if (item.organization) {
            const orgElem = document.createElement('div');
            orgElem.className = 'vacancy-org';
            orgElem.textContent = item.organization;
            aElem.appendChild(orgElem);
        }

        containerElement.appendChild(aElem);
    });
}

// ============================================================
// Daily Multi-Calendar Panel
// Members + their colors (must match CSS vars)
// ============================================================

const CAL_MEMBERS = {
    me:      { label: 'Já',      color: '#c9a84c' },
    max:     { label: 'Max',     color: '#60a5fa' },
    avi:     { label: 'Avi',     color: '#34d399' },
    beatrix: { label: 'Beatrix', color: '#f472b6' },
    ursula:  { label: 'Ursula',  color: '#a78bfa' },
};

function setCalTodayLabel() {
    const el = document.getElementById('cal-today-label');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleDateString('cs-CZ', {
        weekday: 'long', day: 'numeric', month: 'long'
    });
}

function renderCalEvents(events) {
    const container = document.getElementById('cal-events');
    if (!container) return;

    if (!events || events.length === 0) {
        container.innerHTML = '<p class="cal-empty">Dnes žádné události 🎉</p>';
        return;
    }

    // Sort by start time
    events.sort((a, b) => new Date(a.start) - new Date(b.start));

    container.innerHTML = events.map(ev => {
        const owner = ev.owner || 'me';
        const startStr = ev.all_day ? 'Celý den' : formatCalTime(ev.start);
        const endStr   = ev.all_day ? '' : (' – ' + formatCalTime(ev.end));
        return 
            <div class="cal-event" data-owner="">
                <div class="cal-event-time"></div>
                <div class="cal-event-body">
                    <div class="cal-event-title"></div>
                    <div class="cal-event-owner"></div>
                </div>
            </div>
        ;
    }).join('');
}

function formatCalTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

async function fetchCalendarEvents() {
    const container = document.getElementById('cal-events');
    if (!container) return;

    try {
        const res = await fetch('/api/calendar/today');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        renderCalEvents(data.events || []);
    } catch (e) {
        if (container) {
            container.innerHTML = '<p class="cal-empty" style="color:#f472b6;">Kalendář nedostupný</p>';
        }
        console.warn('Calendar fetch failed:', e);
    }
}

// Initialize calendar on load
document.addEventListener('DOMContentLoaded', () => {
    setCalTodayLabel();
    fetchCalendarEvents();
    // Refresh every 5 minutes
    setInterval(fetchCalendarEvents, 5 * 60 * 1000);
    // Also refresh date label at midnight
    setInterval(setCalTodayLabel, 60 * 1000);
});

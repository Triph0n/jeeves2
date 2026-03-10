let ws;
const statusDot = document.querySelector('.dot');
const statusText = document.getElementById('connection-status');
const jeevesStateText = document.getElementById('jeeves-state');
const avatarContainer = document.getElementById('avatar-container');
const transcriptText = document.getElementById('transcript-text');
const commandInput = document.getElementById('command-input');
const sendBtn = document.getElementById('send-btn');

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
    }

    if (data.type === 'action_log') {
        transcriptText.textContent = data.message;
        transcriptText.style.color = 'var(--text-main)';

        // Return to muted color after 5 seconds
        setTimeout(() => {
            if (transcriptText.textContent === data.message) {
                transcriptText.style.color = 'var(--text-muted)';
            }
        }, 5000);
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

// Initialize
window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();

    sendBtn.addEventListener('click', sendCommand);
    commandInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendCommand();
        }
    });
});

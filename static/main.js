// --- Global Variables & Initialization ---
let realtimePreview = false;
let typingTimer;
const typingInterval = 1000;
let currentEmotion = 'neutral';
let initialEmotionData = null;
let initialPersonaName = '';
let personaExists = false;

document.addEventListener('DOMContentLoaded', function() {
    if (window.appData) {
        currentEmotion = window.appData.currentEmotion || 'neutral';
        initialEmotionData = window.appData.emotionData || null;
        initialPersonaName = window.appData.personaName || '';
        personaExists = window.appData.personaExists || false;
    }
    createParticles();
    if (document.querySelector('.main-layout')) { // Check if on main page
        setupMainPage();
    }
    setupGeneralListeners();
});

function setupMainPage() {
    if (personaExists) {
        document.body.className = `theme-transition ${currentEmotion}`;
        // Setup post-analysis UI components
        loadChatHistory();
        updateLlamaStatusIndicator();
        updateChatWelcomeMessage();
        typeWriterEffect('.persona-greeting', 50);
    }
}

function setupGeneralListeners() {
    const textarea = document.getElementById('user_input');
    if (textarea) {
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = `${textarea.scrollHeight}px`;
        });
    }
    
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    };

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(modal => modal.style.display = 'none');
        }
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 'h': e.preventDefault(); showHistory(); break;
                case 'a': e.preventDefault(); showAnalytics(); break;
                case 'c': e.preventDefault(); showComparison(); break;
            }
        }
    });
}

// --- Particle Animation ---
function createParticles() {
    const particlesContainer = document.getElementById('particles');
    if (!particlesContainer) return;
    for (let i = 0; i < 15; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = `${Math.random() * 100}%`;
        const size = Math.random() * 10 + 5;
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.animationDelay = `${Math.random() * 20}s`;
        particle.style.animationDuration = `${Math.random() * 10 + 15}s`;
        particlesContainer.appendChild(particle);
    }
}

// --- Form & Page Loading ---
function handleSubmit(event) {
    showLoading();
}

function showLoading() {
    const loader = document.getElementById('page-loader');
    if(loader) loader.classList.add('show');
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
}

// --- Chat Functionality ---
function updateLlamaStatusIndicator() {
    const statusDiv = document.getElementById('llama-status');
    if (!statusDiv) return;
    fetch('/status').then(res => res.json()).then(data => {
        if (data.llama && data.llama.available) {
            statusDiv.innerHTML = `<span style="color: #4caf50; font-weight: 500;">🦙 Llama Active</span>`;
        } else {
            statusDiv.innerHTML = `<span style="color: #ff9800; font-weight: 500;">⚠️ Standard Responses</span>`;
        }
    }).catch(() => statusDiv.innerHTML = `<span style="color: #f44336;">Status check failed</span>`);
}

function updateChatWelcomeMessage() {
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage && initialPersonaName) {
        welcomeMessage.innerHTML = `Hi! I'm ${initialPersonaName}. How can I support you today?`;
    }
}

function handleChatKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChatMessage();
    }
}

function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    
    input.value = '';
    const sendButton = document.getElementById('send-button');
    sendButton.disabled = true;
    sendButton.textContent = '...';
    
    addMessageToChat(message, 'user');
    
    fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message, emotion: currentEmotion })
    })
    .then(res => res.json())
    .then(data => {
        if(data.error) {
            addMessageToChat('Sorry, I encountered an error.', 'therapist', {avatar: '🤖', name: 'System'});
        } else {
            addMessageToChat(data.response, 'therapist', data.persona, data.llama_generated, data.response_time);
        }
    })
    .catch(err => {
        console.error('Chat error:', err);
        addMessageToChat('Sorry, I encountered a connection error.', 'therapist', {avatar: '🤖', name: 'System'});
    })
    .finally(() => {
        sendButton.disabled = false;
        sendButton.textContent = 'Send';
        input.focus();
    });
}

function addMessageToChat(message, sender, persona, llamaGenerated, responseTime) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const msgDiv = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    if (sender === 'user') {
        msgDiv.className = 'user-message';
        msgDiv.innerHTML = `<div><div class="message-content">${message}</div><div class="message-timestamp">${timestamp}</div></div>`;
    } else {
        const responseTimeInfo = responseTime ? `(${(responseTime).toFixed(1)}s)` : '';
        const statusInfo = llamaGenerated ? `<span style="color: #4caf50;">🦙 Llama</span> ${responseTimeInfo}` : `<span style="color: #ff9800;">⚡ Quick</span> ${responseTimeInfo}`;
        msgDiv.className = 'therapist-message';
        msgDiv.innerHTML = `<div>
            <div class="message-persona">${persona.avatar} ${persona.name}</div>
            <div class="message-content">${message}</div>
            <div class="message-timestamp"><span>${timestamp}</span><span>${statusInfo}</span></div>
        </div>`;
    }
    container.appendChild(msgDiv);
    container.querySelector('.welcome-message')?.remove();
    container.scrollTop = container.scrollHeight;
}

function loadChatHistory() {
    fetch('/chat/history').then(res => res.json()).then(data => {
        const container = document.getElementById('chat-messages');
        if (data.history && data.history.length > 0) {
            container.innerHTML = '';
            data.history.forEach(msg => {
                addMessageToChat(msg.message, 'user');
                addMessageToChat(msg.response, 'therapist', { avatar: '🎭', name: msg.persona }, msg.llama_generated, msg.response_time);
            });
        }
    }).catch(err => console.error('Error loading chat history:', err));
}

function clearChatHistory() {
    if (confirm('Are you sure you want to clear your chat history?')) {
        fetch('/chat/clear').then(() => {
            document.getElementById('chat-messages').innerHTML = `<div class="welcome-message">Chat history cleared.</div>`;
            showNotification('Chat history cleared', 'success');
        }).catch(err => showNotification('Error clearing chat history', 'error'));
    }
}

// --- Modal & API Functions ---
function showHistory() { 
    const modal = document.getElementById('historyModal');
    modal.style.display = 'block';
    // Add fetch logic here
}
function showAnalytics() {
    const modal = document.getElementById('analyticsModal');
    modal.style.display = 'block';
    // Add fetch logic here
}
function showComparison() {
    const modal = document.getElementById('comparisonModal');
    modal.style.display = 'block';
    // Add fetch logic here
}
function showPersonaDetails(emotion) { 
    const modal = document.getElementById('personaModal');
    modal.style.display = 'block';
    // Add fetch logic here
}
function showSystemStatus() { 
    const modal = document.getElementById('systemStatusModal');
    modal.style.display = 'block';
    // Add fetch logic here
}

// --- Demo & Other Functions ---
function resetDemo() { console.log("Resetting demo"); }
function generateSampleData() { console.log("Generating sample data"); }
function toggleRealtimePreview() { console.log("Toggling preview"); }
function handleTextInput(el) { /* Placeholder */ }
function getMoreActivities(emotion) { console.log(`Getting activities for: ${emotion}`); }
function selectActivity(el) { console.log("Selected:", el.textContent); }
function startConversation() { console.log("Starting conversation"); }
function explainAnalysis() { console.log("Explaining analysis..."); }

// --- Utility Functions ---
function showNotification(message, type = 'info', duration = 3000) {
    const notification = document.createElement('div');
    notification.className = 'notification-popup';
    notification.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 15px 25px;
        border-radius: 12px;
        color: white;
        z-index: 1001;
        font-weight: 500;
        box-shadow: var(--shadow-medium);
        backdrop-filter: blur(10px);
    `;
    const colors = { success: '#4caf50', error: '#f44336', warning: '#ff9800', info: '#2196F3' };
    notification.style.background = colors[type] || colors.info;
    notification.innerHTML = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), duration);
}


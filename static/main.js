// --- Global Variables ---
let realtimePreview = false;
let typingTimer;
const typingInterval = 1000;
let currentEmotion = 'neutral';
let initialEmotionData = null;
let initialPersonaName = '';
let personaExists = false;

// --- Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data from the window object set in index.html
    if (window.appData) {
        currentEmotion = window.appData.currentEmotion || 'neutral';
        initialEmotionData = window.appData.emotionData || null;
        initialPersonaName = window.appData.personaName || '';
        personaExists = window.appData.personaExists || false;
    }

    // Initialize UI components
    createParticles();
    setupEventListeners();
    initScrollAnimations();

    if (personaExists) {
        // Apply emotion-specific theme class to the body
        document.body.className = `theme-transition ${currentEmotion}`;
        
        // Setup post-analysis UI components
        loadChatHistory();
        updateLlamaStatusIndicator();
        updateChatWelcomeMessage();
        typeWriterEffect('.persona-greeting', 50);
    }
});

/**
 * Creates floating particles for background effect.
 */
function createParticles() {
    const particlesContainer = document.getElementById('particles');
    if (!particlesContainer) return;
    const particleCount = 15;
    for (let i = 0; i < particleCount; i++) {
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

/**
 * Sets up global event listeners for key presses and modal clicks.
 */
function setupEventListeners() {
    const textarea = document.getElementById('user_input');
    if (textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = `${this.scrollHeight}px`;
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

/**
 * Initializes Intersection Observer for fade-in animations on scroll.
 */
function initScrollAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.content-card, .quote-section').forEach(card => {
        observer.observe(card);
    });
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
    }).then(res => res.json()).then(data => {
        addMessageToChat(data.response, 'therapist', data.persona, data.llama_generated, data.response_time);
    }).catch(err => {
        console.error('Chat error:', err);
        addMessageToChat('Sorry, I encountered an error. Please try again.', 'therapist');
    }).finally(() => {
        sendButton.disabled = false;
        sendButton.textContent = 'Send';
        input.focus();
    });
}

function addMessageToChat(message, sender, persona, llamaGenerated, responseTime) {
    const container = document.getElementById('chat-messages');
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

// --- Form Handling ---
function handleSubmit(event) { showLoading(); }
function showLoading() {
    document.querySelector('.input-form').style.display = 'none';
    document.getElementById('loading').style.display = 'block';
    document.getElementById('submit-btn').disabled = true;
}

// --- Other UI Functions ---
function typeWriterEffect(selector, speed = 50) {
    const element = document.querySelector(selector);
    if (!element) return;
    const text = element.textContent.trim();
    element.textContent = '';
    element.style.opacity = '1';
    let i = 0;
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i++);
            setTimeout(type, speed);
        }
    }
    type();
}

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

// --- Modal Content Loading (Stubs) ---
// Note: These functions need to fetch data and populate modal content.

function showHistory() {
    const modal = document.getElementById('historyModal');
    modal.style.display = 'block';
    const content = document.getElementById('history-content');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading history...</p></div>';
    fetch('/history')
        .then(response => response.json())
        .then(data => {
            // Logic to render history data into 'content' div here
            content.innerHTML = "History data loaded."; // Placeholder
        });
}

function showAnalytics() {
    const modal = document.getElementById('analyticsModal');
    modal.style.display = 'block';
    const content = document.getElementById('analytics-content');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading analytics...</p></div>';
    fetch('/analytics')
        .then(response => response.json())
        .then(data => {
            // Logic to render analytics data into 'content' div here
            content.innerHTML = "Analytics data loaded."; // Placeholder
        });
}

function showComparison() {
    const modal = document.getElementById('comparisonModal');
    modal.style.display = 'block';
    // Logic for comparison tool interaction goes here.
}

function showPersonaDetails(emotion) {
    const modal = document.getElementById('personaModal');
    modal.style.display = 'block';
    const content = document.getElementById('persona-modal-body');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading details...</p></div>';
    fetch(`/persona/${emotion}`)
        .then(response => response.json())
        .then(data => {
            // Logic to render persona details into 'content' div here
            document.getElementById('persona-modal-title').textContent = data.name;
            content.innerHTML = `<p>${data.specializes_in}</p>`; // Placeholder
        });
}

function showSystemStatus() {
    const modal = document.getElementById('systemStatusModal');
    modal.style.display = 'block';
    const content = document.getElementById('system-status-content');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading status...</p></div>';
    fetch('/status')
        .then(response => response.json())
        .then(data => {
            // Logic to render status data into 'content' div here
            content.innerHTML = `AI Status: ${data.emotion_classifier.status}`; // Placeholder
        });
}

function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function getMoreActivities(emotion) { console.log(`Get more activities for ${emotion}`); }
function selectActivity(el) { console.log(`Activity selected: ${el.textContent}`); }
function startConversation() { console.log('Starting conversation'); }
function explainAnalysis() { console.log('Explaining analysis...'); }
function resetDemo() { console.log('Resetting demo'); }
function generateSampleData() { console.log('Generating sample data'); }
function toggleRealtimePreview() { console.log('Toggling real-time preview'); }
function handleTextInput(el) { /* Handled by real-time preview logic if active */ }
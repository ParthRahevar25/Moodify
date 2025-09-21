from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from transformers import pipeline
import os
import random
import re
import json
from datetime import datetime, timedelta
import uuid
import logging
import subprocess
import time
# 🦙 Llama 3.2 Integration Configuration
LLAMA_MODEL = "llama3.2"  # Adjust based on your Ollama model name
LLAMA_AVAILABLE = False

def check_llama_availability():
    """Check if Llama 3.2 is available via Ollama"""
    global LLAMA_AVAILABLE
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=10)
        if LLAMA_MODEL in result.stdout:
            LLAMA_AVAILABLE = True
            logger.info(f"✅ Llama 3.2 ({LLAMA_MODEL}) is available")
        else:
            logger.warning(f"⚠️ Llama model '{LLAMA_MODEL}' not found in Ollama")
    except Exception as e:
        logger.error(f"❌ Error checking Llama availability: {e}")
        LLAMA_AVAILABLE = False

def generate_llama_response(prompt, persona_context, user_emotion, max_tokens=300):
    """Generate response using Llama 3.2 via Ollama"""
    try:
        # Create a therapeutic prompt with persona context
        therapeutic_prompt = f"""You are {persona_context['name']}, a compassionate AI therapist with a {persona_context['personality']} personality. 
The user is currently feeling {user_emotion}. 

Core values: {', '.join(persona_context.get('core_values', []))}
Personality traits: {', '.join(persona_context.get('personality_traits', []))}

User says: "{prompt}"

Respond as a professional therapist would, offering:
1. Validation of their feelings
2. Gentle guidance or coping strategies
3. Empathetic support
4. Stay in character as {persona_context['name']}

Keep response under 150 words and maintain a warm, supportive tone."""

        # Use the correct Ollama command structure
        result = subprocess.run([
            'ollama', 'run', LLAMA_MODEL
        ], 
        input=therapeutic_prompt,
        capture_output=True, 
        text=True, 
        timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            response = result.stdout.strip()
            # Clean up any artifacts from the generation
            response = re.sub(r'^Response:\s*', '', response)
            return response
        else:
            logger.error(f"Llama generation failed: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("Llama generation timed out")
        return None
    except Exception as e:
        logger.error(f"Error generating Llama response: {e}")
        return None
    
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-very-secret-key-that-you-should-change')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///mood_app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize database
# db = SQLAlchemy(app)

# Set up logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# 📖 Load quotes from external JSON file
def load_quotes():
    """Load quotes from quotes.json file"""
    try:
        with open('quotes.json', 'r', encoding='utf-8') as f:
            quotes_data = json.load(f)
        logger.info("✅ Quotes loaded successfully from quotes.json")
        return quotes_data
    except Exception as e:
        logger.error(f"⚠️ Error loading quotes.json: {e}")
        # Fallback quotes if file doesn't exist
        return {
            "joy": ["Keep smiling!", "Happiness is contagious!"],
            "sadness": ["It's okay to feel down. Better days are coming."],
            "anger": ["Take a deep breath. You've got this."],
            "fear": ["Bravery is not the absence of fear."],
            "surprise": ["Life is full of surprises!"],
            "love": ["You are deeply loved."],
            "neutral": ["Keep going. You're doing fine."]
        }

# Load quotes at startup
QUOTES_DATA = load_quotes()

# 🧠 Enhanced Hugging Face emotion classifier with robust error handling
emotion_classifier = None
fallback_mode = False

def initialize_emotion_classifier():
    """Initialize emotion classifier with fallback handling"""
    global emotion_classifier, fallback_mode
    try:
        # Updated to use top_k instead of deprecated return_all_scores
        emotion_classifier = pipeline(
            "text-classification", 
            model="j-hartmann/emotion-english-distilroberta-base", 
            top_k=None  # Returns all scores (replaces return_all_scores=True)
        )
        logger.info("✅ Emotion classifier loaded successfully")
        fallback_mode = False
    except Exception as e:
        logger.error(f"⚠️ Error loading emotion classifier: {e}")
        logger.info("🔄 Switching to fallback emotion detection")
        emotion_classifier = None
        fallback_mode = True

# 📊 Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    mood_entries = db.relationship('MoodEntry', backref='user', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class MoodEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    emotion = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    text_input = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    persona_used = db.Column(db.String(50))
    all_emotions_data = db.Column(db.Text)
    fallback_used = db.Column(db.Boolean, default=False)
    emotion_intensity = db.Column(db.String(20))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    persona_used = db.Column(db.String(50), nullable=False)
    emotion_context = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    llama_generated = db.Column(db.Boolean, default=False)
    response_time = db.Column(db.Float)

# 🔤 Fallback emotion detection using keyword matching
EMOTION_KEYWORDS = {
    'joy': {
        'keywords': ['happy', 'excited', 'joy', 'celebration', 'amazing', 'wonderful', 'fantastic', 
                    'great', 'awesome', 'brilliant', 'perfect', 'love', 'thrilled', 'ecstatic',
                    'delighted', 'cheerful', 'elated', 'euphoric', 'blissful', 'overjoyed'],
        'weight': 1.0
    },
    'sadness': {
        'keywords': ['sad', 'depressed', 'down', 'upset', 'crying', 'tears', 'lonely', 'empty',
                    'heartbroken', 'devastated', 'miserable', 'gloomy', 'melancholy', 'grief',
                    'sorrow', 'despair', 'hopeless', 'disappointed', 'hurt', 'lost'],
        'weight': 1.0
    },
    'anger': {
        'keywords': ['angry', 'mad', 'furious', 'rage', 'annoyed', 'frustrated', 'irritated',
                    'pissed', 'outraged', 'livid', 'enraged', 'heated', 'bitter', 'resentful',
                    'hostile', 'aggressive', 'indignant', 'incensed', 'infuriated', 'fuming'],
        'weight': 1.0
    },
    'fear': {
        'keywords': ['scared', 'afraid', 'terrified', 'anxious', 'worried', 'nervous', 'panic',
                    'frightened', 'concerned', 'stressed', 'overwhelmed', 'insecure', 'uncertain',
                    'apprehensive', 'alarmed', 'distressed', 'uneasy', 'troubled', 'fearful', 'dread'],
        'weight': 1.0
    },
    'surprise': {
        'keywords': ['surprised', 'shocked', 'amazed', 'unexpected', 'sudden', 'wow', 'incredible',
                    'unbelievable', 'astonishing', 'stunning', 'remarkable', 'extraordinary',
                    'mind-blowing', 'jaw-dropping', 'startled', 'bewildered', 'flabbergasted',
                    'astounded', 'dumbfounded', 'taken aback'],
        'weight': 1.0
    },
    'love': {
        'keywords': ['love', 'adore', 'cherish', 'devoted', 'affection', 'romantic', 'passionate',
                    'intimate', 'caring', 'tender', 'warmth', 'fondness', 'attachment', 'bond',
                    'connection', 'soulmate', 'beloved', 'darling', 'sweetheart', 'crush'],
        'weight': 1.0
    },
    'neutral': {
        'keywords': ['okay', 'fine', 'normal', 'regular', 'usual', 'average', 'typical', 'standard',
                    'ordinary', 'common', 'routine', 'everyday', 'mundane', 'calm', 'steady',
                    'balanced', 'stable', 'peaceful', 'quiet', 'still'],
        'weight': 0.5
    }
}

# 🎭 Enhanced Mood Personas with Deep Personality Profiles
MOOD_PERSONAS = {
    'joy': {
        'name': 'Sunny',
        'avatar': '😊',
        'personality': 'energetic, optimistic, encouraging',
        'personality_traits': ['Uplifting', 'Energetic', 'Celebratory', 'Motivating', 'Positive'],
        'core_values': ['Celebration', 'Gratitude', 'Sharing Joy', 'Motivation', 'Positivity'],
        'intensity_levels': {
            'mild': 'content and peaceful',
            'moderate': 'happy and upbeat', 
            'high': 'ecstatic and euphoric'
        },
        'greeting_variations': [
            "Hey there, sunshine! I can feel your positive energy radiating! ✨",
            "What a beautiful day to be alive! Your joy is absolutely contagious! 🌟",
            "Look at you glowing with happiness! This is what pure joy looks like! ☀️",
            "I'm practically bouncing with excitement just being here with you! 🎉",
            "Your smile is lighting up everything around you right now! 🌈"
        ],
        'activities': [
            'Create a gratitude photo collage',
            'Plan a celebration for your wins',
            'Start an uplifting playlist',
            'Share joy with someone you love',
            'Dance to your favorite song',
            'Write down 3 things that made you smile today',
            'Call someone and share your good news',
            'Take a victory selfie',
            'Plan a small treat for yourself'
        ],
        'color_scheme': '#FFD700',
        'conversation_starters': [
            "What made you smile today?",
            "Tell me about something you're excited about!",
            "What victory should we celebrate?",
            "Who would you love to share this joy with?",
            "What's the best part of your day so far?"
        ],
        'response_patterns': [
            "That's absolutely wonderful!",
            "I love hearing about your happiness!",
            "Your joy is so inspiring!",
            "This calls for a celebration!",
            "You deserve all this happiness!"
        ]
    },
    'sadness': {
        'name': 'Luna',
        'avatar': '🌙',
        'personality': 'gentle, empathetic, nurturing',
        'personality_traits': ['Compassionate', 'Gentle', 'Understanding', 'Healing', 'Supportive'],
        'core_values': ['Empathy', 'Healing', 'Patience', 'Comfort', 'Understanding'],
        'intensity_levels': {
            'mild': 'a bit melancholy',
            'moderate': 'deeply sad',
            'high': 'overwhelmed with grief'
        },
        'greeting_variations': [
            "I'm here with you. Sometimes we need quiet moments to heal. 💙",
            "Your feelings are so valid. Let's sit with this sadness together. 🌙",
            "I see your pain, and I want you to know you're not alone. 🕊️",
            "It's okay to not be okay. I'm here to listen and support you. 💜",
            "Your heart needs gentle care right now, and that's perfectly okay. 🌸"
        ],
        'activities': [
            'Try a 5-minute guided meditation',
            'Write in a feelings journal',
            'Make yourself a warm cup of tea',
            'Take a gentle walk outside',
            'Listen to calming music',
            'Call someone who cares about you',
            'Watch comforting movies',
            'Practice gentle breathing exercises',
            'Create art to express your feelings'
        ],
        'color_scheme': '#6B73FF',
        'conversation_starters': [
            "Would you like to talk about what's weighing on your heart?",
            "What would bring you a small moment of peace right now?",
            "How can I support you through this?",
            "What do you need most in this moment?",
            "Would it help to share what happened?"
        ],
        'response_patterns': [
            "I understand how you're feeling.",
            "Your emotions are completely valid.",
            "Take all the time you need.",
            "You're stronger than you know.",
            "This feeling will pass, I promise."
        ]
    },
    'anger': {
        'name': 'Phoenix',
        'avatar': '🔥',
        'personality': 'strong, direct, transformative',
        'personality_traits': ['Powerful', 'Direct', 'Transformative', 'Protective', 'Assertive'],
        'core_values': ['Justice', 'Boundaries', 'Transformation', 'Strength', 'Action'],
        'intensity_levels': {
            'mild': 'irritated and frustrated',
            'moderate': 'angry and fired up',
            'high': 'furious and raging'
        },
        'greeting_variations': [
            "I feel your fire. Let's channel this energy into something powerful! 🔥",
            "That anger shows you have strong values. Let's use this energy! ⚡",
            "I see the warrior in you rising up. This fire can create change! 💪",
            "Your anger is valid and powerful. Let's transform it into action! 🚀",
            "This intensity you feel? It's your inner strength demanding justice! ⚔️"
        ],
        'activities': [
            'Try high-intensity exercise',
            'Write an angry letter (then tear it up)',
            'Create something with your hands',
            'Practice powerful breathing exercises',
            'Go for a vigorous walk or run',
            'Punch a pillow or scream in your car',
            'Channel anger into creative expression',
            'Set clear boundaries with others',
            'Plan constructive action steps'
        ],
        'color_scheme': '#FF4757',
        'conversation_starters': [
            "What injustice fired you up today?",
            "How can we turn this energy into positive change?",
            "What boundaries need to be set?",
            "What action would help you feel empowered?",
            "What's the real issue that needs addressing?"
        ],
        'response_patterns': [
            "Your anger is completely justified!",
            "Let's channel this power constructively.",
            "You have every right to feel this way.",
            "This energy can create real change.",
            "Your boundaries matter and deserve respect."
        ]
    },
    'fear': {
        'name': 'Sage',
        'avatar': '🦉',
        'personality': 'wise, protective, reassuring',
        'personality_traits': ['Wise', 'Protective', 'Calming', 'Grounding', 'Reassuring'],
        'core_values': ['Safety', 'Wisdom', 'Courage', 'Protection', 'Growth'],
        'intensity_levels': {
            'mild': 'slightly worried',
            'moderate': 'anxious and fearful',
            'high': 'terrified and panicking'
        },
        'greeting_variations': [
            "Fear shows us what matters. I'm here to help you find your courage. 🕊️",
            "I feel your worry, and I want you to know you're safe with me. 🦉",
            "Your concerns are valid. Let's work through this together. 💜",
            "Even in uncertainty, you have more strength than you realize. 🌟",
            "Fear is just excitement without breath. Let's breathe together. 🌿"
        ],
        'activities': [
            'Practice the 5-4-3-2-1 grounding technique',
            'Write down what you can control',
            'Take three deep, calming breaths',
            'Reach out to someone who makes you feel safe',
            'Create a safety plan for yourself',
            'Practice progressive muscle relaxation',
            'Visualize your safe space',
            'Break down big fears into smaller steps',
            'Research and prepare for what worries you'
        ],
        'color_scheme': '#7B68EE',
        'conversation_starters': [
            "What would you do if you weren't afraid?",
            "What support do you need to feel safer?",
            "What's one small brave step you could take?",
            "What are you most worried will happen?",
            "How can we prepare you for what's ahead?"
        ],
        'response_patterns': [
            "You're braver than you believe.",
            "Let's take this one step at a time.",
            "Your caution shows wisdom.",
            "Fear is natural - you're not alone.",
            "We'll face this together."
        ]
    },
    'love': {
        'name': 'Rose',
        'avatar': '💕',
        'personality': 'warm, romantic, connecting',
        'personality_traits': ['Warm', 'Romantic', 'Connecting', 'Nurturing', 'Appreciative'],
        'core_values': ['Love', 'Connection', 'Appreciation', 'Kindness', 'Unity'],
        'intensity_levels': {
            'mild': 'fond and affectionate',
            'moderate': 'deeply in love',
            'high': 'passionately devoted'
        },
        'greeting_variations': [
            "Love is in the air! Your heart is so open and beautiful right now. 💖",
            "I can feel the love radiating from you - it's absolutely magical! 🌹",
            "Your heart is full and it's lighting up everything around you! ✨",
            "The love you're feeling is a gift to yourself and others! 💝",
            "Your capacity for love is one of your most beautiful qualities! 💕"
        ],
        'activities': [
            'Write a love note to yourself',
            'Call someone you appreciate',
            'Create a list of things you adore',
            'Plan something special for a loved one',
            'Look at photos of happy memories',
            'Practice loving-kindness meditation',
            'Express gratitude to someone important',
            'Create something beautiful for someone',
            'Share a meaningful moment with loved ones'
        ],
        'color_scheme': '#FF69B4',
        'conversation_starters': [
            "Who are you grateful to have in your life?",
            "How are you showing yourself love today?",
            "What makes your heart feel full?",
            "What's the most beautiful thing about this relationship?",
            "How does love show up in your daily life?"
        ],
        'response_patterns': [
            "Love is such a beautiful thing!",
            "Your heart is so open and generous.",
            "The love you give comes back to you.",
            "You deserve all the love you're feeling.",
            "Love multiplies when it's shared!"
        ]
    },
    'surprise': {
        'name': 'Spark',
        'avatar': '⚡',
        'personality': 'curious, adventurous, spontaneous',
        'personality_traits': ['Curious', 'Adventurous', 'Spontaneous', 'Playful', 'Enthusiastic'],
        'core_values': ['Adventure', 'Curiosity', 'Spontaneity', 'Discovery', 'Wonder'],
        'intensity_levels': {
            'mild': 'pleasantly surprised',
            'moderate': 'shocked and amazed',
            'high': 'completely astounded'
        },
        'greeting_variations': [
            "Whoa! Life just threw you a curveball! Let's explore what this means! ⭐",
            "Plot twist! I love how life keeps things interesting, don't you? 🎢",
            "Surprise! The universe clearly has some exciting plans for you! ✨",
            "Well, that was unexpected! Let's see where this adventure leads! 🗺️",
            "Life just got interesting! I'm here for this wild ride with you! 🎪"
        ],
        'activities': [
            'Try something completely new today',
            'Ask yourself "What if?" questions',
            'Explore a random Wikipedia article',
            'Plan a spontaneous mini-adventure',
            'Call someone you haven\'t talked to in a while',
            'Take a different route to somewhere familiar',
            'Say yes to an unexpected opportunity',
            'Document this surprising moment',
            'Embrace the unknown with curiosity'
        ],
        'color_scheme': '#FFEB3B',
        'conversation_starters': [
            "What unexpected thing just happened?",
            "How might this surprise change your path?",
            "What adventure could this lead to?",
            "What possibilities does this open up?",
            "How are you feeling about this plot twist?"
        ],
        'response_patterns': [
            "Life is full of amazing surprises!",
            "This could be the start of something wonderful!",
            "Expect the unexpected - that's life!",
            "What an interesting turn of events!",
            "The best stories start with surprises!"
        ]
    },
    'neutral': {
        'name': 'Zen',
        'avatar': '🌱',
        'personality': 'balanced, mindful, steady',
        'personality_traits': ['Balanced', 'Mindful', 'Steady', 'Centered', 'Peaceful'],
        'core_values': ['Balance', 'Mindfulness', 'Peace', 'Stability', 'Presence'],
        'intensity_levels': {
            'mild': 'calm and centered',
            'moderate': 'balanced and steady',
            'high': 'deeply peaceful'
        },
        'greeting_variations': [
            "Finding balance in the everyday. Let's explore what's present for you right now. 🍃",
            "There's wisdom in this calm space you're in. What shall we discover? 🧘",
            "Sometimes the most profound moments happen in quiet spaces like this. 🕯️",
            "Your steady presence is a gift. Let's see what this moment holds. 🌿",
            "In this neutral space, you have room to choose what comes next. 🌸"
        ],
        'activities': [
            'Set a small intention for today',
            'Practice mindful breathing',
            'Organize one small space',
            'Reflect on what you need right now',
            'Take a mindful walk',
            'Practice gratitude for ordinary moments',
            'Do a simple meditation',
            'Focus on being present',
            'Notice the beauty in everyday things'
        ],
        'color_scheme': '#4CAF50',
        'conversation_starters': [
            "What's your mind focused on right now?",
            "How can we add some intentionality to your day?",
            "What small step would serve you well?",
            "What are you noticing in this moment?",
            "How would you like to feel moving forward?"
        ],
        'response_patterns': [
            "There's wisdom in taking things steady.",
            "Balance is a beautiful thing.",
            "Sometimes neutral is exactly what we need.",
            "Your calm presence is valuable.",
            "Peace is found in the present moment."
        ]
    }
}

def fallback_emotion_detection(text):
    """Enhanced fallback emotion detection using keyword matching with intensity"""
    if not text:
        return {'emotion': 'neutral', 'confidence': 0.3, 'all_emotions': [], 'intensity': 'mild'}
    
    text_lower = text.lower()
    scores = {}
    
    for emotion, data in EMOTION_KEYWORDS.items():
        score = 0
        matches = 0
        
        for keyword in data['keywords']:
            if keyword in text_lower:
                # Weight longer keywords more heavily
                keyword_weight = len(keyword) / 10 + data['weight']
                score += keyword_weight
                matches += 1
        
        # Normalize score by text length and add bonus for multiple matches
        if matches > 0:
            normalized_score = (score / len(text_lower.split())) + (matches * 0.1)
            scores[emotion] = min(normalized_score, 1.0)  # Cap at 1.0
    
    if not scores:
        # If no keywords found, return neutral with low confidence
        return {
            'emotion': 'neutral', 
            'confidence': 0.3, 
            'all_emotions': [{'label': 'neutral', 'score': 0.3}],
            'intensity': 'mild'
        }
    
    # Get primary emotion
    primary_emotion = max(scores.keys(), key=lambda k: scores[k])
    primary_confidence = scores[primary_emotion]
    
    # Determine intensity based on confidence and text patterns
    intensity = determine_emotion_intensity(text, primary_confidence)
    
    # Create all_emotions format similar to Hugging Face output
    all_emotions = [{'label': emotion, 'score': score} for emotion, score in scores.items()]
    all_emotions.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        'emotion': primary_emotion,
        'confidence': primary_confidence,
        'all_emotions': all_emotions,
        'intensity': intensity
    }

def determine_emotion_intensity(text, confidence):
    """Determine emotion intensity based on text patterns and confidence"""
    text_lower = text.lower()
    
    # Intensity indicators
    high_intensity_words = ['extremely', 'absolutely', 'completely', 'totally', 'incredibly', 
                           'very', 'so', 'really', 'super', 'ultra', 'immensely']
    caps_ratio = sum(1 for c in text if c.isupper()) / len(text) if text else 0
    exclamation_count = text.count('!')
    
    intensity_score = confidence
    
    # Boost for intensity words
    for word in high_intensity_words:
        if word in text_lower:
            intensity_score += 0.1
    
    # Boost for caps (shouting)
    if caps_ratio > 0.3:
        intensity_score += 0.2
    
    # Boost for exclamations
    intensity_score += min(exclamation_count * 0.1, 0.3)
    
    if intensity_score >= 0.8:
        return 'high'
    elif intensity_score >= 0.5:
        return 'moderate'
    else:
        return 'mild'

def analyze_emotion_with_confidence(text):
    """Enhanced emotion detection with confidence scores and fallback"""
    global fallback_mode
    
    if not text or len(text.strip()) < 3:
        return {
            'emotion': 'neutral', 
            'confidence': 0.3, 
            'all_emotions': [{'label': 'neutral', 'score': 0.3}],
            'fallback_used': True,
            'intensity': 'mild'
        }
    
    # Try Hugging Face first
    if not fallback_mode and emotion_classifier:
        try:
            results = emotion_classifier(text)
            
            # Handle the new API response format
            # With top_k=None, results is a list of dicts with 'label' and 'score'
            if isinstance(results, list) and len(results) > 0:
                # Sort by score (highest first)
                sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
                primary_emotion = sorted_results[0]
                
                # Normalize emotion labels to lowercase
                normalized_results = []
                for result in sorted_results:
                    normalized_results.append({
                        'label': result['label'].lower(),
                        'score': result['score']
                    })
                
                intensity = determine_emotion_intensity(text, primary_emotion['score'])
                
                return {
                    'emotion': primary_emotion['label'].lower(),
                    'confidence': primary_emotion['score'],
                    'all_emotions': normalized_results,
                    'fallback_used': False,
                    'intensity': intensity
                }
            else:
                logger.warning("Unexpected response format from emotion classifier")
                fallback_mode = True
                
        except Exception as e:
            logger.error(f"Hugging Face emotion analysis error: {e}")
            logger.info("Falling back to keyword detection")
            fallback_mode = True
    
    # Use fallback method
    fallback_result = fallback_emotion_detection(text)
    fallback_result['fallback_used'] = True
    return fallback_result

def generate_persona_response(emotion, persona_data, intensity='moderate', context=None):
    """Generate enhanced persona response based on emotion and intensity"""
    if not persona_data:
        return "Stay strong. You've got this! 💪"
    
    # Get quotes from external JSON
    emotion_quotes = QUOTES_DATA.get(emotion, QUOTES_DATA.get('neutral', ["You're doing great!"]))
    
    # Select quote based on intensity if available
    if len(emotion_quotes) > 3:
        if intensity == 'high':
            quote = random.choice(emotion_quotes[-2:])  # Last two quotes for high intensity
        elif intensity == 'mild':
            quote = random.choice(emotion_quotes[:2])   # First two for mild
        else:
            quote = random.choice(emotion_quotes[1:-1]) # Middle quotes for moderate
    else:
        quote = random.choice(emotion_quotes)
    
    # Add persona-specific enhancement
    if 'response_patterns' in persona_data:
        enhancement = random.choice(persona_data['response_patterns'])
        return f"{enhancement} {quote}"
    
    return quote

def get_persona_greeting(persona_data, intensity='moderate'):
    """Get intensity-appropriate greeting from persona"""
    if not persona_data or 'greeting_variations' not in persona_data:
        return "Hello! I'm here to help you with whatever you're feeling."
    
    greetings = persona_data['greeting_variations']
    
    # Select greeting based on intensity
    if len(greetings) > 1:
        if intensity == 'high':
            return greetings[0]  # Most energetic greeting
        elif intensity == 'mild':
            return greetings[-1] # Most gentle greeting
        else:
            return random.choice(greetings[1:-1] if len(greetings) > 2 else greetings)
    
    return random.choice(greetings)

def get_or_create_user():
    """Get or create user session with enhanced tracking"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        session['session_start'] = datetime.utcnow().isoformat()
        user = User(session_id=session['user_id'])
        db.session.add(user)
        try:
            db.session.commit()
            logger.info(f"Created new user session: {session['user_id']}")
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            db.session.rollback()
    return User.query.filter_by(session_id=session['user_id']).first()

def save_mood_entry(user, emotion_data, text_input, persona_name):
    """Save mood entry to database with enhanced data"""
    try:
        entry = MoodEntry(
            user_id=user.id,
            emotion=emotion_data['emotion'],
            confidence=emotion_data['confidence'],
            text_input=text_input[:1000],  # Limit text length
            persona_used=persona_name,
            all_emotions_data=json.dumps(emotion_data.get('all_emotions', [])),
            fallback_used=emotion_data.get('fallback_used', False),
            emotion_intensity=emotion_data.get('intensity', 'moderate')
        )
        db.session.add(entry)
        db.session.commit()
        logger.info(f"Saved mood entry: {emotion_data['emotion']} for user {user.id}")
    except Exception as e:
        logger.error(f"Database error saving mood entry: {e}")
        db.session.rollback()

def validate_input(text):
    """Validate and clean user input"""
    if not text:
        return None, "Please share something about how you're feeling."
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    # Check length
    if len(text) < 3:
        return None, "Please share a bit more about how you're feeling."
    
    if len(text) > 2000:
        return text[:2000], "Input was truncated to 2000 characters."
    
    # Basic sanitization (keep it simple for emotion analysis)
    text = re.sub(r'[^\w\s\.\!\?\,\;\:\-\(\)]', '', text)
    
    return text, None

# 🎵 Spotify tracks by emotion
emotion_to_spotify = {
    'joy': [
        '3tjFYV6RSFtuktYl3ZtYcq',
        '7qiZfU4dY1lWllzX7mPBI3',
        '2dpaYNEQHiRxtZbfNsse99'
    ],
    'sadness': [
        '0bYg9bo50gSsH3LtXe2SQn',
        '7zDzuGkJoZrVEi4EZLuOEB',
        '6nek1Nin9q48AVZcWs9e9D'
    ],
    'anger': [
        '2X485T9Z5Ly0xyaghN73ed',
        '0j2T0R9qNfGehGkL8E4gQf',
        '4iV5W9uYEdYUVa79Axb7Rh'
    ],
    'fear': [
        '6I9VzXrHxO9rA9A5euc8Ak',
        '6OnyAlyF0XzAc2Z2xW1Ozw',
        '6QgjcU0zLnzq5OrUoSZ3OK'
    ],
    'surprise': [
        '1rqqCSm0Qe4I9rUvWncaom',
        '2VxeLyX666F8uXCJ0dZF8B',
        '1pKYYY0dkg23sQQXi0Q5zN'
    ],
    'love': [
        '0rx0DJI556Ix5gBny6EWmn',
        '6UelLqGlWMcVH1E5c4H7lY',
        '1u8c2t2Cy7UBoG4ArRcF5g'
    ],
    'neutral': [
        '6J6Wx0RUhSdyU5mBWz0kLa',
        '4iJyoBOLtHqaGxP12qzhQI',
        '5HCyWlXZPP0y6Gqq8TgA20'
    ]
}

# 🎮 Game HTML mapping based on emotion
emotion_to_game = {
    'joy': 'static/games/flappy.html',
    'sadness': 'static/games/calm_breathing.html',
    'anger': 'brickbreaker.html',
    'fear': 'space_invaders.html',
    'surprise': 'click_challenge.html',
    'love': 'puzzle.html',
    'neutral': 'default_game.html'
}

def get_time_based_activities(activities, current_hour):
    """Customize activities based on time of day"""
    if 6 <= current_hour < 12:  # Morning
        return [f"This morning: {activity.lower()}" for activity in activities[:3]]
    elif 12 <= current_hour < 18:  # Afternoon
        return [f"This afternoon: {activity.lower()}" for activity in activities[2:5]]
    else:  # Evening
        return [f"This evening: {activity.lower()}" for activity in activities[-3:]]
    
# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'error')
            return redirect(url_for('signup'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('login.html', is_signup=True)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- Main Application Route ---
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    user = User.query.get(session['user_id'])
    
    emotion_data, persona, error_message = None, None, None
    
    if request.method == 'POST':
        user_input = request.form.get('user_input', '').strip()
        if len(user_input) < 3:
            error_message = "Please share a bit more about your feelings."
        else:
            try:
                emotion_data = analyze_emotion_with_confidence(user_input)
                emotion = emotion_data['emotion']
                persona = MOOD_PERSONAS.get(emotion, MOOD_PERSONAS['neutral'])
                save_mood_entry(user, emotion_data, user_input, persona['name'])
            except Exception as e:
                logger.error(f"Error processing mood analysis: {e}")
                error_message = "An error occurred during analysis. Please try again."

    greeting, quote, spotify_tracks, game_url, activities, conversation_starter = (None, None, [], None, [], None)
    if persona and emotion_data:
        greeting = random.choice(persona.get('greeting_variations', ["Hello!"]))
        quote = random.choice(QUOTES_DATA.get(emotion_data.get('emotion'), ["Keep going."]))
        spotify_tracks = emotion_to_spotify.get(emotion_data.get('emotion'), [])
        game_url = emotion_to_game.get(emotion_data.get('emotion'))
        activities = persona.get('activities', [])
        conversation_starter = random.choice(persona.get('conversation_starters', ["How are you today?"]))

    return render_template('eample.html',
                           emotion_data=emotion_data, persona=persona, quote=quote,
                           greeting=greeting, spotify_tracks=spotify_tracks,
                           game_url=game_url, activities=activities,
                           conversation_starter=conversation_starter, error_message=error_message,
                           fallback_mode=fallback_mode, demo_mode=request.args.get('demo', False))


# 🌐 Routes

# @app.route('/', methods=['GET', 'POST'])
# @login_required
# def index():
#     emotion_data = None
#     persona = None
#     quote = None
#     greeting = None
#     spotify_tracks = []
#     game_url = None
#     activities = []
#     conversation_starter = None
#     error_message = None
#     demo_mode = request.args.get('demo', False)

#     if request.method == 'POST':
#         user_input = request.form.get('user_input', '').strip()
#         user = get_or_create_user()

#         # Validate input
#         cleaned_input, validation_error = validate_input(user_input)
#         if validation_error:
#             error_message = validation_error
#             if not cleaned_input:
#                 return render_template('eample.html', error_message=error_message)
#             user_input = cleaned_input

#         try:
#             # 🔍 Emotion detection
#             emotion_data = analyze_emotion_with_confidence(user_input)
#             emotion = emotion_data['emotion']
#             intensity = emotion_data.get('intensity', 'moderate')

#             # 🎭 Get persona for this emotion
#             persona = MOOD_PERSONAS.get(emotion, MOOD_PERSONAS['neutral'])

#             # 🗣️ Generate persona greeting based on intensity
#             greeting = get_persona_greeting(persona, intensity)

#             # ✨ Generate persona quote
#             quote = generate_persona_response(emotion, persona, intensity)

#             # 🎵 Get matching Spotify tracks
#             spotify_tracks = emotion_to_spotify.get(emotion, emotion_to_spotify['neutral'])

#             # 🎮 Load matching game
#             game_url = emotion_to_game.get(emotion, emotion_to_game['neutral'])

#             # 📋 Get time-based activities
#             current_hour = datetime.now().hour
#             activities = get_time_based_activities(persona['activities'], current_hour)

#             # 💬 Get conversation starter
#             conversation_starter = random.choice(persona['conversation_starters'])

#             # 💾 Save to database
#             save_mood_entry(user, emotion_data, user_input, persona['name'])

#             logger.info(f"Processed emotion: {emotion} (intensity: {intensity}) for user {user.session_id}")

#         except Exception as e:
#             logger.error(f"Error processing mood analysis: {e}")
#             error_message = "Something went wrong analyzing your mood. Please try again."
#             emotion_data = None

#     return render_template('eample.html',
#                            emotion_data=emotion_data,
#                            persona=persona,
#                            quote=quote,
#                            greeting=greeting,
#                            spotify_tracks=spotify_tracks,
#                            game_url=game_url,
#                            activities=activities,
#                            conversation_starter=conversation_starter,
#                            error_message=error_message,
#                            demo_mode=demo_mode,
#                            fallback_mode=fallback_mode)

# 📊 Enhanced Mood History with Analytics

@app.route('/chat', methods=['POST'])
@login_required
def chat_with_therapist():
    """Handle chat messages with AI therapist"""
    if 'user_id' not in session:
        return jsonify({'error': 'No session found'}), 400
    
    user = User.query.get(session['user_id'])
    data = request.get_json()
    
    user_message = data.get('message', '').strip()
    current_emotion = data.get('emotion', 'neutral')
    
    if not user_message or len(user_message) < 3:
        return jsonify({'error': 'Message too short'}), 400
    
    if len(user_message) > 1000:
        user_message = user_message[:1000]
    
    try:
        # Get current persona based on emotion
        persona = MOOD_PERSONAS.get(current_emotion, MOOD_PERSONAS['neutral'])
        
        start_time = time.time()
        llama_response = None
        
        # Try Llama first if available
        if LLAMA_AVAILABLE:
            llama_response = generate_llama_response(
                user_message, 
                persona, 
                current_emotion
            )
        
        response_time = time.time() - start_time
        
        # Fallback to predefined responses if Llama fails
        if not llama_response:
            pattern = random.choice(persona.get('response_patterns', ['I understand how you feel.']))
            quote = random.choice(QUOTES_DATA.get(current_emotion, ["You're doing great."]))

            fallback_responses = [
                f"I hear you saying {user_message[:50]}... As {persona['name']}, I want you to know that your feelings are completely valid.",
                f"Thank you for sharing that with me. {pattern}",
                f"I'm here to listen and support you through this {current_emotion}. {quote}"
            ]

            llama_response = random.choice(fallback_responses)
            llama_generated = False
        else:
            llama_generated = True

        # Save chat message to database
        chat_message = ChatMessage(
            user_id=user.id,
            message=user_message,
            response=llama_response,
            persona_used=persona['name'],
            emotion_context=current_emotion,
            llama_generated=llama_generated,
            response_time=response_time
        )
        
        db.session.add(chat_message)
        db.session.commit()
        
        return jsonify({
            'response': llama_response,
            'persona': {
                'name': persona['name'],
                'avatar': persona['avatar'],
                'personality': persona['personality']
            },
            'llama_generated': llama_generated,
            'response_time': round(response_time, 2)
        })
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return jsonify({'error': 'Failed to generate response'}), 500

@app.route('/chat/history')
@login_required
def get_chat_history():
    """Get recent chat history for user"""
    if 'user_id' not in session:
        return jsonify({'error': 'No session found'}), 400
    
    user = User.query.get(session['user_id'])
    
    try:
        messages = ChatMessage.query.filter_by(user_id=user.id)\
                                  .order_by(ChatMessage.timestamp.desc())\
                                  .limit(20).all()
        
        history = []
        for msg in reversed(messages):  # Reverse to show chronological order
            history.append({
                'id': msg.id,
                'message': msg.message,
                'response': msg.response,
                'persona': msg.persona_used,
                'emotion': msg.emotion_context,
                'timestamp': msg.timestamp.strftime('%H:%M'),
                'llama_generated': msg.llama_generated,
                'response_time': msg.response_time
            })
        
        return jsonify({'history': history})
        
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return jsonify({'error': 'Failed to fetch chat history'}), 500

@app.route('/chat/clear')
@login_required
def clear_chat_history():
    """Clear chat history for current user"""
    if 'user_id' not in session:
        return jsonify({'error': 'No session found'}), 400
    
    user = User.query.get(session['user_id'])
    
    try:
        ChatMessage.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        return jsonify({'message': 'Chat history cleared'})
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")
        return jsonify({'error': 'Failed to clear chat history'}), 500
    
@app.route('/history')
@login_required
def mood_history():
    """Get user's mood history with enhanced analytics"""
    if 'user_id' not in session:
        return jsonify({'error': 'No session found'}), 400
    
    user = User.query.filter_by(session_id=session['user_id']).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        entries = MoodEntry.query.filter_by(user_id=user.id)\
                               .order_by(MoodEntry.timestamp.desc())\
                               .limit(20).all()
        
        # Enhanced history data
        history_data = []
        emotion_counts = {}
        total_confidence = 0
        fallback_count = 0
        
        for entry in entries:
            # Parse all emotions data
            all_emotions = []
            try:
                if entry.all_emotions_data:
                    all_emotions = json.loads(entry.all_emotions_data)
            except:
                all_emotions = []
            
            history_entry = {
                'emotion': entry.emotion,
                'confidence': round(entry.confidence * 100, 1),
                'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M'),
                'persona': entry.persona_used,
                'intensity': entry.emotion_intensity,
                'fallback_used': entry.fallback_used,
                'all_emotions': all_emotions[:3]  # Top 3 emotions
            }
            history_data.append(history_entry)
            
            # Analytics
            emotion_counts[entry.emotion] = emotion_counts.get(entry.emotion, 0) + 1
            total_confidence += entry.confidence
            if entry.fallback_used:
                fallback_count += 1
        
        # Calculate analytics
        analytics = {
            'total_entries': len(entries),
            'average_confidence': round((total_confidence / len(entries)) * 100, 1) if entries else 0,
            'most_common_emotion': max(emotion_counts.items(), key=lambda x: x[1])[0] if emotion_counts else 'neutral',
            'emotion_distribution': emotion_counts,
            'fallback_usage': round((fallback_count / len(entries)) * 100, 1) if entries else 0
        }
        
        return jsonify({
            'history': history_data,
            'analytics': analytics
        })
        
    except Exception as e:
        logger.error(f"Error fetching mood history: {e}")
        return jsonify({'error': 'Failed to fetch mood history'}), 500

# 🎯 Enhanced Follow-up Suggestions
@app.route('/followup/<emotion>')
@login_required
def get_followup(emotion):
    """Get enhanced follow-up suggestions for an emotion"""
    try:
        persona = MOOD_PERSONAS.get(emotion, MOOD_PERSONAS['neutral'])
        
        # Get different activities than initially shown
        all_activities = persona['activities']
        suggested_activities = random.sample(all_activities, min(3, len(all_activities)))
        
        # Get a new conversation starter
        conversation_starter = random.choice(persona['conversation_starters'])
        
        # Generate persona-specific follow-up response
        follow_up_responses = [
            f"{persona['name']} says: Try focusing on what brings you {emotion} today.",
            f"As {persona['name']}, I encourage you to lean into this feeling constructively.",
            f"{persona['name']} suggests: This {emotion} can guide your next steps.",
            f"From my perspective as {persona['name']}: Use this energy wisely."
        ]
        
        suggestions = {
            'activities': suggested_activities,
            'conversation_starter': conversation_starter,
            'persona_response': random.choice(follow_up_responses),
            'intensity_tip': f"For {emotion} at this level: " + random.choice([
                "Take your time with whatever approach feels right.",
                "Trust your instincts about what you need most.",
                "Remember that all feelings are temporary and valuable.",
                "Use this as information about what matters to you."
            ])
        }
        
        return jsonify(suggestions)
        
    except Exception as e:
        logger.error(f"Error generating follow-up suggestions: {e}")
        return jsonify({'error': 'Failed to generate suggestions'}), 500

# 🎭 Persona Deep Dive Route
@app.route('/persona/<emotion>')
@login_required
def persona_details(emotion):
    """Get detailed persona information for demo purposes"""
    try:
        persona = MOOD_PERSONAS.get(emotion, MOOD_PERSONAS['neutral'])
        
        if not persona:
            return jsonify({'error': 'Persona not found'}), 404
        
        # Enhanced persona details for demo
        persona_details = {
            'name': persona['name'],
            'avatar': persona['avatar'],
            'personality': persona['personality'],
            'personality_traits': persona.get('personality_traits', []),
            'core_values': persona.get('core_values', []),
            'intensity_levels': persona.get('intensity_levels', {}),
            'sample_quotes': QUOTES_DATA.get(emotion, [])[:5],
            'conversation_style': persona.get('response_patterns', []),
            'specializes_in': f"Supporting people through {emotion} with {persona['personality']} approach"
        }
        
        return jsonify(persona_details)
        
    except Exception as e:
        logger.error(f"Error fetching persona details: {e}")
        return jsonify({'error': 'Failed to fetch persona details'}), 500

# 🔄 Emotion Comparison Route for Demo
@app.route('/compare', methods=['POST'])
@login_required
def compare_emotions():
    """Compare how different texts analyze emotions - for demo purposes"""
    try:
        data = request.get_json()
        texts = data.get('texts', [])
        
        if not texts or len(texts) < 2:
            return jsonify({'error': 'Please provide at least 2 text samples'}), 400
        
        comparisons = []
        
        for i, text in enumerate(texts[:5]):  # Limit to 5 comparisons
            cleaned_text, _ = validate_input(text)
            if cleaned_text:
                emotion_data = analyze_emotion_with_confidence(cleaned_text)
                persona = MOOD_PERSONAS.get(emotion_data['emotion'], MOOD_PERSONAS['neutral'])
                
                comparison = {
                    'index': i,
                    'text': text[:100] + "..." if len(text) > 100 else text,
                    'emotion': emotion_data['emotion'],
                    'confidence': round(emotion_data['confidence'] * 100, 1),
                    'intensity': emotion_data.get('intensity', 'moderate'),
                    'persona_name': persona['name'],
                    'persona_avatar': persona['avatar'],
                    'top_emotions': emotion_data.get('all_emotions', [])[:3],
                    'fallback_used': emotion_data.get('fallback_used', False)
                }
                comparisons.append(comparison)
        
        return jsonify({'comparisons': comparisons})
        
    except Exception as e:
        logger.error(f"Error in emotion comparison: {e}")
        return jsonify({'error': 'Failed to compare emotions'}), 500

# 📈 Analytics Dashboard Route
@app.route('/analytics')
@login_required
def analytics_dashboard():
    """Enhanced analytics for demonstration"""
    if 'user_id' not in session:
        return jsonify({'error': 'No session found'}), 400
    
    user = User.query.filter_by(session_id=session['user_id']).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        entries = MoodEntry.query.filter_by(user_id=user.id)\
                               .order_by(MoodEntry.timestamp.desc()).all()
        
        if not entries:
            return jsonify({'message': 'No data available yet'})
        
        # Detailed analytics
        analytics = {
            'overview': {
                'total_entries': len(entries),
                'date_range': {
                    'first_entry': entries[-1].timestamp.strftime('%Y-%m-%d'),
                    'latest_entry': entries[0].timestamp.strftime('%Y-%m-%d')
                },
                'average_confidence': round(sum(e.confidence for e in entries) / len(entries) * 100, 1)
            },
            'emotion_breakdown': {},
            'intensity_patterns': {'mild': 0, 'moderate': 0, 'high': 0},
            'persona_interactions': {},
            'confidence_trends': [],
            'hourly_patterns': {},
            'fallback_usage': {
                'ai_analysis': sum(1 for e in entries if not e.fallback_used),
                'keyword_analysis': sum(1 for e in entries if e.fallback_used)
            }
        }
        
        # Process each entry
        for entry in entries:
            # Emotion breakdown
            emotion = entry.emotion
            analytics['emotion_breakdown'][emotion] = analytics['emotion_breakdown'].get(emotion, 0) + 1
            
            # Intensity patterns
            intensity = entry.emotion_intensity or 'moderate'
            analytics['intensity_patterns'][intensity] += 1
            
            # Persona interactions
            persona = entry.persona_used or 'Unknown'
            analytics['persona_interactions'][persona] = analytics['persona_interactions'].get(persona, 0) + 1
            
            # Hourly patterns
            hour = entry.timestamp.hour
            analytics['hourly_patterns'][hour] = analytics['hourly_patterns'].get(hour, 0) + 1
            
            # Confidence trends (last 10 entries)
            if len(analytics['confidence_trends']) < 10:
                analytics['confidence_trends'].append({
                    'timestamp': entry.timestamp.strftime('%m-%d %H:%M'),
                    'confidence': round(entry.confidence * 100, 1),
                    'emotion': emotion
                })
        
        return jsonify(analytics)
        
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        return jsonify({'error': 'Failed to generate analytics'}), 500

# 🛠️ System Status Route for Demo
@app.route('/status')
@login_required
def system_status():
    """System status for demonstration"""
    status = {
        'emotion_classifier': {
            'status': 'active' if not fallback_mode else 'fallback',
            'model': 'j-hartmann/emotion-english-distilroberta-base' if not fallback_mode else 'keyword-based',
            'fallback_mode': fallback_mode
        },
        'personas': {
            'count': len(MOOD_PERSONAS),
            'available': list(MOOD_PERSONAS.keys())
        },
        'database': {
            'status': 'connected',
            'total_users': User.query.count(),
            'total_entries': MoodEntry.query.count()
        },
        'quotes': {
            'source': 'quotes.json',
            'emotions_covered': list(QUOTES_DATA.keys()),
            'total_quotes': sum(len(quotes) for quotes in QUOTES_DATA.values())
        },
        'llama': {
            'available': LLAMA_AVAILABLE,
            'model': LLAMA_MODEL,
            'chat_enabled': LLAMA_AVAILABLE
        },
    }
    
    return jsonify(status)

# 🎮 Demo Control Routes
@app.route('/demo/reset')
@login_required
def demo_reset():
    """Reset demo data for clean presentation"""
    if 'user_id' in session:
        user = User.query.filter_by(session_id=session['user_id']).first()
        if user:
            MoodEntry.query.filter_by(user_id=user.id).delete()
            db.session.commit()
    
    session.clear()
    return jsonify({'message': 'Demo reset complete'})

@app.route('/demo/sample-data')
@login_required
def demo_sample_data():
    """Generate sample data for demo"""
    sample_inputs = [
        "I just got promoted at work and I'm so excited to tell everyone!",
        "I'm feeling really anxious about my presentation tomorrow.",
        "My dog passed away yesterday and I can't stop crying.",
        "I'm absolutely furious about the unfair treatment at work today.",
        "I just met someone amazing and I think I'm falling in love!",
        "I won the lottery! I can't believe this is actually happening!",
        "Just having a regular Tuesday, nothing special happening."
    ]
    
    user = get_or_create_user()
    generated_entries = []
    
    for i, sample_text in enumerate(sample_inputs):
        emotion_data = analyze_emotion_with_confidence(sample_text)
        persona = MOOD_PERSONAS.get(emotion_data['emotion'], MOOD_PERSONAS['neutral'])
        
        # Create entry but with timestamp spread across last week
        entry_time = datetime.utcnow() - timedelta(days=6-i, hours=random.randint(0, 23))
        
        entry = MoodEntry(
            user_id=user.id,
            emotion=emotion_data['emotion'],
            confidence=emotion_data['confidence'],
            text_input=sample_text,
            persona_used=persona['name'],
            all_emotions_data=json.dumps(emotion_data.get('all_emotions', [])),
            fallback_used=emotion_data.get('fallback_used', False),
            emotion_intensity=emotion_data.get('intensity', 'moderate'),
            timestamp=entry_time
        )
        
        db.session.add(entry)
        generated_entries.append({
            'emotion': emotion_data['emotion'],
            'confidence': round(emotion_data['confidence'] * 100, 1),
            'persona': persona['name']
        })
    
    db.session.commit()
    
    return jsonify({
        'message': 'Sample data generated',
        'entries': generated_entries
    })

# Initialize Llama on startup
initialize_emotion_classifier()
check_llama_availability()

# 🚀 Run App
if __name__ == '__main__':
    # Create tables if they don't exist
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
    
    app.run(debug=True,port=5000)
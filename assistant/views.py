from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
import json
import requests
import re
import random
import uuid
from datetime import datetime
from transformers import pipeline
from tavily import TavilyClient
from .models import UserHealthProfile

# --- 1. CONFIGURATION ---
TAVILY_API_KEY = "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" 
TAVILY_CLIENT = TavilyClient(api_key=TAVILY_API_KEY)
IRCS_GUJ_CAMPS_URL = "https://www.indianredcross.org/gujarat"

# Available AI Models Configuration
AVAILABLE_MODELS = {
    "google/flan-t5-large": {
        "name": "Flan-T5 Large",
        "description": "Balanced - Best for most tasks",
        "badge": "Default"
    },
    "google/flan-t5-base": {
        "name": "Flan-T5 Base",
        "description": "Fast - Quick responses",
        "badge": "Fast"
    },
    "google/flan-t5-xl": {
        "name": "Flan-T5 XL",
        "description": "Powerful - Most accurate",
        "badge": "Advanced"
    }
}

# Cache for loaded models
MODEL_CACHE = {}
DEFAULT_MODEL = "google/flan-t5-large"

# --- 2. HELPER FUNCTIONS ---

def detect_language(text):
    """
    Detect language of the input text.
    Returns: 'en' (English), 'hi' (Hindi), 'gu' (Gujarati)
    """
    if not text or not text.strip():
        return 'en'
    
    # Check for Gujarati script (U+0A80 to U+0AFF)
    if re.search(r'[\u0A80-\u0AFF]', text):
        return 'gu'
    
    # Check for Hindi/Devanagari script (U+0900 to U+097F)
    if re.search(r'[\u0900-\u097F]', text):
        return 'hi'
    
    # Default to English
    return 'en'

def get_language_instruction(lang):
    """Get language-specific instruction for AI prompts"""
    instructions = {
        'en': "Answer in English.",
        'hi': "Answer in Hindi (हिंदी में उत्तर दें). Use Devanagari script.",
        'gu': "Answer in Gujarati (ગુજરાતીમાં જવાબ આપો). Use Gujarati script."
    }
    return instructions.get(lang, instructions['en'])

def get_language_response_templates(lang):
    """Get language-specific response templates"""
    templates = {
        'en': {
            'contextless': "I need a little more detail. What specific topic would you like me to explain more about? (e.g., 'Explain more about age limits')",
            'recommendations': ["Who can donate blood?", "What are the risks?", "Locations near me"]
        },
        'hi': {
            'contextless': "मुझे थोड़ा और विवरण चाहिए। आप किस विशिष्ट विषय के बारे में अधिक जानना चाहेंगे? (उदाहरण: 'उम्र सीमा के बारे में अधिक बताएं')",
            'recommendations': ["रक्तदान कौन कर सकता है?", "जोखिम क्या हैं?", "मेरे पास स्थान"]
        },
        'gu': {
            'contextless': "મને થોડી વધુ વિગતો જોઈએ છે. તમે કયા ચોક્કસ વિષય વિશે વધુ સમજાવવા માંગો છો? (ઉદાહરણ: 'ઉંમર મર્યાદા વિશે વધુ સમજાવો')",
            'recommendations': ["રક્તદાન કોણ કરી શકે છે?", "જોખમો શું છે?", "મારી નજીકના સ્થાનો"]
        }
    }
    return templates.get(lang, templates['en'])

# Knowledge base for common blood donation questions
BLOOD_DONATION_KB = {
    'en': {
        'benefits': "Blood donation has several benefits: 1) It helps save lives, 2) Reduces risk of heart disease, 3) Burns calories (about 650 per donation), 4) Free health checkup, 5) Reduces iron overload, 6) Stimulates production of new blood cells. Regular donors often report feeling good about helping others.",
        'side effects': "Blood donation is generally safe with minimal side effects. Common temporary effects include: slight dizziness, bruising at needle site, mild fatigue. These usually resolve within 24 hours. Serious complications are extremely rare. You should feel normal within a few hours after donation.",
        'who can donate': "To donate blood, you must: be 18-65 years old, weigh at least 50 kg, be in good health, have hemoglobin levels of at least 12.5 g/dL (females) or 13.5 g/dL (males), not have any infectious diseases, and wait appropriate intervals between donations (56 days for whole blood).",
        'age limit': "The age limit for blood donation is 18 to 65 years. Donors must be at least 18 years old and not older than 65 years. Some countries may have slightly different age requirements.",
        'weight requirement': "The minimum weight requirement for blood donation is 50 kg (110 pounds). This ensures the donor's body can safely handle the blood loss during donation.",
        'how often': "You can donate whole blood every 56 days (approximately 8 weeks). For platelets, you can donate more frequently - every 7 days, up to 24 times per year. Regular donors help maintain a stable blood supply.",
        'process': "The blood donation process takes about 10-15 minutes: 1) Registration and health screening, 2) Mini physical exam (blood pressure, temperature, hemoglobin check), 3) Blood collection (about 450ml), 4) Rest and refreshments. The entire visit takes about 45-60 minutes including paperwork and recovery time."
    },
    'hi': {
        'benefits': "रक्तदान के कई लाभ हैं: 1) यह जीवन बचाने में मदद करता है, 2) हृदय रोग का जोखिम कम करता है, 3) कैलोरी जलाता है (प्रति दान लगभग 650), 4) मुफ्त स्वास्थ्य जांच, 5) आयरन अधिकता कम करता है, 6) नई रक्त कोशिकाओं के उत्पादन को उत्तेजित करता है। नियमित दाता अक्सर दूसरों की मदद करने के बारे में अच्छा महसूस करने की रिपोर्ट करते हैं।",
        'side effects': "रक्तदान आमतौर पर न्यूनतम दुष्प्रभावों के साथ सुरक्षित है। सामान्य अस्थायी प्रभावों में शामिल हैं: हल्का चक्कर आना, सुई स्थल पर चोट लगना, हल्की थकान। ये आमतौर पर 24 घंटे के भीतर ठीक हो जाते हैं। गंभीर जटिलताएं अत्यंत दुर्लभ हैं। दान के कुछ घंटे बाद आपको सामान्य महसूस करना चाहिए।",
        'who can donate': "रक्तदान करने के लिए, आपको होना चाहिए: 18-65 वर्ष की आयु, कम से कम 50 किग्रा वजन, अच्छे स्वास्थ्य में, हीमोग्लोबिन स्तर कम से कम 12.5 g/dL (महिलाएं) या 13.5 g/dL (पुरुष), कोई संक्रामक रोग नहीं, और दान के बीच उचित अंतराल (पूरे रक्त के लिए 56 दिन)।",
        'age limit': "रक्तदान के लिए आयु सीमा 18 से 65 वर्ष है। दाताओं की आयु कम से कम 18 वर्ष और 65 वर्ष से अधिक नहीं होनी चाहिए। कुछ देशों में थोड़ी अलग आयु आवश्यकताएं हो सकती हैं।",
        'weight requirement': "रक्तदान के लिए न्यूनतम वजन आवश्यकता 50 किग्रा (110 पाउंड) है। यह सुनिश्चित करता है कि दाता का शरीर दान के दौरान रक्त हानि को सुरक्षित रूप से संभाल सकता है।",
        'how often': "आप हर 56 दिनों (लगभग 8 सप्ताह) में पूरा रक्त दान कर सकते हैं। प्लेटलेट्स के लिए, आप अधिक बार दान कर सकते हैं - हर 7 दिन, प्रति वर्ष 24 बार तक। नियमित दाता स्थिर रक्त आपूर्ति बनाए रखने में मदद करते हैं।",
        'process': "रक्तदान प्रक्रिया में लगभग 10-15 मिनट लगते हैं: 1) पंजीकरण और स्वास्थ्य जांच, 2) मिनी शारीरिक परीक्षा (रक्तचाप, तापमान, हीमोग्लोबिन जांच), 3) रक्त संग्रह (लगभग 450ml), 4) आराम और ताज़गी। पूरी यात्रा में कागजी कार्रवाई और रिकवरी समय सहित लगभग 45-60 मिनट लगते हैं।"
    },
    'gu': {
        'benefits': "રક્તદાનના ઘણા ફાયદા છે: 1) તે જીવન બચાવવામાં મદદ કરે છે, 2) હૃદય રોગનું જોખમ ઘટાડે છે, 3) કેલરી બળાવે છે (પ્રતિ દાન લગભગ 650), 4) મફત આરોગ્ય તપાસ, 5) આયર્ન ઓવરલોડ ઘટાડે છે, 6) નવી રક્ત કોશિકાઓના ઉત્પાદનને ઉત્તેજિત કરે છે. નિયમિત દાતાઓ ઘણીવાર અન્યોને મદદ કરવા વિશે સારું લાગવાની જાણ કરે છે.",
        'side effects': "રક્તદાન સામાન્ય રીતે ઓછામાં ઓછા આડઅસરો સાથે સુરક્ષિત છે. સામાન્ય અસ્થાયી અસરોમાં શામેલ છે: થોડું ચક્કર આવવું, સોય સ્થળે ચામડી પર લાલ ચિહ્ન, હળવી થાક. આ સામાન્ય રીતે 24 કલાકમાં ઠીક થઈ જાય છે. ગંભીર જટિલતાઓ અત્યંત દુર્લભ છે. દાન પછી થોડા કલાકોમાં તમે સામાન્ય લાગવું જોઈએ.",
        'who can donate': "રક્તદાન કરવા માટે, તમારે હોવું જોઈએ: 18-65 વર્ષની ઉંમર, ઓછામાં ઓછું 50 કિગ્રા વજન, સારા આરોગ્યમાં, હીમોગ્લોબિન સ્તર ઓછામાં ઓછું 12.5 g/dL (સ્ત્રીઓ) અથવા 13.5 g/dL (પુરુષો), કોઈ સંક્રામક રોગ નહીં, અને દાન વચ્ચે યોગ્ય અંતરાલ (સંપૂર્ણ રક્ત માટે 56 દિવસ).",
        'age limit': "રક્તદાન માટે ઉંમર મર્યાદા 18 થી 65 વર્ષ છે. દાતાઓની ઉંમર ઓછામાં ઓછી 18 વર્ષ અને 65 વર્ષથી વધુ નહીં હોવી જોઈએ. કેટલાક દેશોમાં થોડી અલગ ઉંમરની આવશ્યકતાઓ હોઈ શકે છે.",
        'weight requirement': "રક્તદાન માટે ન્યૂનતમ વજન આવશ્યકતા 50 કિગ્રા (110 પાઉન્ડ) છે. આ ખાતરી કરે છે કે દાતાનું શરીર દાન દરમિયાન રક્ત હાનિને સુરક્ષિત રીતે સંભાળી શકે છે.",
        'how often': "તમે દર 56 દિવસ (આશરે 8 અઠવાડિયા) માં સંપૂર્ણ રક્ત દાન કરી શકો છો. પ્લેટલેટ્સ માટે, તમે વધુ વારંવાર દાન કરી શકો છો - દર 7 દિવસ, વર્ષ દીઠ 24 વખત સુધી. નિયમિત દાતાઓ સ્થિર રક્ત પુરવઠો જાળવવામાં મદદ કરે છે.",
        'process': "રક્તદાન પ્રક્રિયામાં આશરે 10-15 મિનિટ લાગે છે: 1) નોંધણી અને આરોગ્ય સ્ક્રીનિંગ, 2) મિની શારીરિક પરીક્ષા (રક્તચાપ, તાપમાન, હીમોગ્લોબિન તપાસ), 3) રક્ત સંગ્રહ (આશરે 450ml), 4) આરામ અને તાજગી. સંપૂર્ણ મુલાકાતમાં કાગળકામ અને પુનઃપ્રાપ્તિ સમય સહિત આશરે 45-60 મિનિટ લાગે છે."
    }
}

def get_knowledge_base_answer(question, lang='en'):
    """Check knowledge base for common questions"""
    question_lower = question.lower().strip()
    
    # English keywords
    if lang == 'en':
        if any(word in question_lower for word in ['benefit', 'advantage', 'good', 'help']):
            return BLOOD_DONATION_KB[lang]['benefits']
        elif any(word in question_lower for word in ['side effect', 'risk', 'danger', 'harm', 'bad']):
            return BLOOD_DONATION_KB[lang]['side effects']
        elif any(word in question_lower for word in ['who can', 'eligible', 'qualify', 'requirement']):
            return BLOOD_DONATION_KB[lang]['who can donate']
        elif any(word in question_lower for word in ['age', 'old', 'young']):
            return BLOOD_DONATION_KB[lang]['age limit']
        elif any(word in question_lower for word in ['weight', 'kg', 'pound']):
            return BLOOD_DONATION_KB[lang]['weight requirement']
        elif any(word in question_lower for word in ['how often', 'frequency', 'time between']):
            return BLOOD_DONATION_KB[lang]['how often']
        elif any(word in question_lower for word in ['process', 'procedure', 'step', 'how to']):
            return BLOOD_DONATION_KB[lang]['process']
    
    # Hindi keywords
    elif lang == 'hi':
        if any(word in question_lower for word in ['लाभ', 'फायदा', 'अच्छा']):
            return BLOOD_DONATION_KB[lang]['benefits']
        elif any(word in question_lower for word in ['दुष्प्रभाव', 'जोखिम', 'नुकसान', 'बुरा']):
            return BLOOD_DONATION_KB[lang]['side effects']
        elif any(word in question_lower for word in ['कौन कर सकता', 'योग्य', 'आवश्यकता']):
            return BLOOD_DONATION_KB[lang]['who can donate']
        elif any(word in question_lower for word in ['उम्र', 'सीमा']):
            return BLOOD_DONATION_KB[lang]['age limit']
        elif any(word in question_lower for word in ['वजन', 'किलो']):
            return BLOOD_DONATION_KB[lang]['weight requirement']
        elif any(word in question_lower for word in ['कितनी बार', 'कितने दिन', 'अंतराल']):
            return BLOOD_DONATION_KB[lang]['how often']
        elif any(word in question_lower for word in ['प्रक्रिया', 'तरीका', 'कैसे']):
            return BLOOD_DONATION_KB[lang]['process']
    
    # Gujarati keywords
    elif lang == 'gu':
        if any(word in question_lower for word in ['લાભ', 'ફાયદો', 'સારું']):
            return BLOOD_DONATION_KB[lang]['benefits']
        elif any(word in question_lower for word in ['આડઅસર', 'જોખમ', 'નુકસાન', 'ખરાબ']):
            return BLOOD_DONATION_KB[lang]['side effects']
        elif any(word in question_lower for word in ['કોણ કરી શકે', 'યોગ્ય', 'જરૂરિયાત']):
            return BLOOD_DONATION_KB[lang]['who can donate']
        elif any(word in question_lower for word in ['ઉંમર', 'મર્યાદા']):
            return BLOOD_DONATION_KB[lang]['age limit']
        elif any(word in question_lower for word in ['વજન', 'કિલો']):
            return BLOOD_DONATION_KB[lang]['weight requirement']
        elif any(word in question_lower for word in ['કેટલી વાર', 'કેટલા દિવસ', 'અંતરાલ']):
            return BLOOD_DONATION_KB[lang]['how often']
        elif any(word in question_lower for word in ['પ્રક્રિયા', 'રીત', 'કેવી રીતે']):
            return BLOOD_DONATION_KB[lang]['process']
    
    return None

def load_model_if_needed(model_name=None):
    """Load AI model with caching support"""
    global MODEL_CACHE
    
    if model_name is None:
        model_name = DEFAULT_MODEL
    
    # Validate model name
    if model_name not in AVAILABLE_MODELS:
        model_name = DEFAULT_MODEL
    
    # Check if model is already loaded
    if model_name in MODEL_CACHE:
        print(f"Using cached model: {model_name}")
        return MODEL_CACHE[model_name]
    
    print(f"Loading Generative Model: {model_name}...")
    try:
        generator = pipeline("text2text-generation", model=model_name, max_length=512)
        MODEL_CACHE[model_name] = generator
        return generator
    except Exception as e:
        print(f"Error loading model {model_name}: {e}")
        # Fallback to default if available
        if model_name != DEFAULT_MODEL and DEFAULT_MODEL in MODEL_CACHE:
            print(f"Falling back to default model: {DEFAULT_MODEL}")
            return MODEL_CACHE[DEFAULT_MODEL]
        raise e

def generate_ai_recommendations(topic_text, generator, lang='en'):
    """Generates 3 SPECIFIC follow-up questions based on the answer text."""
    try:
        short_context = topic_text[:400]
        
        # Language-specific prompts
        prompts = {
            'en': f"""
        Read this medical text: "{short_context}"
        
        Task: Create 3 specific follow-up questions a user might ask. 
        Rules:
        1. Questions must be about the text.
        2. Do NOT use generic phrases like "Tell me more" or "Explain".
        3. Make them complete questions.
        4. Answer in English.
        
        Output Format: Q1? Q2? Q3?
        """,
            'hi': f"""
        इस चिकित्सा पाठ को पढ़ें: "{short_context}"
        
        कार्य: उपयोगकर्ता द्वारा पूछे जा सकने वाले 3 विशिष्ट अनुवर्ती प्रश्न बनाएं।
        नियम:
        1. प्रश्न पाठ के बारे में होने चाहिए।
        2. "और बताओ" या "समझाओ" जैसे सामान्य वाक्यांश का उपयोग न करें।
        3. उन्हें पूर्ण प्रश्न बनाएं।
        4. हिंदी में उत्तर दें।
        
        आउटपुट प्रारूप: Q1? Q2? Q3?
        """,
            'gu': f"""
        આ તબીબી ટેક્સ્ટ વાંચો: "{short_context}"
        
        કાર્ય: વપરાશકર્તા પૂછી શકે તેવા 3 ચોક્કસ અનુવર્તી પ્રશ્નો બનાવો.
        નિયમો:
        1. પ્રશ્નો ટેક્સ્ટ વિશે હોવા જોઈએ.
        2. "વધુ કહો" અથવા "સમજાવો" જેવા સામાન્ય શબ્દસમૂહનો ઉપયોગ ન કરો.
        3. તેમને સંપૂર્ણ પ્રશ્નો બનાવો.
        4. ગુજરાતીમાં જવાબ આપો.
        
        આઉટપુટ ફોર્મેટ: Q1? Q2? Q3?
        """
        }
        
        prompt = prompts.get(lang, prompts['en'])
        results = generator(prompt, max_length=100, do_sample=True, temperature=0.95)
        raw_text = results[0]['generated_text'].strip()
        
        parts = raw_text.split('?')
        clean_recs = []
        for p in parts:
            clean_q = re.sub(r'^[0-9\.\-\s]+', '', p).strip()
            if len(clean_q) > 10:
                # Language-specific generic phrase checks
                generic_phrases = {
                    'en': ["tell me more", "explain"],
                    'hi': ["और बताओ", "समझाओ"],
                    'gu': ["વધુ કહો", "સમજાવો"]
                }
                phrases = generic_phrases.get(lang, generic_phrases['en'])
                if not any(phrase in clean_q.lower() for phrase in phrases):
                    clean_recs.append(clean_q + "?")
        
        clean_recs = list(set(clean_recs))
        
        # Language-specific fallback recommendations
        fallbacks = {
            'en': ["What are the benefits?", "Are there any side effects?", "Who can donate?"],
            'hi': ["लाभ क्या हैं?", "क्या कोई दुष्प्रभाव हैं?", "रक्तदान कौन कर सकता है?"],
            'gu': ["લાભો શું છે?", "શું કોઈ આડઅસરો છે?", "રક્તદાન કોણ કરી શકે છે?"]
        }
        
        if len(clean_recs) < 3:
            fallback = fallbacks.get(lang, fallbacks['en'])
            clean_recs.extend(fallback)
            
        return clean_recs[:3]
    except Exception as e:
        print(f"Rec Gen Error: {e}")
        # Language-specific default recommendations
        defaults = {
            'en': ["Who can donate?", "Is donation safe?", "How often can I donate?"],
            'hi': ["रक्तदान कौन कर सकता है?", "क्या दान सुरक्षित है?", "मैं कितनी बार दान कर सकता हूं?"],
            'gu': ["રક્તદાન કોણ કરી શકે છે?", "શું દાન સુરક્ષિત છે?", "હું કેટલી વાર દાન કરી શકું?"]
        }
        return defaults.get(lang, defaults['en'])

def get_blood_data_dynamic(city):
    banks = []
    camps = []
    
    if not TAVILY_API_KEY: return [], []

    try:
        query = f"Official blood banks, donation centers, and upcoming camps in {city}, Gujarat"
        response = TAVILY_CLIENT.search(query=query, search_depth="basic", max_results=7)

        for result in response['results']:
            title = result['title'].lower()
            if 'bank' in title or 'center' in title or 'hospital' in title:
                banks.append({
                    "name": result['title'],
                    "snippet": result['content'],
                    "source_link": result['url'],
                    "type": "Center"
                })
            elif 'camp' in title or 'drive' in title or 'event' in title:
                camps.append({
                    "name": result['title'],
                    "snippet": result['content'],
                    "date_status": "Event",
                    "source_link": result['url'],
                })
    except Exception:
        pass 

    if not camps:
        camps.append({
            "name": "Official State Schedule",
            "snippet": "Check official government listings for upcoming drives.",
            "date_status": "Resource",
            "source_link": IRCS_GUJ_CAMPS_URL
        })
    return banks, camps

# --- 3. VIEWS ---
def home(request): return render(request, 'assistant/home.html')
def chat_page(request): return render(request, 'assistant/chat.html')
def get_response(request): return JsonResponse({"msg": "Use POST /api/chat"})

@csrf_exempt
def get_models(request):
    """Get available AI models"""
    return JsonResponse({
        'models': AVAILABLE_MODELS,
        'default': DEFAULT_MODEL
    })

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chat')
    else: form = UserCreationForm()
    return render(request, 'assistant/register.html', {'form': form})

# --- 4. REPORT GENERATION HELPERS ---

# Comprehensive eligibility questions for blood donation
ELIGIBILITY_QUESTIONS = [
    "What is your full name?",
    "What is your age?",
    "What is your weight? (in kg)",
    "What is your gender? (Male/Female/Other)",
    "What is your blood group/type? (e.g., A+, B+, O+, AB+)",
    "Do you have diabetes? (Yes/No)",
    "Do you have anemia or low hemoglobin? (Yes/No)",
    "What is your hemoglobin level? (if known)",
    "What is your blood pressure? (Normal range: 90/60 to 120/80 mmHg)",
    "Did you previously suffer from COVID-19? (Yes/No)",
    "Do you have any allergies? (Yes/No)",
    "If yes, please specify your allergies:",
    "Are you currently taking any medications? (Yes/No)",
    "If yes, please specify the medications:",
    "Have you donated blood before? (Yes/No)",
    "If yes, when was your last donation? (date or approximate time)",
    "Do you have any chronic diseases? (Yes/No)",
    "If yes, please specify:",
    "Do you have any infectious diseases? (HIV, Hepatitis, etc.) (Yes/No)",
    "If yes, please specify:",
    "Have you had any tattoos or piercings in the last 6 months? (Yes/No)",
    "If yes, when did you get them?",
    "Are you currently pregnant? (Yes/No - for females)",
    "Are you currently breastfeeding? (Yes/No - for females)",
    "Have you had any surgery in the last 6 months? (Yes/No)",
    "If yes, please specify:"
]

def get_or_create_profile(request):
    """Get or create user health profile"""
    session_id = request.session.get('health_profile_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session['health_profile_id'] = session_id
    
    profile, created = UserHealthProfile.objects.get_or_create(
        session_id=session_id,
        defaults={'user': request.user if request.user.is_authenticated else None}
    )
    return profile

def save_answer_to_profile(profile, question_num, answer):
    """Save answer to profile based on question number"""
    answer_lower = answer.lower().strip()
    
    if question_num == 1:  # Name
        profile.name = answer
    elif question_num == 2:  # Age
        try:
            age_match = re.search(r'\d+', answer)
            if age_match:
                profile.age = int(age_match.group())
        except:
            pass
    elif question_num == 3:  # Weight
        try:
            weight_match = re.search(r'\d+\.?\d*', answer)
            if weight_match:
                profile.weight = float(weight_match.group())
        except:
            pass
    elif question_num == 4:  # Gender
        profile.gender = answer
    elif question_num == 5:  # Blood Category
        blood_match = re.search(r'\b([ABO][+-]?|AB[+-]?)\b', answer.upper())
        if blood_match:
            profile.blood_category = blood_match.group(1)
        else:
            profile.blood_category = answer
    elif question_num == 6:  # Diabetes
        profile.has_diabetes = answer_lower in ['yes', 'y', 'true', '1', 'have', 'suffering']
    elif question_num == 7:  # Anemia
        profile.has_anemia = answer_lower in ['yes', 'y', 'true', '1', 'have', 'suffering']
    elif question_num == 8:  # Hemoglobin
        profile.hemoglobin_level = answer
    elif question_num == 9:  # Blood Pressure
        profile.blood_pressure = answer
    elif question_num == 10:  # Corona
        profile.had_corona = answer_lower in ['yes', 'y', 'true', '1', 'had', 'suffered']
    elif question_num == 11:  # Allergies
        profile.has_allergies = answer_lower in ['yes', 'y', 'true', '1', 'have']
    elif question_num == 12:  # Allergies details
        profile.allergies_details = answer
    elif question_num == 13:  # Medications
        profile.taking_medications = answer_lower in ['yes', 'y', 'true', '1', 'taking', 'on']
    elif question_num == 14:  # Medications details
        profile.medications_details = answer
    elif question_num == 15:  # Donated before
        profile.donated_before = answer_lower in ['yes', 'y', 'true', '1', 'have', 'donated']
    elif question_num == 16:  # Last donation
        profile.last_donation_date = answer
    elif question_num == 17:  # Chronic diseases
        profile.has_chronic_diseases = answer_lower in ['yes', 'y', 'true', '1', 'have']
    elif question_num == 18:  # Chronic diseases details
        profile.chronic_diseases_details = answer
    elif question_num == 19:  # Infectious diseases
        profile.has_infectious_disease = answer_lower in ['yes', 'y', 'true', '1', 'have']
    elif question_num == 20:  # Infectious diseases details
        profile.infectious_disease_details = answer
    elif question_num == 21:  # Tattoo/Piercing
        profile.has_tattoo_piercing = answer_lower in ['yes', 'y', 'true', '1', 'have', 'got']
    elif question_num == 22:  # Tattoo/Piercing date
        profile.tattoo_piercing_date = answer
    elif question_num == 23:  # Pregnant
        profile.is_pregnant = answer_lower in ['yes', 'y', 'true', '1', 'am', 'pregnant']
    elif question_num == 24:  # Breastfeeding
        profile.is_breastfeeding = answer_lower in ['yes', 'y', 'true', '1', 'am', 'breastfeeding']
    elif question_num == 25:  # Surgery
        profile.has_surgery_recently = answer_lower in ['yes', 'y', 'true', '1', 'had', 'surgery']
    elif question_num == 26:  # Surgery details
        profile.surgery_details = answer
        profile.completed = True
    
    profile.save()


def is_uncertain_answer(answer: str) -> bool:
    """
    Returns True if the user answer clearly indicates uncertainty / refusal,
    e.g. 'don't know', 'idk', 'na', 'not sure', etc.
    """
    if not answer:
        return True
    text = answer.strip().lower()
    uncertain_phrases = [
        "dont know", "don't know", "do not know", "idk", "dk",
        "no idea", "not sure", "unsure", "n/a", "na", "none", "nothing"
    ]
    # single very short tokens like "?" or "-" are also treated as invalid
    if len(text) <= 1:
        return True
    return any(p in text for p in uncertain_phrases)


def is_valid_blood_pressure(answer: str) -> bool:
    """
    Basic validation for blood pressure: require at least one digit.
    Accept formats like '120/80', '110 70', '120-80', or even single numbers.
    Pure text without digits (e.g. 'normal', 'high') is rejected.
    """
    if not answer:
        return False
    text = answer.strip()
    return any(ch.isdigit() for ch in text)


def validate_answer(question_num: int, answer: str, profile: UserHealthProfile):
    """
    Per-question validation.
    Returns (is_valid: bool, error_message_html: str | None).
    If not valid, we DO NOT advance to next question and re-ask the same one.
    """
    same_question = ELIGIBILITY_QUESTIONS[question_num - 1]
    text = (answer or "").strip().lower()

    # Normalize simple yes/no patterns
    yes_values = {"yes", "y", "true", "1"}
    no_values = {"no", "n", "false", "0"}

    # Helper to check and fail for strictly-yes-no questions
    def require_yes_no(extra_hint: str = ""):
        if text in yes_values or text in no_values:
            return True, None
        hint = "Please answer with <b>Yes</b> or <b>No</b> only."
        if extra_hint:
            hint += f" {extra_hint}"
        return False, f"{hint}<br><br><b>{same_question}</b>"

    # Q2: Age – must be a number
    if question_num == 2:
        if not re.search(r"\d+", text):
            return False, f"Please enter your age as a number (for example: 25). Text descriptions are not accepted.<br><br><b>{same_question}</b>"
        return True, None

    # Q3: Weight – must be a number
    if question_num == 3:
        if not re.search(r"\d+\.?\d*", text):
            return False, f"Please enter your weight in kilograms using numbers (for example: 60 or 72.5). Text descriptions are not accepted.<br><br><b>{same_question}</b>"
        return True, None

    # Q4: Gender – restrict to known options
    if question_num == 4:
        valid_genders = {"male", "female", "other", "m", "f", "o"}
        if text not in valid_genders:
            return False, f"Please answer gender as <b>Male</b>, <b>Female</b>, or <b>Other</b> (you can also use M/F/O).<br><br><b>{same_question}</b>"
        return True, None

    # Q5: Blood group – restrict to known blood types
    if question_num == 5:
        # Accept common patterns: A, A+, A-, B, B+, B-, AB, AB+, AB-, O, O+, O-
        normalized = text.replace(" ", "").upper()
        valid_blood_groups = {
            "A", "A+", "A-",
            "B", "B+", "B-",
            "AB", "AB+", "AB-",
            "O", "O+", "O-",
        }
        if normalized not in valid_blood_groups:
            return False, (
                "Please enter a valid blood group like <b>A+</b>, <b>A-</b>, <b>B+</b>, <b>B-</b>, "
                "<b>AB+</b>, <b>AB-</b>, <b>O+</b>, or <b>O-</b>.<br><br>"
                f"<b>{same_question}</b>"
            )
        return True, None

    # Yes/No questions only
    yes_no_questions = {6, 7, 10, 11, 13, 15, 17, 19, 21, 23, 24, 25}
    if question_num in yes_no_questions:
        return require_yes_no()

    # All other questions: current generic rules (uncertain answer check) are enough
    return True, None

def check_eligibility(profile):
    """Check blood donation eligibility based on profile"""
    reasons = []
    eligible = True
    
    # Age check (18-65 years)
    if profile.age:
        if profile.age < 18:
            eligible = False
            reasons.append("You must be at least 18 years old to donate blood.")
        elif profile.age > 65:
            eligible = False
            reasons.append("Maximum age for blood donation is 65 years.")
    
    # Weight check (minimum 50 kg)
    if profile.weight:
        if profile.weight < 50:
            eligible = False
            reasons.append("Minimum weight requirement is 50 kg for blood donation.")
    
    # Diabetes check
    if profile.has_diabetes:
        eligible = False
        reasons.append("Individuals with uncontrolled diabetes are not eligible to donate.")
    
    # Anemia check
    if profile.has_anemia:
        eligible = False
        reasons.append("Individuals with anemia or low hemoglobin are not eligible.")
    
    # Hemoglobin check (minimum 12.5 g/dL for females, 13.5 g/dL for males)
    if profile.hemoglobin_level:
        try:
            hb_match = re.search(r'(\d+\.?\d*)', profile.hemoglobin_level)
            if hb_match:
                hb_level = float(hb_match.group(1))
                if profile.gender and 'female' in profile.gender.lower():
                    if hb_level < 12.5:
                        eligible = False
                        reasons.append("Hemoglobin level should be at least 12.5 g/dL for females.")
                else:
                    if hb_level < 13.5:
                        eligible = False
                        reasons.append("Hemoglobin level should be at least 13.5 g/dL for males.")
        except:
            pass
    
    # Infectious diseases
    if profile.has_infectious_disease:
        eligible = False
        reasons.append("Individuals with infectious diseases (HIV, Hepatitis, etc.) are not eligible.")
    
    # Pregnancy/Breastfeeding
    if profile.is_pregnant:
        eligible = False
        reasons.append("Pregnant women are not eligible to donate blood.")
    if profile.is_breastfeeding:
        eligible = False
        reasons.append("Breastfeeding women are not eligible to donate blood.")
    
    # Recent tattoo/piercing (6 months)
    if profile.has_tattoo_piercing:
        eligible = False
        reasons.append("You must wait at least 6 months after getting a tattoo or piercing before donating.")
    
    # Recent surgery (6 months)
    if profile.has_surgery_recently:
        eligible = False
        reasons.append("You must wait at least 6 months after surgery before donating blood.")
    
    # COVID-19 (usually 28 days after recovery)
    if profile.had_corona:
        eligible = False
        reasons.append("You must wait at least 28 days after recovery from COVID-19 before donating blood.")
    
    # Medications (depends on type)
    if profile.taking_medications:
        reasons.append("Note: Some medications may affect eligibility. Please consult with a medical professional.")
    
    # Update profile
    if eligible:
        profile.eligibility_status = "Eligible"
        if not reasons:
            reasons.append("You appear to be eligible for blood donation based on the information provided.")
    else:
        profile.eligibility_status = "Not Eligible"
    
    profile.eligibility_reasons = "\n".join(reasons)
    profile.save()
    
    return eligible, reasons

# --- 5. CHAT API (No question flow) ---
@csrf_exempt
def chat_api(request):
    """Chat API - only answers questions, no question flow"""
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            question = body.get('question', '').strip()
            model_name = body.get('model', DEFAULT_MODEL)
            
            if not question: return JsonResponse({'error': 'Empty'}, status=400)

            # Detect language of the question
            detected_lang = detect_language(question)
            lang_instruction = get_language_instruction(detected_lang)
            lang_templates = get_language_response_templates(detected_lang)
            
            # Load the selected model
            generator = load_model_if_needed(model_name)
            
            q_lower = question.lower()
            intent = "UNKNOWN"

            # Check for "Contextless" inputs (language-aware)
            contextless_phrases = {
                'en': ["tell me more", "explain", "explain more", "yes", "no"],
                'hi': ["और बताओ", "समझाओ", "हाँ", "नहीं", "हां"],
                'gu': ["વધુ કહો", "સમજાવો", "હા", "ના"]
            }
            
            is_contextless = len(question) < 5
            if not is_contextless:
                phrases = contextless_phrases.get(detected_lang, contextless_phrases['en'])
                is_contextless = any(phrase in q_lower for phrase in phrases)
            
            if is_contextless:
                return JsonResponse({
                    'answer': lang_templates['contextless'], 
                    'source': 'System', 
                    'confidence': 1.0,
                    'recommendations': lang_templates['recommendations'],
                    'detected_language': detected_lang
                })

            # STRICT CONCEPT FILTER (language-aware keywords)
            concept_keywords = {
                'en': ["what", "why", "how", "who", "risk", "benefit", "safe", "eligible", 
                       "age", "limit", "weight", "process", "procedure", "explain", "define", 
                       "can i", "should i", "maximum", "minimum"],
                'hi': ["क्या", "क्यों", "कैसे", "कौन", "जोखिम", "लाभ", "सुरक्षित", "योग्य",
                       "उम्र", "सीमा", "वजन", "प्रक्रिया", "समझाओ", "परिभाषा", "कर सकता", 
                       "अधिकतम", "न्यूनतम"],
                'gu': ["શું", "શા માટે", "કેવી રીતે", "કોણ", "જોખમ", "લાભ", "સુરક્ષિત", "યોગ્ય",
                       "ઉંમર", "મર્યાદા", "વજન", "પ્રક્રિયા", "સમજાવો", "વ્યાખ્યા", "કરી શકું",
                       "મહત્તમ", "ન્યૂનતમ"]
            }
            
            keywords = concept_keywords.get(detected_lang, concept_keywords['en'])
            if any(word in q_lower for word in keywords):
                intent = "EXPLAIN"
            
            # AI ROUTER (language-aware)
            if intent == "UNKNOWN":
                router_examples = {
                    'en': [
                        '"Find blood bank" -> SEARCH',
                        '"Locations in Surat" -> SEARCH',
                        '"Donate near me" -> SEARCH',
                        '"Blood donation camps" -> SEARCH',
                        '"What is hemoglobin?" -> EXPLAIN',
                        '"Max age for donation" -> EXPLAIN'
                    ],
                    'hi': [
                        '"रक्त बैंक खोजें" -> SEARCH',
                        '"सूरत में स्थान" -> SEARCH',
                        '"मेरे पास दान करें" -> SEARCH',
                        '"रक्तदान शिविर" -> SEARCH',
                        '"हीमोग्लोबिन क्या है?" -> EXPLAIN',
                        '"दान की अधिकतम उम्र" -> EXPLAIN'
                    ],
                    'gu': [
                        '"રક્ત બેંક શોધો" -> SEARCH',
                        '"સુરતમાં સ્થાનો" -> SEARCH',
                        '"મારી નજીક દાન કરો" -> SEARCH',
                        '"રક્તદાન શિબિર" -> SEARCH',
                        '"હીમોગ્લોબિન શું છે?" -> EXPLAIN',
                        '"દાન માટે મહત્તમ ઉંમર" -> EXPLAIN'
                    ]
                }
                
                examples = router_examples.get(detected_lang, router_examples['en'])
                router_prompt = f"""
                Classify user intent.
                {chr(10).join(examples)}
                
                Question: "{question}"
                Answer (SEARCH or EXPLAIN):
                """
                router_out = generator(router_prompt, max_length=5, do_sample=False)
                intent = router_out[0]['generated_text'].strip().upper()
            
            print(f"User: {question} | Language: {detected_lang} | Intent: {intent} | Model: {model_name}")

            # PATH A: SEARCH
            if "SEARCH" in intent:
                city = "Ahmedabad"
                city_keywords = {
                    'en': {'surat': 'Surat', 'vadodara': 'Vadodara'},
                    'hi': {'सूरत': 'Surat', 'वडोदरा': 'Vadodara'},
                    'gu': {'સુરત': 'Surat', 'વડોદરા': 'Vadodara'}
                }
                
                keywords = city_keywords.get(detected_lang, city_keywords['en'])
                for keyword, city_name in keywords.items():
                    if keyword.lower() in q_lower:
                        city = city_name
                        break
                
                banks, camps = get_blood_data_dynamic(city)
                rec_context = f"Blood banks in {city}: " + (banks[0]['name'] if banks else "General info")
                recommendations = generate_ai_recommendations(rec_context, generator, detected_lang)

                # Language-specific labels
                labels = {
                    'en': {
                        'title': f'Latest locations in <b>{city.title()}</b>.',
                        'banks': '🏥 Blood Banks',
                        'camps': '📅 Camps',
                        'visit': 'Visit Link',
                        'details': 'Details'
                    },
                    'hi': {
                        'title': f'<b>{city.title()}</b> में नवीनतम स्थान।',
                        'banks': '🏥 रक्त बैंक',
                        'camps': '📅 शिविर',
                        'visit': 'लिंक देखें',
                        'details': 'विवरण'
                    },
                    'gu': {
                        'title': f'<b>{city.title()}</b> માં નવીનતમ સ્થાનો।',
                        'banks': '🏥 રક્ત બેંકો',
                        'camps': '📅 શિબિરો',
                        'visit': 'લિંક જુઓ',
                        'details': 'વિગતો'
                    }
                }
                
                lang_labels = labels.get(detected_lang, labels['en'])
                html = f"""<div class="space-y-4"><div class="text-sm text-gray-600 mb-2">{lang_labels['title']}</div>"""
                
                if banks:
                    html += f'<div class="font-bold text-gray-800 border-b pb-1 mb-2">{lang_labels["banks"]}</div>'
                    for i, b in enumerate(banks):
                        html += f'<div class="bg-white p-3 mb-2 border rounded shadow-sm"><b>{i+1}. {b["name"]}</b><br><span class="text-xs">{b["snippet"][:120]}...</span><br><a href="{b["source_link"]}" target="_blank" class="text-xs text-blue-600 underline">{lang_labels["visit"]}</a></div>'
                
                if camps:
                    html += f'<div class="font-bold text-gray-800 border-b pb-1 mt-4 mb-2">{lang_labels["camps"]}</div>'
                    for i, c in enumerate(camps):
                        html += f'<div class="bg-red-50 p-3 mb-2 border border-red-100 rounded"><b>{i+1}. {c["name"]}</b><br><span class="text-xs">{c["snippet"][:120]}...</span><br><a href="{c["source_link"]}" target="_blank" class="text-xs text-red-600 underline">{lang_labels["details"]}</a></div>'
                html += "</div>"
                
                return JsonResponse({
                    'answer': html,
                    'source': 'Tavily Search',
                    'confidence': 1.0,
                    'recommendations': recommendations,
                    'model_used': AVAILABLE_MODELS[model_name]['name'],
                    'detected_language': detected_lang
                })

            # PATH B: EXPLAIN
            else:
                # First, check knowledge base for common questions
                kb_answer = get_knowledge_base_answer(question, detected_lang)
                
                if kb_answer:
                    # Use knowledge base answer
                    answer_text = kb_answer
                    recommendations = generate_ai_recommendations(answer_text, generator, detected_lang)
                else:
                    # Use AI generation with improved prompts
                    explain_prompts = {
                        'en': f"""Answer this question about blood donation in English clearly and accurately.

Question: "{question}"

Answer in English:""",
                        'hi': f"""रक्तदान के बारे में इस प्रश्न का उत्तर हिंदी में स्पष्ट और सटीक रूप से दें।

प्रश्न: "{question}"

हिंदी में उत्तर दें:""",
                        'gu': f"""રક્તદાન વિશે આ પ્રશ્નનો જવાબ ગુજરાતીમાં સ્પષ્ટ અને સચોટ રીતે આપો.

પ્રશ્ન: "{question}"

ગુજરાતીમાં જવાબ આપો:"""
                    }
                    
                    # Use language-specific prompt
                    explain_prompt = explain_prompts.get(detected_lang, explain_prompts['en'])

                    res = generator(
                        explain_prompt,
                        max_length=512,
                        do_sample=True,
                        temperature=0.7,
                        top_p=0.9,
                        num_return_sequences=1
                    )

                    answer_text = res[0]['generated_text'].strip()
                    
                    # Clean up the answer - remove any prompt remnants
                    if detected_lang == 'hi':
                        # Remove common Hindi prompt artifacts
                        answer_text = re.sub(r'^(उत्तर|जवाब|Answer|answer|प्रश्न|Question)[:\s]*', '', answer_text, flags=re.IGNORECASE)
                        answer_text = re.sub(r'^[:\s]*', '', answer_text)
                    elif detected_lang == 'gu':
                        # Remove common Gujarati prompt artifacts
                        answer_text = re.sub(r'^(જવાબ|Answer|answer|પ્રશ્ન|Question)[:\s]*', '', answer_text, flags=re.IGNORECASE)
                        answer_text = re.sub(r'^[:\s]*', '', answer_text)
                    else:
                        # Remove common English prompt artifacts
                        answer_text = re.sub(r'^(Answer|answer|Question)[:\s]*', '', answer_text, flags=re.IGNORECASE)
                        answer_text = re.sub(r'^[:\s]*', '', answer_text)
                    
                    # If answer is still empty or too short, use knowledge base or fallback
                    if not answer_text or len(answer_text.strip()) < 10:
                        # Try to find a general answer from KB
                        if 'benefit' in question.lower() or 'लाभ' in question or 'લાભ' in question:
                            answer_text = BLOOD_DONATION_KB.get(detected_lang, BLOOD_DONATION_KB['en']).get('benefits', '')
                        elif 'side effect' in question.lower() or 'दुष्प्रभाव' in question or 'આડઅસર' in question:
                            answer_text = BLOOD_DONATION_KB.get(detected_lang, BLOOD_DONATION_KB['en']).get('side effects', '')
                        else:
                            fallback_answers = {
                                'en': "I understand your question about blood donation. Could you please provide more specific details so I can give you a more accurate answer?",
                                'hi': "मैं रक्तदान के बारे में आपके प्रश्न को समझता हूं। कृपया अधिक विशिष्ट विवरण प्रदान करें ताकि मैं आपको अधिक सटीक उत्तर दे सकूं?",
                                'gu': "હું રક્તદાન વિશે તમારો પ્રશ્ન સમજું છું. કૃપા કરીને વધુ ચોક્કસ વિગતો પ્રદાન કરો જેથી હું તમને વધુ સચોટ જવાબ આપી શકું?"
                            }
                            answer_text = fallback_answers.get(detected_lang, fallback_answers['en'])
                    
                    recommendations = generate_ai_recommendations(answer_text, generator, detected_lang)

                return JsonResponse({
                    'answer': answer_text,
                    'source': 'Generative AI',
                    'confidence': 1.0,
                    'recommendations': recommendations,
                    'model_used': AVAILABLE_MODELS[model_name]['name'],
                    'detected_language': detected_lang
                })

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method Not Allowed'}, status=405)

# --- 6. REPORT GENERATION API ---
@csrf_exempt
def report_api(request):
    """Report generation API - handles question flow and report generation"""
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            answer = body.get('answer', '').strip()
            
            # Check if we're in question flow
            question_flow_active = request.session.get('report_question_flow', False)
            current_question = request.session.get('report_current_question', 0)
            
            # If in question flow, handle the answer
            if question_flow_active and current_question > 0:
                profile = get_or_create_profile(request)

                # --- Validation: reject uncertain / bad answers and re-ask same question ---
                if is_uncertain_answer(answer):
                    same_question = ELIGIBILITY_QUESTIONS[current_question - 1]
                    return JsonResponse({
                        'answer': f"Please answer this question as accurately as you can. Answers like 'don't know' or 'not sure' are not allowed.<br><br><b>{same_question}</b>",
                        'in_question_flow': True,
                        'question_number': current_question,
                        'total_questions': len(ELIGIBILITY_QUESTIONS)
                    })

                # Per-question strict validation (Yes/No only, gender options, numeric age/weight, etc.)
                is_valid, error_msg = validate_answer(current_question, answer, profile)
                if not is_valid:
                    return JsonResponse({
                        'answer': error_msg,
                        'in_question_flow': True,
                        'question_number': current_question,
                        'total_questions': len(ELIGIBILITY_QUESTIONS)
                    })

                # Special validation for blood pressure question (Q9) – must contain numbers
                if current_question == 9 and not is_valid_blood_pressure(answer):
                    same_question = ELIGIBILITY_QUESTIONS[current_question - 1]
                    return JsonResponse({
                        'answer': f"Please enter your blood pressure using numbers (for example: 120/80). Normal range is 90/60 to 120/80 mmHg.<br><br><b>{same_question}</b>",
                        'in_question_flow': True,
                        'question_number': current_question,
                        'total_questions': len(ELIGIBILITY_QUESTIONS)
                    })

                save_answer_to_profile(profile, current_question, answer)

                # Move to next question
                current_question += 1

                # --- Conditional skipping logic ---
                # We loop in case multiple consecutive questions need to be skipped.
                while current_question <= len(ELIGIBILITY_QUESTIONS):
                    # Skip pregnancy/breastfeeding questions for males or other genders
                    if current_question == 23:  # Pregnancy
                        if profile.gender and 'male' in profile.gender.lower():
                            current_question += 1
                            continue
                    if current_question == 24:  # Breastfeeding
                        if profile.gender and 'male' in profile.gender.lower():
                            current_question += 1
                            continue

                    # Skip "If yes, specify..." questions when previous answer was effectively "No"
                    # Q11 -> Q12 (allergies)
                    if current_question == 12 and profile.has_allergies is False:
                        current_question += 1
                        continue
                    # Q13 -> Q14 (medications)
                    if current_question == 14 and profile.taking_medications is False:
                        current_question += 1
                        continue
                    # Q15 -> Q16 (donated before)
                    if current_question == 16 and profile.donated_before is False:
                        current_question += 1
                        continue
                    # Q17 -> Q18 (chronic diseases)
                    if current_question == 18 and profile.has_chronic_diseases is False:
                        current_question += 1
                        continue
                    # Q19 -> Q20 (infectious diseases)
                    if current_question == 20 and profile.has_infectious_disease is False:
                        current_question += 1
                        continue
                    # Q21 -> Q22 (tattoo/piercing)
                    if current_question == 22 and profile.has_tattoo_piercing is False:
                        current_question += 1
                        continue
                    # Q25 -> Q26 (surgery)
                    if current_question == 26 and profile.has_surgery_recently is False:
                        current_question += 1
                        continue

                    # If no skipping rule applied, break out of loop
                    break

                request.session['report_current_question'] = current_question

                if current_question <= len(ELIGIBILITY_QUESTIONS):
                    # Ask next question
                    next_question = ELIGIBILITY_QUESTIONS[current_question - 1]
                    return JsonResponse({
                        'answer': next_question,
                        'in_question_flow': True,
                        'question_number': current_question,
                        'total_questions': len(ELIGIBILITY_QUESTIONS)
                    })
                else:
                    # All questions completed - generate report
                    request.session['report_question_flow'] = False
                    request.session['report_current_question'] = 0

                    # Check eligibility
                    eligible, reasons = check_eligibility(profile)

                    return JsonResponse({
                        'answer': f'Thank you for providing all the information! Your eligibility assessment is complete.',
                        'in_question_flow': False,
                        'completed': True,
                        'eligible': eligible,
                        'reasons': reasons,
                        'profile_id': profile.id
                    })
            
            # Start question flow
            request.session['report_question_flow'] = True
            request.session['report_current_question'] = 1
            first_question = ELIGIBILITY_QUESTIONS[0]
            
            return JsonResponse({
                'answer': f'Great! I\'ll help you check your eligibility for blood donation. Let\'s start with a few questions.<br><br><b>{first_question}</b>',
                'in_question_flow': True,
                'question_number': 1,
                'total_questions': len(ELIGIBILITY_QUESTIONS)
            })

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method Not Allowed'}, status=405)

# --- 7. RESET ASSESSMENT ---
@csrf_exempt
def reset_assessment(request):
    """Reset the assessment - clear session and delete old profile"""
    if request.method == 'POST':
        try:
            # Clear all session data related to report
            if 'report_question_flow' in request.session:
                del request.session['report_question_flow']
            if 'report_current_question' in request.session:
                del request.session['report_current_question']
            if 'health_profile_id' in request.session:
                old_session_id = request.session['health_profile_id']
                del request.session['health_profile_id']
                # Delete old profile from database
                try:
                    UserHealthProfile.objects.filter(session_id=old_session_id).delete()
                except:
                    pass
            
            request.session.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Assessment reset. Ready to start fresh.'
            })
        except Exception as e:
            print(f"Error resetting assessment: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method Not Allowed'}, status=405)

# --- 8. DOWNLOAD REPORT ---
def download_report(request, profile_id):
    """Generate and download eligibility report as HTML/PDF"""
    try:
        profile = UserHealthProfile.objects.get(id=profile_id)
        
        # Check eligibility if not already done
        if not profile.eligibility_status:
            check_eligibility(profile)
        
        # Generate HTML report
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Blood Donation Eligibility Report - {profile.name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 800px; margin: 0 auto; }}
                .header {{ text-align: center; border-bottom: 3px solid #dc2626; padding-bottom: 20px; margin-bottom: 30px; }}
                .header h1 {{ color: #dc2626; margin: 0; }}
                .section {{ margin: 25px 0; }}
                .section h2 {{ color: #333; border-left: 4px solid #dc2626; padding-left: 10px; }}
                .info-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }}
                .info-label {{ font-weight: bold; color: #666; }}
                .status {{ padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center; font-size: 18px; font-weight: bold; }}
                .eligible {{ background: #d1fae5; color: #065f46; border: 2px solid #10b981; }}
                .not-eligible {{ background: #fee2e2; color: #991b1b; border: 2px solid #ef4444; }}
                .reasons {{ background: #f9fafb; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .reasons ul {{ margin: 10px 0; padding-left: 20px; }}
                .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🩸 Blood Donation Eligibility Report</h1>
                    <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
                
                <div class="section">
                    <h2>Personal Information</h2>
                    <div class="info-row">
                        <span class="info-label">Name:</span>
                        <span>{profile.name or 'Not provided'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Age:</span>
                        <span>{profile.age or 'Not provided'} years</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Weight:</span>
                        <span>{profile.weight or 'Not provided'} kg</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Gender:</span>
                        <span>{profile.gender or 'Not provided'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Blood Group:</span>
                        <span>{profile.blood_category or 'Not provided'}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Health Information</h2>
                    <div class="info-row">
                        <span class="info-label">Blood Pressure:</span>
                        <span>{profile.blood_pressure or 'Not provided'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Hemoglobin Level:</span>
                        <span>{profile.hemoglobin_level or 'Not provided'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Diabetes:</span>
                        <span>{'Yes' if profile.has_diabetes else 'No'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Anemia:</span>
                        <span>{'Yes' if profile.has_anemia else 'No'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Previous COVID-19:</span>
                        <span>{'Yes' if profile.had_corona else 'No'}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Eligibility Status</h2>
                    <div class="status {'eligible' if profile.eligibility_status == 'Eligible' else 'not-eligible'}">
                        {profile.eligibility_status or 'Pending Assessment'}
                    </div>
                    <div class="reasons">
                        <h3>Assessment Details:</h3>
                        <ul>
                            {''.join([f'<li>{reason}</li>' for reason in profile.eligibility_reasons.split('\\n') if reason])}
                        </ul>
                    </div>
                </div>
                
                <div class="footer">
                    <p>This report is generated for informational purposes only.</p>
                    <p>Please consult with a medical professional before donating blood.</p>
                    <p>Blood Assistant AI - {datetime.now().strftime('%Y')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        response = HttpResponse(html_content, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="eligibility_report_{profile.name or "user"}_{datetime.now().strftime("%Y%m%d")}.html"'
        return response
        
    except UserHealthProfile.DoesNotExist:
        return HttpResponse("Report not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error generating report: {str(e)}", status=500)

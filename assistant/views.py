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

def generate_ai_recommendations(topic_text, generator):
    """Generates 3 SPECIFIC follow-up questions based on the answer text."""
    try:
        short_context = topic_text[:400]
        prompt = f"""
        Read this medical text: "{short_context}"
        
        Task: Create 3 specific follow-up questions a user might ask. 
        Rules:
        1. Questions must be about the text.
        2. Do NOT use generic phrases like "Tell me more" or "Explain".
        3. Make them complete questions.
        
        Output Format: Q1? Q2? Q3?
        """
        
        results = generator(prompt, max_length=100, do_sample=True, temperature=0.95)
        raw_text = results[0]['generated_text'].strip()
        
        parts = raw_text.split('?')
        clean_recs = []
        for p in parts:
            clean_q = re.sub(r'^[0-9\.\-\s]+', '', p).strip()
            if len(clean_q) > 10 and "tell me more" not in clean_q.lower():
                clean_recs.append(clean_q + "?")
        
        clean_recs = list(set(clean_recs))
        
        if len(clean_recs) < 3:
            clean_recs.append("What are the benefits?")
            clean_recs.append("Are there any side effects?")
            
        return clean_recs[:3]
    except Exception as e:
        print(f"Rec Gen Error: {e}")
        return ["Who can donate?", "Is donation safe?", "How often can I donate?"]

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

            # Load the selected model
            generator = load_model_if_needed(model_name)
            
            q_lower = question.lower()
            intent = "UNKNOWN"

            # Check for "Contextless" inputs
            if len(question) < 5 or q_lower in ["tell me more", "explain", "explain more", "yes", "no"]:
                return JsonResponse({
                    'answer': "I need a little more detail. What specific topic would you like me to explain more about? (e.g., 'Explain more about age limits')", 
                    'source': 'System', 
                    'confidence': 1.0,
                    'recommendations': ["Who can donate blood?", "What are the risks?", "Locations near me"]
                })

            # STRICT CONCEPT FILTER
            concept_keywords = [
                "what", "why", "how", "who", "risk", "benefit", "safe", "eligible", 
                "age", "limit", "weight", "process", "procedure", "explain", "define", 
                "can i", "should i", "maximum", "minimum"
            ]
            
            if any(word in q_lower for word in concept_keywords):
                intent = "EXPLAIN"
            
            # AI ROUTER
            if intent == "UNKNOWN":
                router_prompt = f"""
                Classify user intent.
                "Find blood bank" -> SEARCH
                "Locations in Surat" -> SEARCH
                "Donate near me" -> SEARCH
                "Blood donation camps" -> SEARCH
                "What is hemoglobin?" -> EXPLAIN
                "Max age for donation" -> EXPLAIN
                
                Question: "{question}"
                Answer (SEARCH or EXPLAIN):
                """
                router_out = generator(router_prompt, max_length=5, do_sample=False)
                intent = router_out[0]['generated_text'].strip().upper()
            
            print(f"User: {question} | Intent: {intent} | Model: {model_name}")

            # PATH A: SEARCH
            if "SEARCH" in intent:
                city = "Ahmedabad"
                if 'surat' in q_lower: city = "Surat"
                elif 'vadodara' in q_lower: city = "Vadodara"
                
                banks, camps = get_blood_data_dynamic(city)
                rec_context = f"Blood banks in {city}: " + (banks[0]['name'] if banks else "General info")
                recommendations = generate_ai_recommendations(rec_context, generator)

                html = f"""<div class="space-y-4"><div class="text-sm text-gray-600 mb-2">Latest locations in <b>{city.title()}</b>.</div>"""
                
                if banks:
                    html += f'<div class="font-bold text-gray-800 border-b pb-1 mb-2">🏥 Blood Banks</div>'
                    for i, b in enumerate(banks):
                        html += f'<div class="bg-white p-3 mb-2 border rounded shadow-sm"><b>{i+1}. {b["name"]}</b><br><span class="text-xs">{b["snippet"][:120]}...</span><br><a href="{b["source_link"]}" target="_blank" class="text-xs text-blue-600 underline">Visit Link</a></div>'
                
                if camps:
                    html += f'<div class="font-bold text-gray-800 border-b pb-1 mt-4 mb-2">📅 Camps</div>'
                    for i, c in enumerate(camps):
                        html += f'<div class="bg-red-50 p-3 mb-2 border border-red-100 rounded"><b>{i+1}. {c["name"]}</b><br><span class="text-xs">{c["snippet"][:120]}...</span><br><a href="{c["source_link"]}" target="_blank" class="text-xs text-red-600 underline">Details</a></div>'
                html += "</div>"
                
                return JsonResponse({
                    'answer': html,
                    'source': 'Tavily Search',
                    'confidence': 1.0,
                    'recommendations': recommendations,
                    'model_used': AVAILABLE_MODELS[model_name]['name']
                })

            # PATH B: EXPLAIN
            else:
                explain_prompt = f"""
            You are a medical assistant AI. Provide an accurate, dynamic, and concise answer based on the user's question.

            Rules:
            1. Do not repeat the question.
            2. Do not hallucinate facts.
            3. Provide globally accepted medical guidelines only when necessary.
            4. If the question is vague, request clarification.
            5. Answer in simple, human-readable language.

            Question: "{question}"
            Answer:
            """

                res = generator(
                    explain_prompt,
                    max_length=256,
                    do_sample=True,
                    temperature=0.8,
                    top_p=0.95
                )

                answer_text = res[0]['generated_text'].strip()
                recommendations = generate_ai_recommendations(answer_text, generator)

                return JsonResponse({
                    'answer': answer_text,
                    'source': 'Generative AI',
                    'confidence': 1.0,
                    'recommendations': recommendations,
                    'model_used': AVAILABLE_MODELS[model_name]['name']
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

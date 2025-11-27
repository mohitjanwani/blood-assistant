# 🩸 Blood Assistant AI - Quick Summary

## Project Overview
An AI-powered web app that helps users check blood donation eligibility, answers medical questions, and finds blood banks nearby.

---

## Tech Stack (Quick)

| Category | Technology |
|----------|-----------|
| **Backend** | Django 5.2.8 + Python |
| **Database** | SQLite3 |
| **AI Model** | Google FLAN-T5-Large |
| **Frontend** | HTML5, TailwindCSS, Vanilla JS |
| **Voice** | Web Speech API |
| **Search API** | Tavily Search |
| **Server** | Gunicorn |

---

## AI Models Used

### 1. **Google FLAN-T5-Large**
- **What:** Large language model for text generation
- **Size:** 770 million parameters
- **Use:** Answers medical questions about blood donation
- **Benefit:** Natural, conversational responses with medical accuracy

### 2. **Intent Classification**
- **What:** Hybrid keyword + AI classification
- **Use:** Detects if user wants to SEARCH (find banks) or EXPLAIN (get info)
- **Benefit:** Routes user query to correct service

### 3. **Recommendation Engine**
- **What:** FLAN-T5 generates follow-up questions
- **Use:** Creates 3 specific follow-up questions after each answer
- **Benefit:** Keeps conversation contextual and relevant

### 4. **Eligibility Algorithm**
- **What:** Rule-based medical assessment system
- **Use:** Evaluates 11 health criteria for blood donation eligibility
- **Benefit:** Accurate, compliant with WHO/medical standards

---

## Key Features

✅ **Chat with AI** - Ask any blood donation question  
✅ **26-Question Assessment** - Comprehensive eligibility check  
✅ **Smart Skip Logic** - Skips gender-specific questions automatically  
✅ **Find Blood Banks** - Real-time search via Tavily API  
✅ **Voice Input/Output** - Speak questions, listen to answers  
✅ **Download Report** - HTML eligibility certificate  
✅ **Multi-Language** - Auto-detects Hindi, English, Spanish  
✅ **Session-Based** - No login required (anonymous-friendly)  

---

## API Endpoints (4 Total)

| Endpoint | Purpose | Input |
|----------|---------|-------|
| `/api/chat/` | Answer questions | Medical question |
| `/api/report/` | Eligibility assessment | Answer to question |
| `/api/reset/` | Clear session | - |
| `/download-report/<id>/` | Get PDF report | Profile ID |

---

## Eligibility Criteria (11 Checks)

| Criterion | Eligible | Not Eligible |
|-----------|----------|--------------|
| Age | 18-65 years | <18 or >65 |
| Weight | ≥50 kg | <50 kg |
| Hemoglobin | F:≥12.5, M:≥13.5 g/dL | Below minimum |
| Diabetes | Controlled | Uncontrolled |
| Infectious Disease | None | HIV, Hepatitis |
| COVID-19 | Never or >28 days recovery | <28 days |
| Pregnancy | Not pregnant | Currently pregnant |
| Breastfeeding | Not breastfeeding | Currently breastfeeding |
| Tattoo/Piercing | None or >6 months ago | <6 months |
| Surgery | None or >6 months ago | <6 months |
| Anemia | Not present | Present |

---

## Question Flow (26 Questions)

1. Personal Info (5 Q): Name, Age, Weight, Gender, Blood Type
2. Medical Conditions (4 Q): Diabetes, Anemia, Hemoglobin, Blood Pressure
3. Diseases (5 Q): COVID, Allergies, Medications, Chronic Diseases, Infectious Diseases
4. Lifestyle (4 Q): Tattoo/Piercing, Pregnancy, Breastfeeding, Surgery
5. History (3 Q): Previous donations, details

**Smart Skip:** Questions 12, 14, 16, 18, 20, 22, 26 skip if previous answer is "No"  
**Gender Skip:** Questions 23-24 skip for males

---

## Database Model

**UserHealthProfile** stores:
- Personal data (name, age, weight, gender, blood type)
- Medical history (diabetes, anemia, diseases, medications, allergies)
- Lifestyle info (tattoos, surgery, pregnancy, breastfeeding)
- Assessment results (eligibility status, reasons)
- Timestamps (created_at, updated_at)

---

## Benefits

### For Users
🎯 Instant eligibility check without visiting clinics  
🎯 Quick answers to medical questions  
🎯 Find nearby blood banks and donation camps  
🎯 Download official eligibility report  
🎯 Multi-language support with voice features  

### For Developers
⚙️ Modular, scalable architecture  
⚙️ Easy to extend with more features  
⚙️ Open-source, customizable  
⚙️ Production-ready with Gunicorn support  

### For Healthcare
💉 Reduce clinic visits for eligibility screening  
💉 Accurate medical assessment  
💉 Compliant with WHO guidelines  
💉 Valuable health data insights  

---

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Migrate database
python manage.py migrate

# Run
python manage.py runserver

# Visit
http://localhost:8000
```

---

## External Integrations

1. **Tavily Search API** - Find blood banks and camps
2. **Hugging Face** - Download FLAN-T5 model
3. **Indian Red Cross** - Official resources

---

## Security Features

✔️ CSRF protection (Django)  
✔️ Session-based authentication  
✔️ Input validation on all fields  
✔️ SQL injection prevention (Django ORM)  
✔️ No personal data exposed  

---

## Future Enhancements

- Mobile app (React Native/Flutter)
- SMS/Email notifications
- Appointment booking
- Blood inventory tracking
- AI predictions for blood demand
- Blockchain tracking
- Multi-country support

---

## Summary in One Line

**An AI chatbot + medical assessment tool that checks blood donation eligibility, answers health questions, and finds blood banks using FLAN-T5 language model and Tavily search API.**

---

*Generated: November 27, 2025*  
*Repository: blood-assistant (mohitjanwani)*

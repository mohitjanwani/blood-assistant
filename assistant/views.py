from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from transformers import pipeline

# Global variable to hold the model
GENERATOR = None

def load_model_if_needed():
    """
    Loads the Generative AI model into memory only when needed.
    """
    global GENERATOR
    if GENERATOR is None:
        print("Loading Generative Model... (This may take a moment)")
        # We use 'text2text-generation' which is perfect for Q&A.
        # 'google/flan-t5-large' is smarter but slower. 
        # If it crashes your computer, change it to 'google/flan-t5-base'
        try:
            GENERATOR = pipeline(
                "text2text-generation", 
                model="google/flan-t5-large", 
                max_length=512
            )
        except Exception as e:
            print(f"Error loading model: {e}")
            raise e

def home(request):
    return render(request, 'assistant/home.html')

def chat_page(request):
    return render(request, 'assistant/chat.html')

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chat')
    else:
        form = UserCreationForm()
    return render(request, 'assistant/register.html', {'form': form})

def get_response(request):
    """
    GET request handler (optional, if you use GET elsewhere)
    """
    if request.method == "GET":
        question = request.GET.get("msg", "").strip()
        if not question:
            return JsonResponse({"response": "Please ask a valid question."})

        try:
            load_model_if_needed()
            # Generate answer directly from the model's knowledge
            output = GENERATOR(question, max_length=200, do_sample=True)
            answer = output[0]['generated_text']

            return JsonResponse({
                "response": answer,
                "source": "AI Generated",
                "confidence": 1.0
            })
        except Exception as e:
            return JsonResponse({"response": f"Error: {str(e)}"})

@csrf_exempt
def chat_api(request):
    """
    POST JSON: {"question": "What is hemoglobin?"}
    Returns: {"answer": "Hemoglobin is a protein...", "source": "AI Model", "confidence": 1.0}
    """
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            question = body.get('question', '').strip()
            
            if not question:
                return JsonResponse({'error': 'Empty question'}, status=400)

            # 1. Load Model
            load_model_if_needed()

            # 2. Ask the model to generate an answer
            # We add a prompt prefix to help the model understand its role
            prompt = f"Answer the following question concisely in the same language it was asked: {question}"
            
            results = GENERATOR(prompt, max_length=256, min_length=20, do_sample=False)
            answer_text = results[0]['generated_text']

            # 3. Return the answer
            return JsonResponse({
                'answer': answer_text, 
                'source': 'Generative AI (Flan-T5)', 
                'confidence': 1.0
            })

        except Exception as e:
            print(f"Server Error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)
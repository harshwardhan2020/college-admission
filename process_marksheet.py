import os
import io
import json
import requests
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv
import pdfplumber
from PIL import Image
import pytesseract
# import spacy  # --- No longer needed, AI will do this ---
import re
from flask_cors import CORS
import google.generativeai as genai  # --- NEW AI IMPORT ---

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
SUPABASE_TABLE = os.getenv('SUPABASE_TABLE', 'submissions')
# --- NEW: CONFIGURE AI ---
try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
except Exception as e:
    print(f"Warning: Could not configure Google AI. Check GOOGLE_API_KEY. Error: {e}")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print('Warning: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set')

# nlp = spacy.load('en_core_web_sm') # --- No longer needed ---

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# --- CORS and Preflight (unchanged) ---
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/", methods=["OPTIONS"])
@app.route("/process", methods=["OPTIONS"])
def handle_preflight():
    resp = make_response()
    resp.status_code = 200
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

# --- FILE HELPER FUNCTIONS (unchanged) ---

def download_file(url):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    content_type = r.headers.get('content-type', '')
    return r.content, content_type

def extract_text_from_pdf_bytes(b):
    try:
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            # --- ADDED: Fallback to OCR for scanned PDFs ---
            if not text.strip():
                print("PDF text empty, falling back to OCR...")
                with pdfplumber.open(io.BytesIO(b)) as pdf:
                    first_page = pdf.pages[0]
                    pil_img = first_page.to_image(resolution=300).original
                    text = pytesseract.image_to_string(pil_img)
            return text
    except Exception as e:
        print('pdfplumber error', e)
        return ''

def extract_text_from_image_bytes(b):
    try:
        img = Image.open(io.BytesIO(b)).convert('RGB')
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        print('pytesseract error', e)
        return ''

# --- OLD extract_candidate_info (REMOVED) ---
# def extract_candidate_info(text):
# ... we are replacing this with the AI function ...


# --- NEW AI ANALYSIS FUNCTION ---
def get_ai_analysis(doc_text):
    """
    Uses Generative AI to extract info, score, and recommend a branch.
    """
    model = genai.GenerativeModel('gemini-1.5-flash') # Using the fast model
    
    # This prompt is key. We ask for JSON output.
    prompt = f"""
    You are an intelligent college admission document processor.
    Analyze the following document text and return a SINGLE JSON object
    with the following keys:
    - "name": The full name of the candidate.
    - "grade12": The final 12th grade percentage or CGPA as a float.
    - "ai_score": Your calculated score (0-100) for this candidate's suitability.
    - "recommended_branch": The best-suited engineering branch (e.g., "Computer Science", "Mechanical", "Not applicable").

    Here is the document text:
    ---
    {doc_text}
    ---

    Return ONLY the JSON object.
    """

    try:
        response = model.generate_content(prompt)
        
        # Clean up the response to get *only* the JSON
        json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        print("AI Response (raw):", json_text)
        
        # Parse the JSON string into a Python dictionary
        ai_data = json.loads(json_text)
        
        # --- Data Validation ---
        # Ensure all keys are present, providing defaults if not
        validated_data = {
            'name': ai_data.get('name'),
            'grade12': ai_data.get('grade12'),
            'ai_score': ai_data.get('ai_score', 70.0), # Default score
            'recommended_branch': ai_data.get('recommended_branch', 'General Engineering')
        }
        return validated_data
        
    except Exception as e:
        print(f"❌ Error during AI analysis: {e}")
        # Return a default object in case of failure
        return {
            'name': None,
            'grade12': None,
            'ai_score': 70.0, # Default score
            'recommended_branch': 'General Engineering'
        }


def update_submission(submission_id, payload):
    # (This function is unchanged)
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?id=eq.{submission_id}"
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json'
    }
    r = requests.patch(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    return r.json()

# --- MODIFIED /process ENDPOINT ---
@app.route('/process', methods=['POST'])
def process():
    try:
        data = request.get_json(force=True)
        print("Received JSON:", data)
        if not data:
            return jsonify({'error': 'No JSON body received'}), 400

        submission_id = data.get('submission_id')
        file_url = data.get('file_url')
        if not submission_id or not file_url:
            return jsonify({'error': 'submission_id and file_url required'}), 400

        # --- Step 1: Download file (unchanged) ---
        try:
            b, content_type = download_file(file_url)
        except Exception as e:
            return jsonify({'error': 'failed to download file', 'details': str(e)}), 400

        # --- Step 2: Extract text (unchanged) ---
        text = ''
        if 'pdf' in content_type.lower() or file_url.lower().endswith('.pdf'):
            text = extract_text_from_pdf_bytes(b)
        else:
            text = extract_text_from_image_bytes(b)
            
        if not text.strip():
            print("❌ No text could be extracted from the document.")
            return jsonify({'error': 'No text found in document'}), 400

        # --- Step 3: NEW AI Analysis ---
        # This one line replaces all the old extraction and simulation code
        ai_results = get_ai_analysis(text)
        print("AI Analysis complete:", ai_results)

        # --- Step 4: Build Payload ---
        payload = {
            'status': 'Verified',
            'ai_score': ai_results.get('ai_score'),
            'recommended_branch': ai_results.get('recommended_branch')
        }
        # Only add name and grade if the AI found them
        if ai_results.get('name'):
            payload['name'] = ai_results.get('name')
        if ai_results.get('grade12'):
            payload['grade12'] = ai_results.get('grade12')

        # --- Step 5: Update Supabase (unchanged) ---
        try:
            resp = update_submission(submission_id, payload)
            print("✅ Supabase updated successfully:", resp)
            return jsonify({'ok': True, 'extracted': ai_results, 'updated': resp})
        except Exception as e:
            return jsonify({'error': 'failed updating submission', 'details': str(e)}), 500

    except Exception as e:
        print("❌ General backend error:", e)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

# --- (unchanged) ---
if __name__ == '__main__':
    app.run(debug=True)

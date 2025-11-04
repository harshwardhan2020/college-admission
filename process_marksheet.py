import os
import io
import json
import requests
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv
import pdfplumber
from PIL import Image
import pytesseract
import spacy
import re
from flask_cors import CORS



load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
SUPABASE_TABLE = os.getenv('SUPABASE_TABLE', 'submissions')

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print('Warning: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment')

nlp = spacy.load('en_core_web_sm')

app = Flask(__name__)

# New code 
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"             # allow any site
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

# --- Pre-flight handler for OPTIONS ---
@app.route('/', methods=['OPTIONS'])
def root_preflight():
    resp = make_response()
    resp.status_code = 200
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"]
    return resp
# @app.route('/process', methods=['POST'])
# def process():
#     data = request.get_json() or {}
#     submission_id = data.get('submission_id')
#     file_url = data.get('file_url')
#     if not submission_id or not file_url:
#         return jsonify({'error': 'submission_id and file_url required'}), 400

#     try:
#         b, content_type = download_file(file_url)
#     except Exception as e:
#         return jsonify({'error': 'failed to download file', 'details': str(e)}), 400

    # ---- Extract text from file (PDF or Image) ----
    # if 'pdf' in content_type.lower() or file_url.lower().endswith('.pdf'):
    #     text = extract_text_from_pdf_bytes(b)
    #     if not text.strip():
    #         try:
    #             with pdfplumber.open(io.BytesIO(b)) as pdf:
    #                 first = pdf.pages[0]
    #                 pil_img = first.to_image(resolution=300).original
    #                 text = pytesseract.image_to_string(pil_img)
    #         except Exception as e:
    #             print('pdf->image fallback failed', e)
    #             text = ''
    # else:
    #     text = extract_text_from_image_bytes(b)

    # info = extract_candidate_info(text or '')

    # # ---- Simple AI Simulation ----
    # guessed_name = info['names'][0] if info['names'] else None
    # guessed_mark = info['numbers'][0] if info['numbers'] else None

    # ai_score = 85.0  # simulated AI score
    # recommended_branch = "Computer Science"  # sample recommendation

    # # ---- Prepare Supabase update ----
    # payload = {
    #     "status": "Verified",  # now mark as verified
    #     "ai_score": ai_score,
    #     "recommended_branch": recommended_branch
    # }

    # if guessed_name:
    #     payload["name"] = guessed_name
    # if guessed_mark is not None:
    #     payload["grade12"] = guessed_mark

    # try:
    #     resp = update_submission(submission_id, payload)
    #     print("✅ Supabase updated successfully:", resp)
    #     return jsonify({
    #         "ok": True,
    #         "extracted": info,
    #         "ai_score": ai_score,
    #         "recommended_branch": recommended_branch,
    #         "updated": resp
    #     })
    # except Exception as e:
    #     print("❌ failed to update submission", e)
    #     return jsonify({'error': 'failed updating submission', 'details': str(e)}), 500



def download_file(url):
    """Return bytes and content-type"""
    r = requests.get(url, stream=True)
    r.raise_for_status()
    content_type = r.headers.get('content-type', '')
    return r.content, content_type


def extract_text_from_pdf_bytes(b):
    try:
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            if text.strip():
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


def extract_candidate_info(text):
    # Basic heuristics: find PERSON names via spaCy and numbers that look like marks
    doc = nlp(text)
    names = [ent.text for ent in doc.ents if ent.label_ == 'PERSON']

    # find likely marks (numbers between 0-200 or percentages like 85.5%)
    marks = re.findall(r"(\d+\.?\d*)%?|(?:(?:total\s*[:\-]?\s*)(\d+))", text, re.IGNORECASE)
    # marks regex returns tuples because of groups; flatten and filter
    flat_marks = []
    for m in marks:
        if isinstance(m, tuple):
            for part in m:
                if part:
                    flat_marks.append(part)
        elif m:
            flat_marks.append(m)
    # keep numeric-looking values
    numeric = []
    for s in flat_marks:
        try:
            val = float(s)
            if 0 <= val <= 1000:
                numeric.append(val)
        except:
            pass

    # dedupe
    names = list(dict.fromkeys(names))
    numeric = sorted(list(set(numeric)), reverse=True)

    return {
        'names': names,
        'numbers': numeric
    }


def update_submission(submission_id, payload):
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?id=eq.{submission_id}"
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json'
    }
    r = requests.patch(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    return r.json()

@app.route('/process', methods=['POST'])
def process():
    try:
        # ✅ Force Flask to parse JSON body even if headers are slightly off
        data = request.get_json(force=True)
        print("Received JSON:", data)

        if not data:
            return jsonify({'error': 'No JSON body received'}), 400

        submission_id = data.get('submission_id')
        file_url = data.get('file_url')

        if not submission_id or not file_url:
            print("❌ Missing required fields:", submission_id, file_url)
            return jsonify({'error': 'submission_id and file_url required'}), 400

        # ✅ Download the file
        try:
            b, content_type = download_file(file_url)
        except Exception as e:
            print("❌ Download error:", e)
            return jsonify({'error': 'failed to download file', 'details': str(e)}), 400

        # ✅ Extract text from image or PDF
        text = ''
        if 'pdf' in content_type.lower() or file_url.lower().endswith('.pdf'):
            text = extract_text_from_pdf_bytes(b)
        else:
            text = extract_text_from_image_bytes(b)

        info = extract_candidate_info(text or '')
        print("Extracted info:", info)

        guessed_name = info['names'][0] if info['names'] else None
        guessed_mark = info['numbers'][0] if info['numbers'] else None

        # ✅ Build payload
        payload = {
            'status': 'Verified',
            'ai_score': 85.0,
            'recommended_branch': 'Computer Science'
        }
        if guessed_name:
            payload['name'] = guessed_name
        if guessed_mark:
            payload['grade12'] = guessed_mark

        # ✅ Update Supabase
        try:
            resp = update_submission(submission_id, payload)
            print("✅ Supabase updated successfully:", resp)
            return jsonify({'ok': True, 'extracted': info, 'updated': resp})
        except Exception as e:
            print("❌ Failed to update Supabase:", e)
            return jsonify({'error': 'failed updating submission', 'details': str(e)}), 500

    except Exception as e:
        print("❌ General backend error:", e)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True)


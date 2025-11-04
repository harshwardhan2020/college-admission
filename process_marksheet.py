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
@app.route("/", methods=["OPTIONS"])
@app.route("/", methods=["OPTIONS"])
def preflight():
    resp = make_response()
    resp.status_code = 200
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route('/process', methods=['POST'])
def process():
    data = request.get_json() or {}
    submission_id = data.get('submission_id')
    file_url = data.get('file_url')
    if not submission_id or not file_url:
        return jsonify({'error': 'submission_id and file_url required'}), 400

    try:
        b, content_type = download_file(file_url)
    except Exception as e:
        return jsonify({'error': 'failed to download file', 'details': str(e)}), 400

    # ---- Extract text from file (PDF or Image) ----
    if 'pdf' in content_type.lower() or file_url.lower().endswith('.pdf'):
        text = extract_text_from_pdf_bytes(b)
        if not text.strip():
            try:
                with pdfplumber.open(io.BytesIO(b)) as pdf:
                    first = pdf.pages[0]
                    pil_img = first.to_image(resolution=300).original
                    text = pytesseract.image_to_string(pil_img)
            except Exception as e:
                print('pdf->image fallback failed', e)
                text = ''
    else:
        text = extract_text_from_image_bytes(b)

    info = extract_candidate_info(text or '')

    # ---- Simple AI Simulation ----
    guessed_name = info['names'][0] if info['names'] else None
    guessed_mark = info['numbers'][0] if info['numbers'] else None

    ai_score = 85.0  # simulated AI score
    recommended_branch = "Computer Science"  # sample recommendation

    # ---- Prepare Supabase update ----
    payload = {
        "status": "Verified",  # now mark as verified
        "ai_score": ai_score,
        "recommended_branch": recommended_branch
    }

    if guessed_name:
        payload["name"] = guessed_name
    if guessed_mark is not None:
        payload["grade12"] = guessed_mark

    try:
        resp = update_submission(submission_id, payload)
        print("✅ Supabase updated successfully:", resp)
        return jsonify({
            "ok": True,
            "extracted": info,
            "ai_score": ai_score,
            "recommended_branch": recommended_branch,
            "updated": resp
        })
    except Exception as e:
        print("❌ failed to update submission", e)
        return jsonify({'error': 'failed updating submission', 'details': str(e)}), 500
    text = ''
    if 'pdf' in content_type.lower() or file_url.lower().endswith('.pdf'):
        text = extract_text_from_pdf_bytes(b)
        if not text.strip():
            # fallback to OCR on PDF first page
            try:
                with pdfplumber.open(io.BytesIO(b)) as pdf:
                    first = pdf.pages[0]
                    pil_img = first.to_image(resolution=300).original
                    text = pytesseract.image_to_string(pil_img)
            except Exception as e:
                print('pdf->image fallback failed', e)
    else:
        text = extract_text_from_image_bytes(b)

    info = extract_candidate_info(text or '')

    # pick best guesses
    guessed_name = info['names'][0] if info['names'] else None
    guessed_mark = info['numbers'][0] if info['numbers'] else None

    payload = {}
    if guessed_name:
        payload['name'] = guessed_name
    if guessed_mark is not None:
        # naive: if a percentage-like number and grade12 is null, try grade12
        payload['grade12'] = guessed_mark
    # mark status as 'Auto-Processed'
    payload['status'] = 'Auto-Processed'

    try:
        resp = update_submission(submission_id, payload)
    except Exception as e:
        print('failed to update submission', e)
        return jsonify({'error': 'failed updating submission', 'details': str(e)}), 500

    return jsonify({'ok': True, 'extracted': info, 'updated': resp})


if __name__ == '__main__':
    app.run(debug=True)







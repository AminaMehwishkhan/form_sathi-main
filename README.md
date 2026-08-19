# FormSathi — AI Government Form Assistant
**Understand. Fill. Validate. Print.**

Built for Build With Gemma Hackathon 2026 (GDG Cloud Lahore @ Arbisoft).

An offline, privacy-first AI assistant that reads a photo of any government form
(NADRA, passport, bank, university, visa, hospital, utility) using **Gemma 4 Vision**
running locally via **Ollama**, explains it in Urdu/English, asks for each field
conversationally, validates every answer instantly, and produces a downloadable
filled form (PNG / PDF / JSON) — entirely on-device, no data ever leaves the machine.

## Why this matters
Millions of people — elderly users, low-literacy applicants, rural communities —
struggle with English-language bureaucratic forms and pay "form writers" just to
fill them out correctly. FormSathi replaces that with a conversational, validated,
bilingual assistant that runs fully offline, so it works even without internet and
never sends sensitive CNIC/personal data to any cloud API.

## Setup

### 1. Install Ollama and pull the model
```bash
# https://ollama.com/download
ollama serve
ollama pull gemma4:e2b
```

### 2. Install Python dependencies
```bash
cd FormSathi
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. (Recommended) Install an Urdu font for correct rendering in the live preview / PDF
The overlay engine looks for Noto Nastaliq Urdu / Noto Sans Arabic on the system
and falls back to a default bitmap font if not found (which won't render Urdu
glyphs correctly). On Ubuntu/Debian:
```bash
sudo apt-get install fonts-noto
```
On macOS, install "Noto Nastaliq Urdu" from Google Fonts.

On **Windows**:
1. Download the font from [Google Fonts – Noto Nastaliq Urdu](https://fonts.google.com/noto/specimen/Noto+Nastaliq+Urdu)
2. Unzip it, right-click the `.ttf` file → **Install** (or **Install for all users**)
3. It installs to `C:\Windows\Fonts\` automatically — the app already looks there, no config needed.

### 4. Run the app
```bash
streamlit run app.py
```
Open the URL Streamlit prints (usually http://localhost:8501).

## Project structure
```
FormSathi/
├── app.py                  # Streamlit UI + full user journey (upload → analyze → conversation → done)
├── requirements.txt
├── schemas/
│   └── field_schema.py     # Pydantic models: FormAnalysis, FormField, ConversationState
├── utils/
│   ├── gemma.py             # Ollama client — vision analysis + text follow-ups
│   ├── prompts.py           # All prompt templates in one place
│   ├── image.py              # Preprocessing: resize, deskew, denoise, blur detection
│   ├── extraction.py         # Coerces raw Gemma JSON into validated FormAnalysis
│   ├── validation.py         # Rule-based validators (CNIC, phone, date, email, etc.)
│   ├── overlay.py            # Live filled-preview rendering (answer sheet + bbox overlay)
│   ├── pdf.py                 # PDF export
│   └── translation.py         # Lightweight Urdu/English detection + translation helper
├── uploads/ outputs/ forms/ assets/ static/
```

## How it works (pipeline)
```
Upload image → preprocess (deskew/denoise/blur check)
            → Gemma 4 Vision (single structured prompt, forced JSON output)
            → parse & coerce into FormAnalysis/FormField schema
            → conversational loop: one question at a time (Urdu + English)
            → validate every answer instantly (regex/rule-based, no extra LLM call)
            → live filled preview (original next to filled answer sheet)
            → download as PNG / PDF / JSON
```

## What's real vs. what's an MVP simplification
- **Real & working:** the full Streamlit flow, the Gemma prompt + JSON schema contract,
  every validator (CNIC/phone/date/email/etc., matching the spec's exact examples),
  the live answer-sheet preview, and PDF/JSON export.
- **MVP simplification:** precise pixel-level field localization on the *original* form
  image is a hard vision problem on its own. The overlay engine supports bounding
  boxes if Gemma returns them, but defaults to rendering a clean parallel "filled
  answer sheet" next to the original — this is the honest, demo-safe version of the
  left/right live preview described in the spec, and upgrades gracefully as
  localization improves.

## Demo script (suggested)
1. Show `ollama serve` running locally — no internet required, zero data leaves the device.
2. Upload a CNIC form photo → show the Urdu explanation + required documents appear.
3. Walk through 2-3 fields, including one that deliberately fails validation
   (e.g. type `3520` for CNIC) to show the instant Urdu error message.
4. Show the live filled preview updating.
5. Download the PDF and open it.

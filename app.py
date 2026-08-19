"""
FormSathi — AI Government Form Assistant
Understand. Fill. Validate. Print.

Run with:  streamlit run app.py
Requires:  ollama serve   +   ollama pull gemma4:e2b
"""

from __future__ import annotations
import json
import streamlit as st
from PIL import Image

from utils.gemma import analyze_form_image, explain_field, check_ollama_alive, GemmaError, DEFAULT_MODEL
from utils.extraction import parse_gemma_response
from utils.image import prepare_for_analysis, blur_score
from utils.validation import validate_field, find_missing_required
from utils.overlay import render_answer_sheet, side_by_side, draw_bbox_overlays
from utils.pdf import build_filled_form_pdf
from schemas.field_schema import FormAnalysis, ConversationState

st.set_page_config(page_title="FormSathi", page_icon="📝", layout="wide")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "stage": "upload",          # upload -> analyzing -> conversation -> done
        "original_image": None,
        "analysis": None,           # FormAnalysis
        "conv": ConversationState(),
        "chat_log": [],             # list of (speaker, text) for the conversation UI
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def reset_app():
    for k in ["stage", "original_image", "analysis", "conv", "chat_log"]:
        del st.session_state[k]
    _init_state()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📝 FormSathi")
    st.caption("Understand. Fill. Validate. Print.")
    st.divider()

    alive = check_ollama_alive()
    if alive:
        st.success("Ollama connected")
    else:
        st.error("Ollama not reachable")
        st.caption("Run `ollama serve` and `ollama pull gemma4:e2b` in a terminal.")

    model_name = st.text_input("Model", value=DEFAULT_MODEL)
    st.divider()
    if st.button("🔄 Start over"):
        reset_app()
        st.rerun()


# ---------------------------------------------------------------------------
# Stage 1: Upload
# ---------------------------------------------------------------------------
if st.session_state.stage == "upload":
    st.title("Upload a Government Form")
    st.write(
        "Take a photo of any form — NADRA, passport, bank, university, visa, "
        "hospital, utility connection — and FormSathi will explain it and help you fill it, in Urdu or English."
    )

    uploaded = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    if uploaded is not None:
        file_bytes = uploaded.read()
        preview_img = Image.open(uploaded)
        st.image(preview_img, caption="Original Form", width=400)

        col1, col2 = st.columns([1, 1])
        clean = col1.checkbox("Auto-clean image (deskew/denoise)", value=True)
        analyze_clicked = col2.button("🔍 Analyze Form", type="primary", disabled=not alive)

        if not alive:
            st.warning("Connect Ollama first (see sidebar) before analyzing.")

        if analyze_clicked:
            img, processed_bytes = prepare_for_analysis(file_bytes, clean=clean)
            score = blur_score(img)
            if score < 40:
                st.warning(
                    f"⚠️ This photo looks a bit blurry (sharpness score: {score:.0f}). "
                    "You can still continue, but retaking it may improve accuracy."
                )

            st.session_state.original_image = img

            with st.spinner("Gemma is reading your form..."):
                try:
                    raw = analyze_form_image(processed_bytes, model=model_name)
                    analysis = parse_gemma_response(raw)
                except GemmaError as e:
                    st.error(str(e))
                    st.stop()
                except Exception as e:
                    st.error(f"Couldn't parse the form. Try a clearer photo. ({e})")
                    st.stop()

            st.session_state.analysis = analysis
            st.session_state.stage = "conversation"
            st.session_state.chat_log = [
                ("assistant", analysis.explanation_urdu),
                ("assistant", analysis.explanation_english),
            ]
            st.rerun()


# ---------------------------------------------------------------------------
# Stage 2: Conversation + live preview + validation
# ---------------------------------------------------------------------------
elif st.session_state.stage == "conversation":
    analysis: FormAnalysis = st.session_state.analysis
    conv: ConversationState = st.session_state.conv

    left, right = st.columns([1, 1])

    with left:
        st.subheader(analysis.title)
        st.caption(f"⏱️ Estimated time: {analysis.estimated_time}  |  Confidence: {analysis.confidence:.0%}")

        if analysis.confidence < 0.75:
            st.warning(f"I'm only {analysis.confidence:.0%} confident in this reading. Consider retaking the photo.")

        if analysis.warnings:
            for w in analysis.warnings:
                st.info(f"ℹ️ {w}")

        with st.expander("📎 Required documents", expanded=True):
            for doc in analysis.required_documents:
                st.markdown(f"- {doc}")

        st.markdown("#### Original Form")
        st.image(draw_bbox_overlays(st.session_state.original_image, analysis.fields), width=380)

    with right:
        st.markdown("#### Conversation")
        chat_box = st.container(height=280)
        with chat_box:
            for speaker, text in st.session_state.chat_log:
                with st.chat_message("assistant" if speaker == "assistant" else "user"):
                    st.write(text)

        current = conv.current_field(analysis.fields)

        if current and not conv.completed:
            st.markdown(f"**{current.question_urdu}**")
            st.caption(current.question_english or current.label)

            if current.help_text_urdu:
                with st.popover("❓ اس کا کیا مطلب ہے؟ / What does this mean?"):
                    st.write(current.help_text_urdu)
                    if current.help_text_english:
                        st.caption(current.help_text_english)
                    if st.button("Explain differently", key=f"explain_{current.id}"):
                        with st.spinner("..."):
                            hint = explain_field(current.label, current.help_text_urdu or "", model=model_name)
                        st.write(hint.get("urdu", ""))
                        st.caption(hint.get("english", ""))

            with st.form(key=f"field_form_{current.id}", clear_on_submit=True):
                answer = st.text_input("Your answer / آپ کا جواب", key=f"input_{current.id}")
                submitted = st.form_submit_button("Next →")

            if submitted:
                is_valid, error_urdu = validate_field(current.validation, answer, current.required)
                current.value = answer
                current.is_valid = is_valid
                current.error_message = error_urdu

                st.session_state.chat_log.append(("user", answer if answer else "(skipped)"))

                if is_valid:
                    conv.advance(len(analysis.fields))
                    nxt = conv.current_field(analysis.fields)
                    if nxt:
                        st.session_state.chat_log.append(("assistant", nxt.question_urdu))
                    else:
                        st.session_state.chat_log.append(
                            ("assistant", "شکریہ! تمام معلومات مکمل ہو گئیں۔ / Thank you, all done!")
                        )
                        st.session_state.stage = "done"
                else:
                    st.session_state.chat_log.append(("assistant", f"❌ {error_urdu}"))
                st.rerun()

        elif conv.completed:
            st.success("✅ All questions answered.")
            st.session_state.stage = "done"
            st.rerun()

        st.markdown("#### Live Filled Preview")
        sheet = render_answer_sheet(analysis.fields, analysis.title)
        st.image(sheet, width=380)


# ---------------------------------------------------------------------------
# Stage 3: Done — validation summary + download
# ---------------------------------------------------------------------------
elif st.session_state.stage == "done":
    analysis: FormAnalysis = st.session_state.analysis
    st.title("✅ Form Ready")

    missing = find_missing_required(analysis.fields)
    if missing:
        st.error("❌ Missing required fields: " + ", ".join(missing))
    else:
        st.success("All required fields are complete and valid.")

    sheet = render_answer_sheet(analysis.fields, analysis.title)
    combined = side_by_side(st.session_state.original_image, sheet)
    st.image(combined, caption="Original (left) vs Filled (right)", use_container_width=True)

    st.markdown("#### Download")
    d1, d2, d3 = st.columns(3)

    import io
    img_buf = io.BytesIO()
    sheet.save(img_buf, format="PNG")
    d1.download_button("⬇️ Filled Image (PNG)", img_buf.getvalue(), file_name="filled_form.png", mime="image/png")

    pdf_bytes = build_filled_form_pdf(analysis.title, sheet, missing_fields=missing)
    d2.download_button("⬇️ PDF", pdf_bytes, file_name="filled_form.pdf", mime="application/pdf")

    json_payload = json.dumps(
        {
            "title": analysis.title,
            "fields": [
                {"id": f.id, "label": f.label, "value": f.value, "valid": f.is_valid}
                for f in analysis.fields
            ],
            "missing_required": missing,
        },
        ensure_ascii=False,
        indent=2,
    )
    d3.download_button("⬇️ JSON", json_payload, file_name="filled_form.json", mime="application/json")

    st.divider()
    if st.button("📝 Fill another form"):
        reset_app()
        st.rerun()

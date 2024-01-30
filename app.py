import streamlit as st
from gen import read_docx, audio_transcript, split_pdf_to_chunks, read_document, translate_and_combine_text, convert_text_to_docx_bytes
import io
from docx import Document

st.title('Document Processor and Translator')

def save_custom_prompt(prompt):
    with open("custom_prompts.txt", "a") as file:
        file.write(prompt + "\n")

def load_custom_prompts():
    try:
        with open("custom_prompts.txt", "r") as file:
            return file.readlines()
    except FileNotFoundError:
        return []

saved_custom_prompts = load_custom_prompts()

file_types = {
    'MP3': ['mp3'],
    'DOC': ['docx'],
    'PDF': ['pdf']
}

if 'file_processed' not in st.session_state:
    st.session_state.file_processed = False
if 'transcript' not in st.session_state:
    st.session_state.transcript = ""
if 'translated_text' not in st.session_state:
    st.session_state.translated_text = ""
if 'source_language' not in st.session_state:
    st.session_state.source_language = ""
if 'target_language' not in st.session_state:
    st.session_state.target_language = ""

if 'file_processed' not in st.session_state:
    st.session_state.file_processed = False
if 'transcript' not in st.session_state:
    st.session_state.transcript = ""

option = st.selectbox('Choose the type of file to upload', list(file_types.keys()))

file = st.file_uploader("Upload a file", type=file_types[option])

edited_text = ""

if file and (not hasattr(st.session_state, 'last_uploaded_file') or file != st.session_state.last_uploaded_file):
    st.session_state.file_processed = False
    st.session_state.transcript = ""
    st.session_state.translated_text = ""
    st.session_state.source_language = ""
    st.session_state.target_language = ""
    st.session_state.last_uploaded_file = file

if file and not st.session_state.file_processed:
    if st.button('Transcribe'):
        if option == 'MP3':
            with st.spinner('Transcribing audio...'):
                st.session_state.transcript = audio_transcript(file)
                st.session_state.file_processed = True

        elif option == 'DOC':
            with st.spinner('Transcribing document...'):
                st.session_state.transcript = read_docx(file)
                st.session_state.file_processed = True

        elif option == 'PDF':
            pdf_chunks = list(split_pdf_to_chunks(file))
            extracted_text = ''
            for i, chunk in enumerate(pdf_chunks, start=1):
                with st.spinner(f'Transcribing page {i} of {len(pdf_chunks)}...'):
                    extracted_text += read_document(chunk)
            st.session_state.transcript = extracted_text
            st.session_state.file_processed = True

if st.session_state.file_processed:          
    edited_text = st.text_area("Content (Edit as needed)", st.session_state.transcript, height=600)
    source_language = st.text_input("Enter the source language:")
    target_language = st.text_input("Enter the target language:") 
    prompt_option = st.radio("Choose your prompt type", ["Use default prompt", "Enter custom prompt", "Use saved prompt"])
    custom_prompt = ""

    if prompt_option == "Enter custom prompt":
        custom_prompt = st.text_area("Enter your custom prompt:")
        if st.button("Save Custom Prompt"):
            save_custom_prompt(custom_prompt)
            saved_custom_prompts.append(custom_prompt)
            st.success("Custom prompt saved.")
    elif prompt_option == "Use saved prompt":
        custom_prompt = st.selectbox("Select a saved prompt", saved_custom_prompts)

    if st.button('Translate'):
        if edited_text:
            with st.spinner(f'Translating to {target_language}...'):
                if prompt_option == "Use default prompt":
                    # Use default prompt
                    prompt = f"""You are a professional translator. You have to translate the provided text into {target_language}. Remember to:
                    1) Keep the length of the translated text the same as original text.
                    2) Don't skip or leave any part of the text. All details are very important.
                    3) Identify the Name, Entities and don't translate them, just write them in {target_language}
                    4) Keep the format of the translated text the same as the orignal text.
                    5) You need to format the output as if it was a page of a book. Analyse the content and determine the format, It could be a table of content, title page, or page of a chapter. It should be formatted as that page.
                    6) Only return the translation of the text provided, Don't return anything else.
                    7) Don't return any text in the original language. Only return text in {target_language}
                    8) Identify the headings in the text and bold them
                    9) If you aren't given any text, just return a blank response. Don't return anything other than translated text or blank response"""
                else:
                    # Use custom prompt (entered or selected from saved prompts)
                    prompt = custom_prompt
                st.session_state.translated_text = translate_and_combine_text(edited_text, prompt, source_language, target_language)
        else:
            st.error("No text available to translate.")

    if 'translated_text' in st.session_state:
        st.session_state.translated_text = st.text_area("Edit the translation:", st.session_state.translated_text, height=600)
        if st.button("Generate Download Link"):
            docx_bytes = convert_text_to_docx_bytes(st.session_state.translated_text)
            st.download_button(
                label="Download Edited Translation",
                data=docx_bytes,
                file_name="edited_translation.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

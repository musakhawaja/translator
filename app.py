import streamlit as st
# from gen import read_docx, audio_transcript, split_pdf_to_chunks, read_document, translate_and_combine_text, convert_text_to_docx_bytes
import io
from docx import Document
import time
import re
import json 


from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import io
from PyPDF2 import PdfFileReader, PdfFileWriter
from openai import OpenAI
import json
from docx import Document
import base64
import re
import math
import tempfile
from pydub import AudioSegment
import os
from dotenv import load_dotenv
load_dotenv()
client = OpenAI(api_key = os.getenv('OPENAI_API_KEY'))

def format_timestamp(seconds):
    """Helper function to format timestamps."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

def read_docx(file_path):
    doc = Document(file_path)
    full_text = ""
    char_count = 0

    for para in doc.paragraphs:
        para_text = para.text + "\n"
        full_text += para_text
        char_count += len(para_text)

        if char_count >= 3000:
            full_text += "\n--EndOfPage--\n\n"
            char_count = 0  
    return full_text.strip()

def audio_transcript(audio_file):
    audio = AudioSegment.from_file(audio_file)
    length_audio = len(audio) / 1000  # Convert to seconds
    full_transcription = ""
    if length_audio <= 60:
        start_seconds = 0 * 60
        end_seconds = min((0 + 1) * 60, length_audio)
        start = 0 * 60 * 1000  # Convert to milliseconds for slicing
        end = min((0 + 1) * 60 * 1000, len(audio))
        transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
        # full_transcription = transcription.strip()
        timestamp = f"Start:[{format_timestamp(start_seconds)}] End:[{format_timestamp(end_seconds)}]"
        full_transcription += f"{timestamp}\n{transcription.strip()}\n\n--EndOfPage--\n\n"
    else:
        for i in range(0, math.ceil(length_audio / 60)):
            start_seconds = i * 60
            end_seconds = min((i + 1) * 60, length_audio)
            start = i * 60 * 1000  # Convert to milliseconds for slicing
            end = min((i + 1) * 60 * 1000, len(audio))
            chunk = audio[start:end]
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
                chunk.export(temp_file.name, format="wav")
                transcription = client.audio.transcriptions.create(model="whisper-1", file=open(temp_file.name, 'rb'), response_format="text")
                timestamp = f"Start:[{format_timestamp(start_seconds)}] End:[{format_timestamp(end_seconds)}]"
                full_transcription += f"{timestamp}\n{transcription.strip()}\n\n--EndOfPage--\n\n"

    print(full_transcription)
    return full_transcription

def split_pdf_to_chunks(uploaded_file, pages_per_chunk=3):
    file_stream = io.BytesIO(uploaded_file.getvalue())
    reader = PdfFileReader(file_stream)
    total_pages = reader.getNumPages()
    temp_files = []  #

    for start_page in range(0, total_pages, pages_per_chunk):
        writer = PdfFileWriter()
        end_page = min(start_page + pages_per_chunk, total_pages)

        for page_number in range(start_page, end_page):
            writer.addPage(reader.getPage(page_number))
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        writer.write(temp_file)
        temp_file.close()  
        temp_files.append(temp_file.name) 

    return temp_files

def read_document(temp_file_path):
    credentials = service_account.Credentials.from_service_account_file("ocrproject-412113-82a31889338f.json")
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)
    name = "projects/707177808576/locations/us/processors/6eebcb4a15b88393"
    
    all_structured_text = ""  # Initialize a variable to store all structured text from all documents

    with open(temp_file_path, "rb") as chunk:
        content = chunk.read()
        raw_document = documentai.RawDocument(content=content, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = client.process_document(request=request)
        document = result.document

        structured_text = ""
        for page in document.pages:
            rows = {}
            for block in page.blocks:
                y_coord = block.layout.bounding_poly.vertices[0].y
                if y_coord not in rows:
                    rows[y_coord] = []
                block_text = document.text[block.layout.text_anchor.text_segments[0].start_index:
                                            block.layout.text_anchor.text_segments[0].end_index]
                rows[y_coord].append((block.layout.bounding_poly.vertices[0].x, block_text))

            for y_coord in sorted(rows.keys()):
                row = sorted(rows[y_coord], key=lambda x: x[0])
                row_text = '\t'.join([text for _, text in row])
                structured_text += row_text + "\n"

            structured_text += "--EndOfPage--\n\n"
        
        all_structured_text += structured_text  # Append the structured text from the current document

    # Delete the temporary file after processing
    os.remove(temp_file_path)

    return all_structured_text

def translate(file_path, prompt, source_lang="English", target_lang="Urdu"):
    with open(file_path, 'r', encoding='utf-8') as file:
        text = file.read()

    completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )

    result = completion.choices[0].message.content
    print(result)
    return result
    
def translate_and_combine_text(edited_text, prompt, source_lang, target_lang):
    pages = edited_text.split("--EndOfPage--")
    temp_file_paths = []
    translated_texts = []

    # Save each page to a temp file
    for page in pages:
        with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding='utf-8', suffix=".txt") as temp_file:
            temp_file.write(page)
            temp_file_paths.append(temp_file.name)

    # Translate each temp file
    for file_path in temp_file_paths:
        translated_text = translate(file_path, prompt, source_lang, target_lang)
        translated_texts.append(translated_text)

    # Combine translated texts
    combined_translated_text = "\n\n".join(translated_texts)

    # Cleanup: delete temp files
    for file_path in temp_file_paths:
        os.remove(file_path)

    return combined_translated_text

def convert_text_to_docx_bytes(text):
    doc = Document()
    lines = text.split('\n')
    for line in lines:
        paragraph = doc.add_paragraph()
        parts = re.split(r'(\*\*.*?\*\*)', line)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run = paragraph.add_run(part[2:-2]) 
                run.bold = True
            else:
                paragraph.add_run(part)

    docx_io = io.BytesIO()
    doc.save(docx_io)
    docx_io.seek(0)
    return docx_io









st.title('Document Processor and Translator')

def save_last_state(data, filename="last_state.json"):
    """Saves the last transcription and translation to a file."""
    with open(filename, "w") as file:
        json.dump(data, file)

def load_last_state(filename="last_state.json"):
    """Loads the last transcription and translation from a file."""
    try:
        with open(filename, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_custom_prompt(display_name, prompt_text):
    prompts = load_custom_prompts()  # Ensure this returns a dictionary
    prompts[display_name] = prompt_text  # Assign the prompt text to the display name key
    with open("custom_prompts.json", "w") as file:
        json.dump(prompts, file)  # Save the updated dictionary back to the JSON file

def load_custom_prompts():
    try:
        with open("custom_prompts.json", "r") as file:
            return json.load(file)  # Load and return a dictionary
    except (FileNotFoundError, json.JSONDecodeError):
        return {} 
    
def display_time_taken(process_name):
    """Function to display the time taken for a process in a human-readable format."""
    time_taken = st.session_state.get(f'{process_name}_time', None)
    if time_taken:
        if time_taken > 60:
            time_str = f"{time_taken / 60:.2f} minutes"
        else:
            time_str = f"{time_taken:.2f} seconds"
        st.info(f"{process_name.replace('_', ' ').capitalize()} completed in {time_str}.")


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
if 'translation_time' not in st.session_state:
    st.session_state.translation_time = ""
if 'transcription_time' not in st.session_state:
    st.session_state.transcription_time = ""



option = st.selectbox('Choose the type of file to upload', list(file_types.keys()))

file = st.file_uploader("Upload a file", type=file_types[option])

edited_text = ""

if file and (not hasattr(st.session_state, 'last_uploaded_file') or file != st.session_state.last_uploaded_file):
    st.session_state.file_processed = False
    st.session_state.transcript = ""
    st.session_state.translated_text = ""
    st.session_state.source_language = ""
    st.session_state.target_language = ""
    st.session_state.translation_time = ""
    st.session_state.transcription_time= ""
    st.session_state.last_uploaded_file = file

if file and not st.session_state.file_processed:
    if st.button('Transcribe'):
        start_time = time.time()
        if option == 'MP3':
            with st.spinner('Transcribing audio...'):
                st.session_state.transcript = audio_transcript(file)
                st.session_state.file_processed = True

        elif option == 'DOC':
            with st.spinner('Transcribing document...'):
                st.session_state.transcript = read_docx(file)
                st.session_state.file_processed = True

        elif option == 'PDF':
            temp_file_paths = split_pdf_to_chunks(file)
            print("Temp file paths:", temp_file_paths)  # This now returns a list of temp file paths
            extracted_texts = []

            
            for i, temp_file_path in enumerate(temp_file_paths, start=1):
                try:
                    with st.spinner(f'Transcribing page {i}-{i+3} of {len(temp_file_paths)*3}...'):
                        extracted_text = read_document(temp_file_path)  # read_document now processes a file path
                        extracted_texts.append(extracted_text)
                        # Cleanup: delete the temporary file after processing
                except Exception as e:
                    st.error(f"An error occurred while processing file {i}: {temp_file_path}. Error: {e}")
                    print(f"An error occurred while processing file {i}: {temp_file_path}. Error: {e}")
                    continue  # Skip the current file and continue with the next

            st.session_state.transcript = "\n\n".join(extracted_texts)
            st.session_state.file_processed = True
        st.session_state['transcription_time'] = time.time() - start_time  # End timing
display_time_taken('transcription')
save_last_state({'transcript': st.session_state['transcript']})
if st.session_state.file_processed:          
    edited_text = st.text_area("Content (Edit as needed)", st.session_state.transcript, height=600)
    source_language = st.text_input("Enter the source language:")
    target_language = st.text_input("Enter the target language:") 
    prompt_option = st.radio("Choose your prompt type", ["Use default prompt", "Enter custom prompt", "Use saved prompt"])

    if option == "MP3":
        timestamp_pattern = r"Start:\[\d{2}:\d{2}:\d{2}\] End:\[\d{2}:\d{2}:\d{2}\]\n"
        processed_transcript = re.sub(timestamp_pattern, '', edited_text)
        edited_text = processed_transcript

    
    if prompt_option == "Enter custom prompt":
        display_name = st.text_input("Enter a name for your custom prompt:")
        custom_prompt = st.text_area("Enter your custom prompt:")
        if st.button("Save Custom Prompt"):
            save_custom_prompt(display_name, custom_prompt)
            st.success("Custom prompt saved.")
    elif prompt_option == "Use saved prompt":
        selected_name = st.selectbox("Select a saved prompt", list(saved_custom_prompts.keys()))
        custom_prompt = st.text_area("Edit your custom prompt:", value=saved_custom_prompts[selected_name])
        if st.button("Update Custom Prompt"):
            save_custom_prompt(selected_name, custom_prompt)
            st.success(f"Custom prompt '{selected_name}' updated.")

    if st.button('Translate'):
        start_time = time.time()
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
        st.session_state['translation_time'] = time.time() - start_time  # End timing
    display_time_taken('translation')
    save_last_state({
        'transcript': st.session_state['transcript'],
        'translated_text': st.session_state['translated_text']
    })
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


    if st.button('Load Last State'):
        last_state = load_last_state()
        if last_state:
            if 'transcript' in last_state:
                st.session_state.transcript = last_state.get('transcript', "")
                # Update the text area for transcription directly
                edited_text = st.text_area("Content (Edit as needed)", value=st.session_state.transcript, height=300)
            if 'translated_text' in last_state:
                st.session_state.translated_text = last_state.get('translated_text', "")
                # Update the text area for translation directly
                translated_text_area = st.text_area("Translated Text", value=st.session_state.translated_text, height=300)
            st.success("Last state loaded successfully.")
        else:
            st.error("No saved state found.")

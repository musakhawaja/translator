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
    length_audio = len(audio) / 1000
    full_transcription = ""
    if length_audio <= 60:
        transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
        full_transcription = transcription.strip()
    else:
        for i in range(0, math.ceil(length_audio / 60)):
            start = i * 60 * 1000  
            end = min((i + 1) * 60 * 1000, len(audio))
            chunk = audio[start:end]
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
                chunk.export(temp_file.name, format="wav")
                transcription = client.audio.transcriptions.create(model="whisper-1", file=open(temp_file.name, 'rb'), response_format="text")
                full_transcription += transcription.strip() + " "
                full_transcription+= "\n--EndOfPage--\n\n"

    print(full_transcription)
    return full_transcription


def split_pdf_to_chunks(uploaded_file, pages_per_chunk=1):
    file_stream = io.BytesIO(uploaded_file.getvalue())
    reader = PdfFileReader(file_stream)
    total_pages = reader.getNumPages()

    for start_page in range(0, total_pages, pages_per_chunk):
        writer = PdfFileWriter()
        end_page = min(start_page + pages_per_chunk, total_pages)
        for page_number in range(start_page, end_page):
            writer.addPage(reader.getPage(page_number))
        chunk_file = io.BytesIO()
        writer.write(chunk_file)
        chunk_file.seek(0)  
        yield chunk_file

def read_document(chunk):
    credentials = service_account.Credentials.from_service_account_file("ocrproject-412113-82a31889338f.json")
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)
    name = "projects/707177808576/locations/us/processors/6eebcb4a15b88393"

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

    return structured_text


def translate(text, prompt, source_lang = "English", target_lang="Urdu"):
  completion = client.chat.completions.create(
  model="gpt-4",
  messages=[{"role": "system", "content": prompt},
            {"role": "user", "content": text}]
)

  result = completion.choices[0].message.content
  print(result)
  return result
    
def translate_and_combine_text(edited_text, prompt, source_lang, target_lang):
    pages = edited_text.split("--EndOfPage--")
    translated_pages = [translate(page, prompt, source_lang, target_lang) for page in pages]
    combined_translated_text = "\n\n".join(translated_pages)

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


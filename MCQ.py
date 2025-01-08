import streamlit as st
import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

# Load environment variables
load_dotenv()

# Configure GenerativeAI with Google API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Set up pytesseract path (update this path according to your system)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def extract_text_from_pdf(pdf_file_path):
    text = ""
    with fitz.open(pdf_file_path) as doc:
        for page in doc:
            text += page.get_text()

            # Extract images and perform OCR
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]

                # Perform OCR on the image
                image = Image.open(io.BytesIO(image_bytes))
                ocr_text = pytesseract.image_to_string(image)
                text += f"\n[Image Content: {ocr_text}]\n"

    return text


def generate_mcq_questions_and_answers_from_pdf(pdf_file_path, difficulty, num_questions):
    # Extract text from PDF (including OCR on images)
    try:
        pdf_text = extract_text_from_pdf(pdf_file_path)
    except Exception as e:
        st.error(f"Error reading PDF file: {e}")
        return None, None

    # Format for MCQ questions
    Ans_format = """
    Please generate an Answer Key in the following Format:
    ## Answer Key:
    **Q{question_number}. {correct_option} , Q{question_number}. {correct_option} ,**
    """

    q_format = """
    Please generate multiple choice questions in the following format:

    **Question No. {question_number}:** {question}

    a. {option_a}
    b. {option_b}
    c. {option_c}
    d. {option_d}

    Based on the given text only: {text}
    """

    # Define the prompt based on the difficulty level
    difficulty_prompt = {
        "Easy": f"Please generate {num_questions} easy MCQ questions. {q_format}{Ans_format}{pdf_text}",
        "Medium": f"Please generate {num_questions} moderate MCQ questions. {q_format}{Ans_format}{pdf_text}",
        "Hard": f"Please generate {num_questions} hard MCQ questions. {q_format}{Ans_format}{pdf_text}"
    }

    prompt = difficulty_prompt.get(difficulty)
    if not prompt:
        st.error("Invalid difficulty level. Please choose from 'Easy', 'Medium', or 'Hard'.")
        return None, None

    # Initialize GenerativeModel
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        model_response = response.text if response else None
    except Exception as e:
        st.error(f"Error generating questions: {e}")
        return None, None

    # Validate model response
    if not model_response:
        st.error("Failed to generate content. Please check your API key or model configuration.")
        return None, None

    # Clean the generated text
    cleaned_text = re.sub(r'[*#]', '', model_response)
    start_index = cleaned_text.find("Answer Key")
    if start_index == -1:
        st.error("Failed to find 'Answer Key' in the response. Check the model's output.")
        return None, None

    # Split into questions and answer key
    generated_que = cleaned_text[:start_index]
    answer_key = cleaned_text[start_index:]
    questions = generated_que.split("Question No. ")[1:]  # Split into individual questions
    key_answers = answer_key.split(", ")  # Split answer key

    return questions, key_answers


# Streamlit UI
st.title("Enhanced PDF to MCQ Generator")

# File uploader
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

difficulty = st.selectbox("Select Difficulty Level", ["Easy", "Medium", "Hard"])
num_questions = st.number_input("Number of Questions", min_value=1, max_value=20, value=5)

if uploaded_file is not None:
    pdf_file_path = os.path.join("data", uploaded_file.name)
    with open(pdf_file_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    if st.button("Generate MCQ"):
        questions, key_answers = generate_mcq_questions_and_answers_from_pdf(pdf_file_path, difficulty, num_questions)

        if questions and key_answers:
            st.write("### Generated Questions")
            for idx, question in enumerate(questions, start=1):
                st.write(f"**{idx}.** {question}")

            st.write("### Answer Key")
            for answer in key_answers:
                st.write(f"**{answer}**")
        else:
            st.error("Failed to generate questions. Please try again.")

import streamlit as st

# Set the page config at the very start
st.set_page_config(page_title="MCQ Generator", page_icon="📝", layout="wide")
import re
import random
import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from MCQ import generate_mcq_questions_and_answers_from_pdf
import base64
from email.mime.text import MIMEText
import datetime
from typing import Dict, List, Tuple

# Google Forms and Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/forms.body',
          'https://www.googleapis.com/auth/gmail.send']


def authenticate_google():
    """Authenticate with Google API."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json',
                SCOPES,
                redirect_uri='http://localhost:8080'
            )
            creds = flow.run_local_server(port=8080)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def create_google_form(form_title: str, questions: List[str], answers: List[str]) -> Tuple[str, str, Dict]:
    """Create Google Form with quiz features, automatic grading, and answer feedback."""
    try:
        creds = authenticate_google()
        service = build('forms', 'v1', credentials=creds)

        # Create the basic form first
        form_body = {
            "info": {
                "title": form_title,
                "documentTitle": form_title
            }
        }
        form = service.forms().create(body=form_body).execute()
        form_id = form['formId']

        # Enable quiz feature with advanced settings
        quiz_settings = {
            "requests": [
                {
                    "updateSettings": {
                        "settings": {
                            "quizSettings": {
                                "isQuiz": True
                            }
                        },
                        "updateMask": "quizSettings"
                    }
                }
            ]
        }

        service.forms().batchUpdate(formId=form_id, body=quiz_settings).execute()

        # Process questions and create form items
        form_update = {"requests": []}

        # Add student information fields at the start
        student_info_fields = [
            {
                "title": "Full Name",
                "questionItem": {
                    "question": {
                        "required": True,
                        "textQuestion": {
                            "paragraph": False
                        }
                    }
                }
            },
            {
                "title": "Roll Number",
                "questionItem": {
                    "question": {
                        "required": True,
                        "textQuestion": {
                            "paragraph": False
                        }
                    }
                }
            },
            {
                "title": "Section",
                "questionItem": {
                    "question": {
                        "required": True,
                        "textQuestion": {
                            "paragraph": False
                        }
                    }
                }
            },
            {
                "title": "Email Address",
                "questionItem": {
                    "question": {
                        "required": True,
                        "textQuestion": {
                            "paragraph": False
                        }
                    }
                }
            }
        ]

        # Add student info fields to form
        for index, field in enumerate(student_info_fields):
            form_update["requests"].append({
                "createItem": {
                    "item": field,
                    "location": {"index": index}
                }
            })

        def extract_answer_index(answer: str) -> int:
            """Extract the answer index (0-3) from the answer string."""
            # Clean and normalize the answer string
            cleaned_answer = answer.strip().lower()
            # Remove any "Q1.", "Q2." etc. prefix
            cleaned_answer = re.sub(r'^q\d+\.?\s*', '', cleaned_answer)

            if not cleaned_answer:
                return 0
            if len(cleaned_answer) == 1 and cleaned_answer in 'abcd':
                return ord(cleaned_answer) - ord('a')
            if cleaned_answer.startswith(('a.', 'b.', 'c.', 'd.')):
                return ord(cleaned_answer[0]) - ord('a')
            if cleaned_answer.isdigit() and 1 <= int(cleaned_answer) <= 4:
                return int(cleaned_answer) - 1
            return 0

        # Add quiz questions with correct answers, points, and feedback
        start_index = len(student_info_fields)  # Start after student info fields
        for i, (question, answer) in enumerate(zip(questions, answers), start=1):
            try:
                question_parts = question.split('\n')
                question_text = question_parts[0].strip()
                options = [part.strip()[3:] for part in question_parts[1:] if
                           part.strip().startswith(('a.', 'b.', 'c.', 'd.'))]

                if not options:
                    continue

                correct_index = extract_answer_index(answer)
                if correct_index >= len(options):
                    correct_index = 0

                # Create question with feedback
                question_request = {
                    "createItem": {
                        "item": {
                            "title": question_text,
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [{"value": option} for option in options],
                                        "shuffle": True
                                    },
                                    "grading": {
                                        "pointValue": 1,
                                        "correctAnswers": {
                                            "answers": [{"value": options[correct_index]}]
                                        },
                                        "whenRight": {
                                            "text": "Correct! Well done!"
                                        },
                                        "whenWrong": {
                                            "text": f"The correct answer is: {options[correct_index]}"
                                        }
                                    }
                                }
                            }
                        },
                        "location": {"index": start_index + i - 1}
                    }
                }
                form_update["requests"].append(question_request)

            except Exception as e:
                st.warning(f"Skipping question {i} due to formatting error: {str(e)}")
                continue

        # Apply all updates
        service.forms().batchUpdate(formId=form_id, body=form_update).execute()

        # Final settings to configure response behavior
        final_settings = {
            "requests": [
                {
                    "updateSettings": {
                        "settings": {
                            "quizSettings": {
                                "isQuiz": True
                            }
                        },
                        "updateMask": "quizSettings"
                    }
                }
            ]
        }

        service.forms().batchUpdate(formId=form_id, body=final_settings).execute()

        # Get the form URL
        form_result = service.forms().get(formId=form_id).execute()
        form_url = form_result.get('responderUri')

        return form_id, form_url, None

    except Exception as e:
        st.error(f"Error creating Google Form: {str(e)}")
        if hasattr(e, 'content'):
            st.error(f"API Error Details: {e.content}")
        return None, None, None


def send_email(to, subject, body):
    """Send email using Gmail API."""
    try:
        creds = authenticate_google()
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        send_message = service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
        return send_message
    except Exception as e:
        st.error(f"Error sending email: {str(e)}")
        return None


def main():
    st.title("AI-DRIVEN-QUIZ-GENERATOR")

    st.write("""
    ### About
    This application generates quizzes from PDF content using AI and creates an interactive Google Form.
    Students will receive immediate feedback and scores after submission.
    """)

    # File upload and quiz configuration
    pdf_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    col1, col2 = st.columns(2)
    with col1:
        num_questions = st.number_input("Number of questions", min_value=1, max_value=20, value=5)
    with col2:
        difficulty_level = st.selectbox("Difficulty level", ["Easy", "Medium", "Hard"])

    student_emails = st.text_area("Student email addresses (one per line)")

    if st.button("Generate Quiz and Send"):
        if not pdf_file:
            st.error("Please upload a PDF file.")
            return
        if not student_emails.strip():
            st.error("Please enter at least one student email address.")
            return

        with st.spinner("Generating quiz questions..."):
            questions, answers = generate_mcq_questions_and_answers_from_pdf(
                pdf_file.name, difficulty_level, num_questions
            )

            if questions and answers:
                form_title = f"Quiz: {pdf_file.name} - {difficulty_level} Level"
                form_id, form_url, _ = create_google_form(form_title, questions, answers)

                if form_url:
                    st.success("Quiz created successfully!")
                    st.write("### Quiz Details")
                    st.write(f"Form URL: {form_url}")

                    # Send emails to students
                    with st.spinner("Sending emails to students..."):
                        successful_sends = 0
                        for email in student_emails.strip().split('\n'):
                            email = email.strip()
                            if email:
                                email_subject = f"New Quiz: {form_title}"
                                email_body = f"""
                                Hello,

                                A new quiz has been created for you.

                                Please complete the quiz using the following link:
                                {form_url}

                                Important:
                                - Fill in your full name, roll number, and section carefully
                                - Complete all questions
                                - You will see your score immediately after submission
                                - You will get feedback for each question
                                - You will see the correct answers for any questions you missed

                                Good luck!
                                """
                                if send_email(email, email_subject, email_body):
                                    successful_sends += 1

                        st.success(f"✉️ Sent quiz invitations to {successful_sends} students")
                else:
                    st.error("Failed to create the quiz. Please try again.")
            else:
                st.error("Failed to generate questions. Please try again with a different PDF or settings.")


if __name__ == "__main__":
    main()
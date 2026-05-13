import os
import uuid
import shutil
from typing import List
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from sqlmodel import Session
from docling.document_converter import DocumentConverter
import instructor
from pydantic import BaseModel
import openai
import google.generativeai as genai
from .db import init_db, get_session
from .models import Session as SessionModel, Interaction as InteractionModel
from .retrieval import (
    generate_search_query, 
    search_qdrant, 
    generate_question, 
    grade_answer
)

from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

class ResumeAnalysis(BaseModel):
    skills: List[str]
    technologies: List[str]
    domain_exposure: List[str]

app = FastAPI(title="Resume RAG API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

def get_llm_client():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    
    base_client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/Antigravity",
            "X-Title": "Resume RAG API",
        }
    )
    return instructor.from_openai(base_client)

@app.post("/upload_resume")
async def upload_resume(
    target_role: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session)
):
    """
    Uploads a PDF resume, extracts text using Docling,
    analyzes it with Gemini + Instructor, and saves to the Session table.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

    client = get_llm_client()
    if not client:
        raise HTTPException(status_code=500, detail="LLM configuration missing (OPENROUTER_API_KEY).")

    temp_dir = "data/raw"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"temp_{uuid.uuid4()}.pdf")
    
    # Ensure we are at the start of the file stream
    await file.seek(0)
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_size = os.path.getsize(temp_path)
    print(f"Saved uploaded file to {temp_path} ({file_size} bytes)")
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        print(f"Extracting text from {file.filename}...")
        converter = DocumentConverter()
        doc_result = converter.convert(temp_path)
        markdown_text = doc_result.document.export_to_markdown()
        
        print(f"--- DEBUG: Markdown Text Length: {len(markdown_text)} ---")
        if len(markdown_text.strip()) == 0:
            print("CRITICAL: extracted markdown is EMPTY. OCR failed.")
            raise HTTPException(
                status_code=500, 
                detail="Resume extraction failed: The document appeared empty or OCR failed to read it. Please try a different PDF format."
            )

        print(f"--- DEBUG: Markdown Text Start ---\n{markdown_text[:500]}...\n--- DEBUG: Markdown Text End ---")

        print(f"Analyzing resume with model: {os.getenv('OPENROUTER_MODEL', 'openai/gpt-oss-120b:free')}...")
        try:
            analysis = client.chat.completions.create(
                model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
                response_model=ResumeAnalysis,
                messages=[
                    {"role": "user", "content": f"Analyze the following resume and extract the candidate's skills, technologies, and domain exposure:\n\n{markdown_text}"}
                ]
            )
        except Exception as llm_error:
            print(f"LLM Error during analysis: {str(llm_error)}")
            # Fallback or re-raise with more context
            raise HTTPException(
                status_code=500, 
                detail=f"LLM analysis failed. This model ({os.getenv('OPENROUTER_MODEL')}) might not support structured output reliably. Error: {str(llm_error)}"
            )

        new_session = SessionModel(
            session_id=str(uuid.uuid4()),
            candidate_skills=analysis.skills,
            candidate_technologies=analysis.technologies,
            candidate_domain=analysis.domain_exposure,
            target_role=target_role
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        return {
            "status": "success",
            "session_id": new_session.session_id,
            "data": analysis.model_dump()
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

class AnswerSubmission(BaseModel):
    session_id: str
    candidate_answer: str

@app.get("/interaction_status/{interaction_id}")
async def get_interaction_status(interaction_id: str, db: Session = Depends(get_session)):
    """
    Polls the status of an interaction (start_interview or submit_answer).
    """
    interaction = db.query(InteractionModel).filter(InteractionModel.interaction_id == interaction_id).first()
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    
    if interaction.status == "processing":
        return {"status": "processing"}
    
    if interaction.status == "failed":
        return {"status": "failed", "error": "Processing failed. Please retry."}

    # If it's ready, we check if there's a previous interaction to get evaluation from
    prev_interaction = db.query(InteractionModel).filter(
        InteractionModel.session_id == interaction.session_id,
        InteractionModel.id < interaction.id
    ).order_by(InteractionModel.id.desc()).first()

    if not prev_interaction:
        # This is the very first question (start_interview flow)
        return {
            "status": "ready",
            "question": interaction.generated_question,
            "interaction_id": interaction.interaction_id
        }
    
    # This is a follow-up turn (submit_answer flow)
    return {
        "status": "ready",
        "evaluation": {
            "score": prev_interaction.score,
            "feedback": prev_interaction.feedback,
            "routing": prev_interaction.routing_action
        },
        "next_question": interaction.generated_question,
        "interaction_id": interaction.interaction_id
    }

async def process_start_interview_task(interaction_id: str, session_db_id: int, target_role: str, resume_data: dict):
    # We need a new session for the background task
    from .db import engine
    from sqlmodel import Session
    with Session(engine) as db:
        try:
            interaction = db.query(InteractionModel).filter(InteractionModel.interaction_id == interaction_id).first()
            if not interaction: return

            print(f"Background: Generating first question for interaction {interaction_id}...")
            query = generate_search_query(resume_data, target_role, [])
            hit = search_qdrant(query)
            
            if not hit:
                interaction.status = "failed"
                db.commit()
                return

            question = generate_question(hit.payload["text"], resume_data)
            
            interaction.generated_question = question
            interaction.reference_chunk = hit.payload["text"]
            interaction.source_book = hit.payload.get("source_book", "Unknown")
            interaction.section_header = hit.payload.get("section_header", "Unknown")
            interaction.status = "ready"
            db.commit()
            print(f"Background: Completed start_interview for {interaction_id}")
        except Exception as e:
            print(f"Background Error in start_interview: {str(e)}")
            db.rollback()
            try:
                interaction = db.query(InteractionModel).filter(InteractionModel.interaction_id == interaction_id).first()
                if interaction:
                    interaction.status = "failed"
                    db.commit()
            except Exception as inner_e:
                print(f"Failed to mark start_interview interaction as failed: {str(inner_e)}")

@app.post("/start_interview", status_code=202)
async def start_interview(session_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_session)):
    """
    Initializes the interview asynchronously. Returns 202 Accepted.
    """
    session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    resume_data = {
        "skills": session.candidate_skills,
        "technologies": session.candidate_technologies,
        "domain_exposure": session.candidate_domain
    }
    
    interaction_uuid = str(uuid.uuid4())
    new_interaction = InteractionModel(
        interaction_id=interaction_uuid,
        session_id=session.id,
        status="processing",
        drill_down_count=0
    )
    db.add(new_interaction)
    db.commit()
    
    background_tasks.add_task(
        process_start_interview_task, 
        interaction_uuid, 
        session.id, 
        session.target_role, 
        resume_data
    )
    
    return {
        "status": "processing",
        "interaction_id": interaction_uuid
    }

async def process_submit_answer_task(
    interaction_id: str, 
    session_db_id: int, 
    candidate_answer: str,
    resume_data: dict,
    target_role: str,
    previous_interaction_db_id: int
):
    from .db import engine
    from sqlmodel import Session
    with Session(engine) as db:
        try:
            interaction = db.query(InteractionModel).filter(InteractionModel.interaction_id == interaction_id).first()
            prev_interaction = db.query(InteractionModel).filter(InteractionModel.id == previous_interaction_db_id).first()
            if not interaction or not prev_interaction: 
                print(f"Background: Interaction(s) not found for ID {interaction_id} or DB ID {previous_interaction_db_id}")
                return

            print(f"Background: Grading answer for previous interaction {prev_interaction.interaction_id}...")
            grade = grade_answer(
                prev_interaction.generated_question,
                prev_interaction.reference_chunk,
                candidate_answer
            )
            
            # 1. Update PREVIOUS interaction with the answer and grade
            prev_interaction.candidate_answer = candidate_answer
            prev_interaction.score = grade.score
            prev_interaction.feedback = grade.feedback
            prev_interaction.routing_action = grade.routing_action
            prev_interaction.focus_concept = grade.focus_concept
            
            routing = grade.routing_action
            focus = grade.focus_concept
            
            # Calculate drill down for the NEXT question based on the PREVIOUS turn
            if routing == "DRILL_DOWN":
                if prev_interaction.drill_down_count >= 2:
                    routing = "NEXT_TOPIC"
                    focus = None
                    next_drill_count = 0
                else:
                    next_drill_count = prev_interaction.drill_down_count + 1
            else:
                next_drill_count = 0
            
            # Get previous topics for the search query
            session = db.query(SessionModel).filter(SessionModel.id == session_db_id).first()
            previous_topics = [i.section_header for i in session.interactions if i.section_header and i.status == "ready"]

            print(f"Background: Generating next question for new interaction {interaction_id}...")
            next_query = generate_search_query(resume_data, target_role, previous_topics, focus)
            next_hit = search_qdrant(next_query)
            
            if not next_hit:
                # Fallback search
                next_hit = search_qdrant(generate_search_query(resume_data, target_role, previous_topics))
            
            if not next_hit:
                print("Background: Failed to find relevant content for next question.")
                interaction.status = "failed"
                db.commit()
                return

            next_question = generate_question(next_hit.payload["text"], resume_data)
            
            # 2. Update NEW interaction with the next question
            interaction.generated_question = next_question
            interaction.reference_chunk = next_hit.payload["text"]
            interaction.source_book = next_hit.payload.get("source_book", "Unknown")
            interaction.section_header = next_hit.payload.get("section_header", "Unknown")
            interaction.drill_down_count = next_drill_count
            interaction.status = "ready"
            
            # Single atomic commit for both interactions
            db.commit()
            print(f"Background: Successfully updated both interactions for {interaction_id}")

        except Exception as e:
            print(f"Background Error in submit_answer: {str(e)}")
            # CRITICAL: Rollback ensures that if generation fails, the grade/answer for prev_interaction 
            # is NOT committed. This keeps prev_interaction 'active' so the user can retry submit_answer.
            db.rollback()
            
            try:
                # Mark only the current interaction as failed so the poller knows to stop
                interaction = db.query(InteractionModel).filter(InteractionModel.interaction_id == interaction_id).first()
                if interaction:
                    interaction.status = "failed"
                    db.commit()
            except Exception as inner_e:
                print(f"Failed to mark interaction as failed: {str(inner_e)}")

@app.post("/submit_answer", status_code=202)
async def submit_answer(
    submission: AnswerSubmission, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_session)
):
    """
    Processes the answer and prepares the next question asynchronously. Returns 202 Accepted.
    """
    session = db.query(SessionModel).filter(SessionModel.session_id == submission.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Find the interaction that was JUST completed (the one that had the question)
    last_interaction = db.query(InteractionModel).filter(
        InteractionModel.session_id == session.id,
        InteractionModel.candidate_answer == None,
        InteractionModel.status == "ready"
    ).order_by(InteractionModel.id.desc()).first()
    
    if not last_interaction:
        raise HTTPException(status_code=400, detail="No active question found to answer.")
    
    interaction_uuid = str(uuid.uuid4())
    # This new interaction will hold the evaluation of the LAST answer AND the NEXT question
    new_interaction = InteractionModel(
        interaction_id=interaction_uuid,
        session_id=session.id,
        status="processing"
    )
    db.add(new_interaction)
    db.commit()

    resume_data = {
        "skills": session.candidate_skills,
        "technologies": session.candidate_technologies,
        "domain_exposure": session.candidate_domain
    }

    background_tasks.add_task(
        process_submit_answer_task,
        interaction_uuid,
        session.id,
        submission.candidate_answer,
        resume_data,
        session.target_role,
        last_interaction.id
    )
    
    return {
        "status": "processing",
        "interaction_id": interaction_uuid
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

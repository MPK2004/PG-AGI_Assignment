import os
import uuid
import shutil
from typing import List
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
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

class ResumeAnalysis(BaseModel):
    skills: List[str]
    technologies: List[str]
    domain_exposure: List[str]

app = FastAPI(title="Resume RAG API")

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
        raise HTTPException(status_code=500, detail="LLM configuration missing (GOOGLE_API_KEY).")

    temp_dir = "data/raw"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"temp_{uuid.uuid4()}.pdf")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        print(f"Extracting text from {file.filename}...")
        converter = DocumentConverter()
        doc_result = converter.convert(temp_path)
        markdown_text = doc_result.document.export_to_markdown()

        print(f"Analyzing resume with model: {os.getenv('OPENROUTER_MODEL')}...")
        analysis = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
            response_model=ResumeAnalysis,
            messages=[
                {"role": "user", "content": f"Analyze the following resume and extract the candidate's skills, technologies, and domain exposure:\n\n{markdown_text}"}
            ]
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

@app.post("/start_interview")
async def start_interview(session_id: str, db: Session = Depends(get_session)):
    """
    Initializes the interview by generating the first question based on the resume.
    """
    session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    resume_data = {
        "skills": session.candidate_skills,
        "technologies": session.candidate_technologies,
        "domain_exposure": session.candidate_domain
    }
    print(f"Generating first question for session {session_id}...")
    query = generate_search_query(resume_data, session.target_role, [])
    
    hit = search_qdrant(query)
    if not hit:
        raise HTTPException(status_code=500, detail="Could not find relevant textbook material for the initial topic.")
    
    question = generate_question(hit.payload["text"], resume_data)
    
    new_interaction = InteractionModel(
        interaction_id=str(uuid.uuid4()),
        session_id=session.id,
        generated_question=question,
        reference_chunk=hit.payload["text"],
        source_book=hit.payload.get("source_book", "Unknown"),
        section_header=hit.payload.get("section_header", "Unknown"),
        drill_down_count=0
    )
    db.add(new_interaction)
    db.commit()
    
    return {
        "status": "success",
        "question": question, 
        "interaction_id": new_interaction.interaction_id
    }

@app.post("/submit_answer")
async def submit_answer(submission: AnswerSubmission, db: Session = Depends(get_session)):
    """
    Grades the candidate's answer and orchestrates the next step (Drill Down or Next Topic).
    """
    session = db.query(SessionModel).filter(SessionModel.session_id == submission.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    last_interaction = db.query(InteractionModel).filter(
        InteractionModel.session_id == session.id,
        InteractionModel.candidate_answer == None
    ).order_by(InteractionModel.id.desc()).first()
    
    if not last_interaction:
        raise HTTPException(status_code=400, detail="No active question found for this session. Please call /start_interview first.")
    
    print(f"Grading answer for interaction {last_interaction.interaction_id}...")
    grade = grade_answer(
        last_interaction.generated_question,
        last_interaction.reference_chunk,
        submission.candidate_answer
    )
    
    last_interaction.candidate_answer = submission.candidate_answer
    last_interaction.score = grade.score
    last_interaction.feedback = grade.feedback
    last_interaction.routing_action = grade.routing_action
    last_interaction.focus_concept = grade.focus_concept
    
    routing = grade.routing_action
    focus = grade.focus_concept
    
    if routing == "DRILL_DOWN":
        if last_interaction.drill_down_count >= 2:
            print(f"Drill-down limit (2) reached for session {session.session_id}. Forcing NEXT_TOPIC.")
            routing = "NEXT_TOPIC"
            focus = None
            next_drill_count = 0
        else:
            next_drill_count = last_interaction.drill_down_count + 1
    else:
        next_drill_count = 0
        
    previous_topics = [i.section_header for i in session.interactions if i.section_header]
    resume_data = {
        "skills": session.candidate_skills,
        "technologies": session.candidate_technologies,
        "domain_exposure": session.candidate_domain
    }
    
    print(f"Routing Action: {routing} | Focus Concept: {focus}")
    next_query = generate_search_query(resume_data, session.target_role, previous_topics, focus)
    next_hit = search_qdrant(next_query)
    
    if not next_hit:
        print("Warning: Specific search failed. Falling back to general query.")
        next_hit = search_qdrant(generate_search_query(resume_data, session.target_role, previous_topics))
    
    if not next_hit:
        raise HTTPException(status_code=500, detail="Failed to retrieve next textbook chunk.")

    next_question = generate_question(next_hit.payload["text"], resume_data)
    
    new_interaction = InteractionModel(
        interaction_id=str(uuid.uuid4()),
        session_id=session.id,
        generated_question=next_question,
        reference_chunk=next_hit.payload["text"],
        source_book=next_hit.payload.get("source_book", "Unknown"),
        section_header=next_hit.payload.get("section_header", "Unknown"),
        drill_down_count=next_drill_count
    )
    db.add(new_interaction)
    db.commit()
    
    return {
        "status": "success",
        "evaluation": {
            "score": grade.score,
            "feedback": grade.feedback,
            "routing": routing
        },
        "next_question": next_question,
        "interaction_id": new_interaction.interaction_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

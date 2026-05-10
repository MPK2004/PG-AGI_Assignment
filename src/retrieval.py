import os
import openai
import instructor
from typing import List, Optional
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

_embed_model = None

def get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embed_model

def get_llm_client(use_instructor: bool = False):
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
    if use_instructor:
        return instructor.from_openai(base_client)
    return base_client

class GraderOutput(BaseModel):
    score: int = Field(..., ge=0, le=10, description="Mastery score from 0 to 10")
    feedback: str = Field(..., description="Qualitative feedback for the candidate")
    routing_action: str = Field(..., description="Either 'NEXT_TOPIC' or 'DRILL_DOWN'")
    focus_concept: Optional[str] = Field(None, description="If DRILL_DOWN, the specific concept to explore.")

def generate_search_query(resume_data: dict, job_role: str, previous_topics: List[str], focus_concept: Optional[str] = None) -> str:
    """
    Bridges the gap between modern resume buzzwords and textbook concepts.
    If focus_concept is provided, it forces a 'drill down' into that specific area.
    """
    client = get_llm_client()
    if not client:
        return "Error: LLM configuration missing."

    skills = ", ".join(resume_data.get("skills", []))
    tech = ", ".join(resume_data.get("technologies", []))
    domain = ", ".join(resume_data.get("domain_exposure", []))
    previous = ", ".join(previous_topics) if previous_topics else "None"

    system_prompt = """You are a Senior AI Researcher and Curriculum Designer. 
Your task is to bridge the gap between modern software libraries/buzzwords and fundamental computer science/machine learning textbook concepts (like those in Tom Mitchell's 1997 'Machine Learning').

STRICT RULES:
1. DO NOT use modern library/framework names.
2. MAP tools to theoretical foundations.
3. USE terminology from classic ML literature (e.g., 'Inductive Bias', 'Concept Learning').
4. OUTPUT ONLY THE SEARCH QUERY STRING. NO EXPLANATIONS."""

    if focus_concept:
        user_content = f"""The candidate struggled with a previous question. 
DRILL DOWN into this specific foundational concept: {focus_concept}
Candidate Context: {skills}, {tech}, {domain}
Target Role: {job_role}

Generate a highly specific theoretical search query to find textbook material on this sub-concept:"""
    else:
        user_content = f"""Candidate Skills: {skills}
Candidate Technologies: {tech}
Candidate Domain: {domain}
Target Job Role: {job_role}
Previous Topics Discussed: {previous}

Generate a new theoretical search query for the next interview topic:"""

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {str(e)}"

def search_qdrant(query: str, limit: int = 1):
    """
    Performs vector search in Qdrant to find relevant textbook chunks.
    """
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url:
        print("Error: QDRANT_URL missing.")
        return None

    client = QdrantClient(url=url, api_key=api_key)
    model = get_embed_model()
    
    query_vector = model.encode(query).tolist()
    search_result = client.query_points(
        collection_name="ml_knowledge_base",
        query=query_vector,
        limit=limit
    ).points
    
    if not search_result:
        return None
    
    return search_result[0]

def generate_question(chunk_text: str, resume_data: dict) -> str:
    """
    Generates an interview question based on a textbook chunk and candidate context.
    """
    client = get_llm_client()
    system_prompt = """You are a Principal Machine Learning Engineer. 
Generate a challenging, open-ended interview question based on the textbook snippet provided.
Tailor the question slightly to the candidate's reported technologies/skills if possible to make it practical.
OUTPUT ONLY THE QUESTION."""
    
    user_content = f"""Textbook Snippet: {chunk_text}
Candidate Background: {resume_data}

Generate the interview question:"""
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating question: {str(e)}"

def grade_answer(question: str, reference_chunk: str, candidate_answer: str) -> GraderOutput:
    """
    Grades the candidate's answer using the Instructor-wrapped LLM for structured output.
    """
    client = get_llm_client(use_instructor=True)
    system_prompt = """You are a strict but fair Technical Interviewer.
Compare the candidate's answer against the textbook reference chunk for accuracy and depth.

SCORING CRITERIA:
- 7-10: Mastery. Candidate understands the core concept and its nuances.
- 0-6: Gap in knowledge. Candidate missed a foundational aspect.

ROUTING LOGIC:
- If Score >= 7, routing_action must be 'NEXT_TOPIC'.
- If Score < 7, routing_action must be 'DRILL_DOWN'. provide the 'focus_concept' for the drill-down.

BE BRUTAL AND ACCURATE."""
    
    try:
        return client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
            response_model=GraderOutput,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {question}\nReference Chunk: {reference_chunk}\nCandidate Answer: {candidate_answer}"}
            ],
            temperature=0.1
        )
    except Exception as e:
        return GraderOutput(score=0, feedback=f"Error during grading: {str(e)}", routing_action="NEXT_TOPIC")

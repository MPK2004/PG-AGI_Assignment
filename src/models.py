from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship, Column, JSON


class Session(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    candidate_skills: List[str] = Field(default=[], sa_column=Column(JSON))
    candidate_technologies: List[str] = Field(default=[], sa_column=Column(JSON))
    candidate_domain: List[str] = Field(default=[], sa_column=Column(JSON))
    target_role: str
    
    interactions: List["Interaction"] = Relationship(
        back_populates="session", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

class Interaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    interaction_id: str = Field(unique=True, index=True)
    
    session_id: Optional[int] = Field(
        default=None, 
        foreign_key="session.id", 
        ondelete="CASCADE"
    )
    
    generated_question: str
    reference_chunk: str
    source_book: str
    section_header: str
    
    candidate_answer: Optional[str] = None
    score: Optional[int] = None
    feedback: Optional[str] = None
    routing_action: Optional[str] = None
    focus_concept: Optional[str] = None
    drill_down_count: int = Field(default=0)
    
    session: Optional[Session] = Relationship(back_populates="interactions")

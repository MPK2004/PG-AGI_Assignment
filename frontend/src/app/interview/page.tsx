"use client";

import { useState } from "react";
import { useInterview } from "@/hooks/useInterview";
import { useRouter } from "next/navigation";

export default function InterviewRoom() {
  const { state, isSubmitting, submitAnswer, clearSession, isLoading } = useInterview();
  const [answer, setAnswer] = useState("");
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="container">
        <div className="card" style={{ textAlign: "center" }}>
          <h1>Loading Garden...</h1>
          <p>Rehydrating session state from the vault.</p>
        </div>
      </div>
    );
  }

  // Fallback if state is missing (though middleware should catch this)
  if (!state) {
    return (
      <div className="container">
        <div className="card">
          <h1>No Active Session</h1>
          <p>The garden walls are closed. Please return to the entry gate to begin your interview.</p>
          <button className="button" onClick={() => router.push("/")}>Return to Gate</button>
        </div>
      </div>
    );
  }

  const handleSubmit = async () => {
    if (!answer.trim()) return;
    await submitAnswer(answer);
    setAnswer("");
  };

  const handleExit = () => {
    if (confirm("Are you sure you want to leave the walled garden? This will terminate your active session.")) {
      clearSession();
      router.push("/");
    }
  };

  return (
    <main className="container">
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
          <span className="status-badge status-active">Secure Session</span>
          <button 
            onClick={handleExit} 
            style={{ 
              background: "none", 
              border: "none", 
              color: "var(--error)", 
              cursor: "pointer", 
              fontSize: "0.875rem",
              fontWeight: "600"
            }}
          >
            Terminate Session
          </button>
        </div>

        {state.feedback && (
          <div className="feedback-area">
            <label style={{ color: "var(--primary)", fontWeight: "bold", textTransform: "uppercase", fontSize: "0.75rem" }}>
              Previous Evaluation
            </label>
            <p style={{ color: "white", marginTop: "0.5rem", marginBottom: "0.5rem", fontSize: "0.95rem" }}>
              {state.feedback}
            </p>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
               <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
                Score: <strong style={{ color: "var(--success)" }}>{state.score}/10</strong>
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
                Routing: <strong style={{ color: "var(--primary)" }}>{state.routing}</strong>
              </span>
            </div>
          </div>
        )}

        <div style={{ marginTop: "2rem" }}>
          <label style={{ textTransform: "uppercase", fontSize: "0.75rem", letterSpacing: "0.05em" }}>
            Current Question
          </label>
          <p className="question-text">{state.question}</p>
        </div>

        <div className="input-group">
          <label style={{ textTransform: "uppercase", fontSize: "0.75rem", letterSpacing: "0.05em" }}>
            Your Answer
          </label>
          <textarea 
            rows={8}
            placeholder="Formulate your technical response..."
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={isSubmitting}
            style={{ resize: "none" }}
          />
        </div>

        <button 
          className="button" 
          onClick={handleSubmit}
          disabled={!answer.trim() || isSubmitting}
        >
          {isSubmitting ? (
            <>
              <span className="loader"></span>
              Transmitting to Backend...
            </>
          ) : (
            "Submit Answer"
          )}
        </button>
      </div>
      
      <p style={{ textAlign: "center", marginTop: "2rem", fontSize: "0.75rem" }}>
        Session ID: <code style={{ color: "var(--primary)" }}>{state.interaction_id.split('-')[0]}...</code>
      </p>
    </main>
  );
}

"use client";

import { useState, useEffect } from "react";
import { useInterview } from "@/hooks/useInterview";
import { useRouter } from "next/navigation";

const SUBMISSION_STEPS = [
  "Evaluating your response...",
  "Searching the knowledge base...",
  "Contextualizing technical concepts...",
  "Formulating the next scenario..."
];

export default function InterviewRoom() {
  const { state, isSubmitting, submitAnswer, clearSession, isLoading, error } = useInterview();
  const [answer, setAnswer] = useState("");
  const [activeStep, setActiveStep] = useState(0);
  const router = useRouter();

  // Cycle through submission steps to mask latency
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isSubmitting) {
      setActiveStep(0);
      interval = setInterval(() => {
        setActiveStep((prev) => (prev < SUBMISSION_STEPS.length - 1 ? prev + 1 : prev));
      }, 2500); // Change step every 2.5 seconds
    }
    return () => clearInterval(interval);
  }, [isSubmitting]);

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
    if (!error) {
      setAnswer("");
    }
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

        {/* Feedback Area with Skeleton */}
        <div className="feedback-area" style={{ opacity: isSubmitting ? 0.5 : 1 }}>
          <label style={{ color: "var(--primary)", fontWeight: "bold", textTransform: "uppercase", fontSize: "0.75rem" }}>
            Previous Evaluation
          </label>
          {isSubmitting ? (
            <div className="skeleton skeleton-feedback" style={{ marginTop: "1rem" }}></div>
          ) : state.feedback ? (
            <>
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
            </>
          ) : (
            <p style={{ marginTop: "0.5rem", fontStyle: "italic" }}>No feedback yet. Initial question.</p>
          )}
        </div>

        {/* Question Area with Skeleton */}
        <div style={{ marginTop: "2rem" }}>
          {!isSubmitting && state.routing && (
            <div className="routing-transition">
              {state.routing === "DRILL_DOWN" ? (
                <div className="routing-badge routing-drill-down">
                  <svg className="routing-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="M7 13l5 5 5-5M7 6l5 5 5-5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Following up on that...
                </div>
              ) : state.routing === "NEXT_TOPIC" ? (
                <div className="routing-badge routing-next-topic">
                  <svg className="routing-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="M13 5l7 7-7 7M5 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Let&apos;s pivot to a new concept...
                </div>
              ) : null}
            </div>
          )}

          <label style={{ textTransform: "uppercase", fontSize: "0.75rem", letterSpacing: "0.05em" }}>
            Current Question
          </label>
          {isSubmitting ? (
            <div style={{ marginTop: "1rem" }}>
              <div className="skeleton skeleton-text" style={{ width: "90%" }}></div>
              <div className="skeleton skeleton-text" style={{ width: "70%" }}></div>
            </div>
          ) : (
            <p className="question-text">{state.question}</p>
          )}
        </div>

        {/* Status Indicators during submission */}
        {isSubmitting && (
          <div className="status-steps">
            {SUBMISSION_STEPS.map((step, idx) => (
              <div 
                key={idx} 
                className={`status-step ${idx === activeStep ? 'active' : idx < activeStep ? 'completed' : ''}`}
              >
                <div className="status-step-icon">
                  {idx < activeStep && "✓"}
                </div>
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}

        {/* Error Boundary */}
        {error && (
          <div className="error-boundary">
            <div>
              <strong style={{ color: "var(--error)" }}>Submission Error:</strong>
              <p style={{ margin: "0.5rem 0", fontSize: "0.875rem" }}>{error}</p>
            </div>
            <button className="button" onClick={handleSubmit} style={{ background: "var(--error)" }}>
              Retry Submission
            </button>
          </div>
        )}

        <div className="input-group" style={{ marginTop: "2rem" }}>
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
              Orchestrating AI...
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

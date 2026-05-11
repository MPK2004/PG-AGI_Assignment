import { useState, useEffect } from "react";
import Cookies from "js-cookie";

const CACHE_KEY = "interview_cache";

interface InterviewState {
  question: string;
  interaction_id: string;
  feedback?: string;
  score?: number;
  routing?: string;
}

export function useInterview() {
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [state, setState] = useState<InterviewState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Initial hydration
  useEffect(() => {
    const sid = Cookies.get("session_id");
    setSessionId(sid);
    
    // Load state from localStorage ONLY if cookie exists
    if (sid) {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        try {
          setState(JSON.parse(cached));
        } catch (e) {
          console.error("Failed to parse cache", e);
        }
      }
    } else {
      // If no cookie, clear cache to ensure single source of truth (Brutal Truth Protocol)
      localStorage.removeItem(CACHE_KEY);
      setState(null);
    }
    setIsLoading(false);
  }, []);

  // Persist non-sensitive content to localStorage for UI resilience
  useEffect(() => {
    if (state && sessionId) {
      localStorage.setItem(CACHE_KEY, JSON.stringify(state));
    } else if (!sessionId) {
      localStorage.removeItem(CACHE_KEY);
    }
  }, [state, sessionId]);

  const startSession = async (targetRole: string, resumeFile: File) => {
    setIsSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("target_role", targetRole);
      formData.append("file", resumeFile);

      const res = await fetch("/api/upload_resume", {
        method: "POST",
        body: formData,
      });
      
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      
      if (data.session_id) {
        // Set Cookie as the primary session lock
        Cookies.set("session_id", data.session_id, { expires: 1, path: "/" });
        setSessionId(data.session_id);
        
        // Start interview immediately
        const startRes = await fetch(`/api/start_interview?session_id=${data.session_id}`, {
          method: "POST",
        });
        if (!startRes.ok) throw new Error("Start interview failed");
        const startData = await startRes.json();
        
        const newState = {
          question: startData.question,
          interaction_id: startData.interaction_id,
        };
        setState(newState);
        return true;
      }
    } catch (e) {
      console.error("Start session failed:", e);
      alert("Failed to process resume. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
    return false;
  };

  const submitAnswer = async (answer: string) => {
    if (!sessionId || !state) return;
    setIsSubmitting(true); // Aggressive disable
    try {
      const res = await fetch("/api/submit_answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          candidate_answer: answer,
        }),
      });
      
      if (!res.ok) throw new Error("Submission failed");
      const data = await res.json();
      
      const newState: InterviewState = {
        question: data.next_question,
        interaction_id: data.interaction_id,
        feedback: data.evaluation.feedback,
        score: data.evaluation.score,
        routing: data.evaluation.routing,
      };
      setState(newState);
    } catch (e) {
      console.error("Submit failed:", e);
      alert("Submission failed. Your session is still active, please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const clearSession = () => {
    Cookies.remove("session_id");
    localStorage.removeItem(CACHE_KEY);
    setSessionId(undefined);
    setState(null);
  };

  return {
    sessionId,
    state,
    isSubmitting,
    isLoading,
    startSession,
    submitAnswer,
    clearSession,
  };
}

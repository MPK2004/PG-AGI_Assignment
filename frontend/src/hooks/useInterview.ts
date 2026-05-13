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

interface InteractionStatusResponse {
  status: "processing" | "ready" | "failed";
  question?: string;
  next_question?: string;
  interaction_id: string;
  evaluation?: {
    score: number;
    feedback: string;
    routing: string;
  };
  error?: string;
}

export function useInterview() {
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [state, setState] = useState<InterviewState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const pollInteraction = async (interactionId: string): Promise<InteractionStatusResponse> => {
    const MAX_RETRIES = 30;
    const RETRY_INTERVAL = 2000;
    let attempts = 0;

    while (attempts < MAX_RETRIES) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_INTERVAL));
      attempts++;

      try {
        const res = await fetch(`/api/interaction_status/${interactionId}`);
        if (!res.ok) {
          // If 404, maybe it's not in DB yet, wait a bit
          if (res.status === 404 && attempts < 5) continue;
          throw new Error(`Status check failed: ${res.statusText}`);
        }
        
        const data = await res.json();
        
        if (data.status === "ready") {
          return data;
        }
        
        if (data.status === "failed") {
          throw new Error(data.error || "The AI engine encountered an error processing your request.");
        }

        // status is "processing", continue loop
        console.log(`Polling interaction ${interactionId}... attempt ${attempts}/${MAX_RETRIES}`);
      } catch (e: unknown) {
        // If it's a network error or explicitly thrown error, we might want to retry unless it's a "failed" status
        const message = e instanceof Error ? e.message : "";
        if (message.includes("AI engine encountered an error")) throw e;
        if (attempts >= MAX_RETRIES) throw new Error("Connection timed out. Please check your internet and try again.");
      }
    }

    throw new Error("The request timed out after 60 seconds. Please try again.");
  };

  const startSession = async (targetRole: string, resumeFile: File) => {
    setIsSubmitting(true);
    setError(null);
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
        Cookies.set("session_id", data.session_id, { expires: 1, path: "/" });
        setSessionId(data.session_id);
        
        const startRes = await fetch(`/api/start_interview?session_id=${data.session_id}`, {
          method: "POST",
        });
        if (!startRes.ok) throw new Error("Start interview failed");
        const startData = await startRes.json();
        
        // Wait for LLM in background
        const finalData = await pollInteraction(startData.interaction_id);
        
        const newState: InterviewState = {
          question: finalData.question,
          interaction_id: finalData.interaction_id,
        };
        setState(newState);
        return true;
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Start session failed";
      console.error("Start session failed:", e);
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
    return false;
  };

  const submitAnswer = async (answer: string) => {
    if (!sessionId || !state) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/submit_answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          candidate_answer: answer,
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Submission failed");
      }
      
      const data = await res.json();
      
      // Wait for LLM in background (The Polling Dance)
      const finalData = await pollInteraction(data.interaction_id);
      
      if (!finalData || finalData.status !== "ready") {
        throw new Error("Invalid response from polling server.");
      }

      const newState: InterviewState = {
        question: finalData.next_question,
        interaction_id: finalData.interaction_id,
        feedback: finalData.evaluation?.feedback || "No feedback provided.",
        score: finalData.evaluation?.score,
        routing: finalData.evaluation?.routing,
      };
      setState(newState);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Submission failed";
      console.error("Submit failed:", e);
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const clearSession = () => {
    Cookies.remove("session_id");
    localStorage.removeItem(CACHE_KEY);
    setSessionId(undefined);
    setState(null);
    setError(null);
  };

  return {
    sessionId,
    state,
    isSubmitting,
    isLoading,
    error,
    startSession,
    submitAnswer,
    clearSession,
  };
}

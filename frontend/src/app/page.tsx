"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useInterview } from "@/hooks/useInterview";

export default function Home() {
  const [role, setRole] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const { startSession, isSubmitting } = useInterview();
  const router = useRouter();

  const handleStart = async () => {
    if (!role || !file) return;
    const success = await startSession(role, file);
    if (success) {
      router.push("/interview");
    }
  };

  return (
    <main className="container">
      <div className="card">
        <h1>Walled Garden</h1>
        <p>A resilient environment for machine learning interviews. Mirroring backend state with persistent session management.</p>
        
        <div className="input-group">
          <label>Target Role</label>
          <input 
            type="text" 
            placeholder="e.g. Senior MLE, Research Scientist" 
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={isSubmitting}
          />
        </div>

        <div className="file-input-wrapper">
          {file ? (
            <div>
              <p style={{ color: "var(--success)", marginBottom: "0.5rem", fontWeight: "bold" }}>✓ {file.name}</p>
              <span className="status-badge status-active">Resume Ready</span>
            </div>
          ) : (
            <div>
              <p>Click or drag your PDF resume here</p>
              <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>Only .pdf files are accepted</span>
            </div>
          )}
          <input 
            type="file" 
            accept=".pdf" 
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            disabled={isSubmitting}
          />
        </div>

        <button 
          className="button" 
          onClick={handleStart}
          disabled={!role || !file || isSubmitting}
        >
          {isSubmitting ? (
            <>
              <span className="loader"></span>
              Initializing Session...
            </>
          ) : (
            "Start Interview"
          )}
        </button>
      </div>
    </main>
  );
}

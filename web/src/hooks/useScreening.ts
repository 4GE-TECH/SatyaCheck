/**
 * useScreening — Hook for screening audio against the backend.
 * Falls back to mock fixtures when the API is unavailable.
 */

import { useState, useCallback } from "react";
import type { ScreeningResponse } from "../types/contracts";
import { getMockFixture, type MockScenario } from "../api/mock";

interface UseScreeningReturn {
  data: ScreeningResponse | null;
  loading: boolean;
  error: string | null;
  screenFile: (file: File) => Promise<void>;
  screenMock: (scenario: MockScenario) => void;
  clear: () => void;
}

export default function useScreening(): UseScreeningReturn {
  const [data, setData] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const screenFile = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    setData(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/screen", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}`);
      }

      const json: ScreeningResponse = await res.json();
      setData(json);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Unknown error occurred";
      setError(`API unavailable (${msg}). Use demo scenarios instead.`);
    } finally {
      setLoading(false);
    }
  }, []);

  const screenMock = useCallback((scenario: MockScenario) => {
    setLoading(true);
    setError(null);
    setData(null);

    // Simulate a brief processing delay for realism
    setTimeout(() => {
      setData(getMockFixture(scenario));
      setLoading(false);
    }, 600);
  }, []);

  const clear = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, screenFile, screenMock, clear };
}

"""
Optional-Aware AI Context Injector (BYOK Gemini).
If user provides a Gemini API key: call Gemini with dense context and 30-min cooldown for RPD limits.
If no key: return a static Quant Report. On 429 or any API error: fall back to static report.
"""
import asyncio
import time
from typing import Optional

# Optional: only load genai when key is provided to avoid import errors in envs without google-genai
try:
    from google import genai
except ImportError:
    genai = None

AI_COOLDOWN_SEC = 1800  # 30 minutes to respect 2026 free tier RPD limits


class AI_ContextInjector:
    """
    Manages optional user Gemini key. Returns AI insight if key present and not in cooldown;
    otherwise returns a static Quant Report.
    """
    def __init__(self, user_gemini_key: Optional[str] = None):
        self.client = None
        if user_gemini_key and (user_gemini_key := (user_gemini_key or "").strip()):
            if genai is not None:
                try:
                    self.client = genai.Client(api_key=user_gemini_key)
                except Exception:
                    self.client = None
            else:
                self.client = None
        self.last_run = 0.0

    def _generate_static_quant_report(self, v_sigma: float, assets_summary: str) -> str:
        """Non-AI fallback: standard data-driven status string."""
        status = "Aggressive" if v_sigma > 1.5 else "Neutral"
        return f"Market Regime: {status} | Strategy: IQM Square-Root Allocation Active."

    async def get_insight(self, v_sigma: float, assets_summary: str) -> str:
        """
        Returns AI insight if key exists and not in cooldown; otherwise returns static Quant summary.
        Handles 429 and other API errors with graceful fallback.
        """
        if not self.client:
            return self._generate_static_quant_report(v_sigma, assets_summary)

        if (time.time() - self.last_run) < AI_COOLDOWN_SEC:
            return "AI cooling down. Portfolio executing via IQM Math."

        try:
            prompt = (
                f"V_Sigma: {v_sigma}. Assets: {assets_summary}. "
                "Act as a quant analyst. Write a 1-sentence Wall St style status for the user's dashboard."
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
            )
            self.last_run = time.time()
            return (response.text or "").strip() or self._generate_static_quant_report(v_sigma, assets_summary)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "resource_exhausted" in err or "rate" in err:
                return "Quant Mode: " + self._generate_static_quant_report(v_sigma, assets_summary)
            return f"Quant Mode: {self._generate_static_quant_report(v_sigma, assets_summary)}"

    async def get_dashboard_insight(self, v_sigma: float, assets_data: str) -> str:
        """Alias for get_insight for plan compatibility."""
        return await self.get_insight(v_sigma, assets_data)

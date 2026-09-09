"""
AgriFlow WhatsApp Bot
======================

M2 milestone (week 5-6 of v10 roadmap) — accessibility layer for the
matching engine via WhatsApp Business API.

Architecture:
    Twilio webhook → server.py → intent.py → handlers.py → matching_engine
                                     ↓
                                gemini_client.py (LLM: Gemini, then
                                openai_client.py as fallback, then mock)

Public entrypoints:
    server.app             — FastAPI app
    server.handle_message  — pure function, useful for tests + CLI
"""

__version__ = "0.1.0"

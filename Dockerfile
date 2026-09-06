# Hugging Face Spaces — Docker SDK build for the AgriFlow FastAPI backend.
#
# Why this exists:
#   HF Spaces (Docker SDK) builds + runs this container; the resulting public
#   URL is what the Vercel dashboard hits via NEXT_PUBLIC_API_URL and what
#   Twilio's WhatsApp Sandbox webhook points at.
#
# Port contract:
#   HF Spaces expects the app to listen on 7860 by default. We honour that.
#
# Secrets (set in the Space's "Settings → Variables and secrets" UI, never here):
#   GEMINI_API_KEY        — from aistudio.google.com
#   TWILIO_ACCOUNT_SID    — Twilio console
#   TWILIO_AUTH_TOKEN     — Twilio console
#   TWILIO_WHATSAPP_FROM  — whatsapp:+14155238886 (sandbox) or your number
#   PHONE_HASH_SALT       — 64 random hex chars
#   MOCK_MODE=true        — start here; flip to false once Gemini/Twilio keys are set.
#   APP_ENV=production    — once every demo default above is off; the server
#                           refuses to boot half-secured (whatsapp_bot/security.py).

FROM python:3.12-slim

# Avoid stale .pyc + force unbuffered stdout for clean HF log streaming.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# Run as an unprivileged user. uid 1000 is what HF Spaces documents for
# Docker Spaces, and the JSON quota store under .state/ needs a writable home.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin agriflow

WORKDIR /app

# Install dependencies first so layer is cacheable when source changes.
COPY --chown=agriflow:agriflow requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Now copy the rest of the project.
COPY --chown=agriflow:agriflow . .
RUN mkdir -p /app/.state && chown -R agriflow:agriflow /app/.state

USER agriflow

# HF Spaces routes external traffic to this port.
EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=4).status == 200 else 1)"

# --proxy-headers so request.url and X-Forwarded-Proto reflect the HF edge,
# which is what the HSTS header and Twilio signature check key on.
CMD ["uvicorn", "whatsapp_bot.server:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]

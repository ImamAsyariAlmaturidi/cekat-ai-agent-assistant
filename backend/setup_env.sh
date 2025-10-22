#!/bin/bash

# ChatKit Backend Environment Setup Script
# Jalankan script ini untuk set environment variables yang diperlukan

echo "Setting up ChatKit Backend Environment Variables..."

# OpenAI API Key (WAJIB)
# Ganti dengan API key OpenAI Anda yang valid
export OPENAI_API_KEY="sk-proj-your-openai-api-key-here"

# ChatKit Domain Key (untuk development, bisa pakai placeholder)
# Untuk production, ganti dengan domain key yang valid dari OpenAI
export VITE_CHATKIT_API_DOMAIN_KEY="domain_pk_local_dev"

# Optional: Custom API URLs (jika tidak di-set, akan menggunakan default)
# export VITE_CHATKIT_API_URL="http://127.0.0.1:8000"
# export VITE_FACTS_API_URL="http://127.0.0.1:8000"

# Python path untuk development
export PYTHONPATH="$(pwd)"

echo "Environment variables set successfully!"
echo ""
echo "Current environment:"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:20}..."
echo "VITE_CHATKIT_API_DOMAIN_KEY: $VITE_CHATKIT_API_DOMAIN_KEY"
echo "PYTHONPATH: $PYTHONPATH"
echo ""
echo "To start the backend server, run:"
echo "uv run uvicorn app.main:app --reload --port 8000"
echo ""
echo "To start the frontend, run (in another terminal):"
echo "cd ../frontend && npm run dev"

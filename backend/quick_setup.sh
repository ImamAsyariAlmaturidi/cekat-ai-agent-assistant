# Quick Environment Setup untuk ChatKit Backend
# Copy dan paste command berikut di terminal:

# 1. Set OpenAI API Key (WAJIB - ganti dengan API key Anda)
export OPENAI_API_KEY="sk-proj-your-openai-api-key-here"

# 2. Set ChatKit Domain Key (untuk development)
export VITE_CHATKIT_API_DOMAIN_KEY="domain_pk_local_dev"

# 3. Set Python path
export PYTHONPATH="$(pwd)"

# 4. Verify environment variables
echo "Environment variables set:"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:20}..."
echo "VITE_CHATKIT_API_DOMAIN_KEY: $VITE_CHATKIT_API_DOMAIN_KEY"
echo "PYTHONPATH: $PYTHONPATH"

# 5. Start backend server
echo "Starting backend server..."
uv run uvicorn app.main:app --reload --port 8000

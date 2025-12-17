# Quickstart Guide

Get SentinelRouter up and running in under 5 minutes.

## Prerequisites

- Python 3.11 or later
- `pip` (Python package manager)
- Git (optional, for cloning the repository)
- API keys for at least one LLM provider (DeepSeek, Anthropic, or Gemini)

## Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/sentinelrouter.git
cd sentinelrouter
```

Alternatively, download the source code as a ZIP file and extract it.

## Step 2: Set Up Environment

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your favorite editor:

```bash
# Required: at least one weak and one strong model key
DEEPSEEK_API_KEY=your_deepseek_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional: Gemini keys for judge models
GEMINI_API_KEY=your_gemini_api_key_here
```

## Step 3: Install Dependencies

Create a virtual environment (recommended) and install the required packages:

```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Quick Setup Script

Alternatively, use the automated setup script that checks Python version, creates `.env`, installs dependencies, and verifies the installation:

```bash
./setup.sh
```

The script will:
- ✅ Verify Python 3.11+ is installed
- ✅ Create `.env` from `.env.example` if missing
- ✅ Install all dependencies
- ✅ Run verification tests
- ✅ Provide setup status report

## Step 4: Initialize the Database

The database is automatically created on first run, but you can manually initialize it:

```bash
python -c "from sentinelrouter.database import init_db; init_db()"
```

## Step 5: Start the Server

### Development Mode (with auto‑reload)

```bash
uvicorn sentinelrouter.sentinelrouter.server:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode (using the provided script)

```bash
./start_servers.sh
```

This starts both the main API server (port 8000) and the metrics dashboard (port 8001).

## Step 6: Verify the Installation

Open a new terminal and run:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "healthy", "service": "sentinelrouter"}
```

## Step 7: Send Your First Request

Use the OpenAI‑compatible endpoint to test routing:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "session_id": "quickstart-test"
  }'
```

You should receive a response with the answer and additional SentinelRouter headers:

- `X-Sentinel-Model-Used`: The model that handled the request (e.g., `deepseek-reasoner`)
- `X-Sentinel-Cost`: Cost incurred for this request
- `X-Sentinel-Session-Cost`: Cumulative session cost so far

## Step 8: View the Dashboard

Open your browser and navigate to:

```
http://localhost:8001
```

You’ll see the real‑time metrics dashboard showing request counts, latencies, and system health.

## Next Steps

- Read the [Configuration Guide](configuration.md) to customize SentinelRouter for your needs.
- Deploy with [Docker](docker-deployment.md) for production use.
- Explore the [Architecture Overview](../architecture/overview.md) to understand how the system works.

## Troubleshooting

If you encounter issues, check:

1. **API keys are correctly set** in `.env`
2. **Ports 8000 and 8001 are not already in use**
3. **The virtual environment is activated** (if using one)
4. **All dependencies are installed** (`pip list | grep sentinelrouter`)

For more help, see the [Troubleshooting](../operations/troubleshooting.md) guide.

---

*Congratulations! You’ve successfully started SentinelRouter. 🎉*
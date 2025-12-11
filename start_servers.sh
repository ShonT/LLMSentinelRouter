#!/bin/bash
# Start both main server and dashboard server

# Start dashboard in background
echo "Starting dashboard server on port 8001..."
python -c "from sentinelrouter.sentinelrouter.dashboard import start_dashboard_server; start_dashboard_server('0.0.0.0', 8001)" &

# Start main API server with gunicorn
echo "Starting main API server on port 8000..."
exec gunicorn sentinelrouter.sentinelrouter.server:app \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --log-level info

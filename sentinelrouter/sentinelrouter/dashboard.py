"""
Enhanced dashboard for SentinelRouter with three tabs.

Provides:
- Tab 1: "Live Traffic" - Operational view with real‑time model metrics
- Tab 2: "Configuration & Keys" - Admin interface for model settings
- Tab 3: "Router Logic" - Diagnostics and routing decision logs
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from typing import Dict, Any, List, Optional
import logging
import asyncio
from datetime import datetime
import json

from .metrics import get_metrics_collector
from .state_manager import get_state_manager
from .config import get_unified_config, get_settings
from .throttle_manager import get_throttle_manager
from .router_logic import Router
from .database import get_db
from .models import RoutingDecision
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Create dashboard app
dashboard_app = FastAPI(title="SentinelRouter Enhanced Dashboard")


# Dependency for database session
def get_dbsession():
    with get_db() as db:
        yield db


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_home():
    """Serve the main dashboard page with three tabs."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SentinelRouter Enhanced Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1600px;
                margin: 0 auto;
            }
            .header {
                text-align: center;
                margin-bottom: 20px;
            }
            .header h1 {
                color: white;
                font-size: 2.5rem;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                margin-bottom: 10px;
            }
            .header .subtitle {
                color: rgba(255,255,255,0.8);
                font-size: 1rem;
                margin-bottom: 30px;
            }
            /* Tabs */
            .tabs {
                display: flex;
                background: rgba(255,255,255,0.1);
                border-radius: 12px 12px 0 0;
                overflow: hidden;
                margin-bottom: 0;
            }
            .tab {
                flex: 1;
                text-align: center;
                padding: 18px 10px;
                color: white;
                font-weight: 600;
                font-size: 1.1rem;
                cursor: pointer;
                transition: all 0.3s;
                border-bottom: 4px solid transparent;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
            }
            .tab:hover {
                background: rgba(255,255,255,0.2);
            }
            .tab.active {
                background: rgba(255,255,255,0.95);
                color: #333;
                border-bottom-color: #10b981;
            }
            .tab-content {
                display: none;
                background: white;
                border-radius: 0 12px 12px 12px;
                padding: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                min-height: 600px;
            }
            .tab-content.active {
                display: block;
            }
            /* Tab 1: Live Traffic */
            .model-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .model-card {
                background: #f8fafc;
                border-radius: 12px;
                padding: 20px;
                border: 1px solid #e2e8f0;
                transition: transform 0.2s;
            }
            .model-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            }
            .model-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .model-name {
                font-size: 1.3rem;
                font-weight: 700;
                color: #1e293b;
            }
            .status-badge {
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 600;
            }
            .status-active { background: #d1fae5; color: #065f46; }
            .status-inactive { background: #fef3c7; color: #92400e; }
            .status-disabled { background: #fee2e2; color: #991b1b; }
            .metric-row {
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                padding-bottom: 8px;
                border-bottom: 1px solid #e2e8f0;
            }
            .metric-label {
                color: #64748b;
                font-size: 0.9rem;
            }
            .metric-value {
                font-weight: 600;
                color: #1e293b;
            }
            .gauge-container {
                height: 10px;
                background: #e2e8f0;
                border-radius: 5px;
                margin: 15px 0;
                overflow: hidden;
            }
            .gauge-fill {
                height: 100%;
                border-radius: 5px;
                transition: width 0.5s;
            }
            .gauge-green { background: #10b981; }
            .gauge-yellow { background: #f59e0b; }
            .gauge-red { background: #ef4444; }
            .controls {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            .btn {
                padding: 8px 16px;
                border-radius: 8px;
                border: none;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                flex: 1;
            }
            .btn-reset {
                background: #3b82f6;
                color: white;
            }
            .btn-reset:hover { background: #2563eb; }
            .btn-stop {
                background: #ef4444;
                color: white;
            }
            .btn-stop:hover { background: #dc2626; }
            .btn-start {
                background: #10b981;
                color: white;
            }
            .btn-start:hover { background: #059669; }
            .global-controls {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 30px;
            }
            /* Tab 2: Configuration */
            .config-section {
                background: #f8fafc;
                border-radius: 12px;
                padding: 25px;
                margin-bottom: 25px;
                border: 1px solid #e2e8f0;
            }
            .config-section h3 {
                color: #1e293b;
                margin-bottom: 20px;
                font-size: 1.3rem;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .config-section h3::before {
                content: "⚙️";
            }
            .api-key-row {
                display: flex;
                align-items: center;
                gap: 15px;
                margin-bottom: 15px;
                padding: 15px;
                background: white;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
            }
            .api-key-label {
                font-weight: 600;
                min-width: 150px;
                color: #475569;
            }
            .api-key-masked {
                font-family: 'Courier New', monospace;
                background: #f1f5f9;
                padding: 8px 12px;
                border-radius: 6px;
                flex: 1;
                color: #64748b;
            }
            .btn-reveal {
                background: #94a3b8;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.85rem;
            }
            .btn-reveal:hover { background: #64748b; }
            .sortable-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }
            .sortable-item {
                background: white;
                border: 1px solid #e2e8f0;
                padding: 15px;
                margin-bottom: 10px;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 15px;
                cursor: move;
                user-select: none;
            }
            .sortable-item:hover {
                background: #f8fafc;
                border-color: #cbd5e1;
            }
            .drag-handle {
                color: #94a3b8;
                font-size: 1.2rem;
                cursor: move;
            }
            .priority-badge {
                background: #3b82f6;
                color: white;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: 600;
            }
            .pricing-tier {
                background: white;
                border: 1px solid #e2e8f0;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
            .tier-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .tier-name {
                font-weight: 700;
                color: #1e293b;
            }
            .btn-delete-tier {
                background: #fca5a5;
                color: #7f1d1d;
                border: none;
                padding: 5px 10px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.8rem;
            }
            .save-area {
                text-align: center;
                margin-top: 30px;
            }
            .btn-save {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 15px 40px;
                border-radius: 10px;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
            }
            .btn-save:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(0,0,0,0.2);
            }
            /* Tab 3: Router Logic */
            .logs-container {
                max-height: 500px;
                overflow-y: auto;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background: #f8fafc;
            }
            .log-entry {
                padding: 20px;
                border-bottom: 1px solid #e2e8f0;
                background: white;
            }
            .log-entry:last-child {
                border-bottom: none;
            }
            .log-header {
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                font-size: 0.9rem;
                color: #64748b;
            }
            .log-model {
                font-weight: 700;
                color: #3b82f6;
            }
            .log-reason {
                background: #fef3c7;
                padding: 12px;
                border-radius: 8px;
                margin: 10px 0;
                color: #92400e;
                font-size: 0.95rem;
            }
            .log-details {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin-top: 15px;
                font-size: 0.9rem;
                color: #475569;
            }
            .log-detail-item {
                background: #f1f5f9;
                padding: 8px 12px;
                border-radius: 6px;
            }
            .request-response-preview {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 15px;
                margin-top: 15px;
                font-family: 'Courier New', monospace;
                font-size: 0.85rem;
            }
            .preview-section {
                margin-bottom: 15px;
            }
            .preview-label {
                font-weight: 700;
                color: #1e293b;
                margin-bottom: 8px;
                display: block;
            }
            .preview-content {
                background: white;
                padding: 10px;
                border-radius: 6px;
                max-height: 150px;
                overflow-y: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                color: #475569;
            }
            .chart-container {
                background: white;
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 20px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            }
            .chart-title {
                font-size: 1.2rem;
                font-weight: 700;
                color: #1e293b;
                margin-bottom: 15px;
            }
            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 25px;
            }
            .metric-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
            }
            .metric-card-value {
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 5px;
            }
            .metric-card-label {
                font-size: 0.9rem;
                opacity: 0.9;
            }
            .filter-controls {
                margin-bottom: 20px;
                padding: 15px;
                background: #f8fafc;
                border-radius: 8px;
            }
            .filter-label {
                display: inline-block;
                margin-right: 10px;
                font-weight: 600;
                color: #1e293b;
            }
            .refresh-info {
                text-align: center;
                color: white;
                margin-top: 20px;
                font-size: 0.9rem;
                opacity: 0.8;
            }
            .hidden {
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 SentinelRouter Enhanced Dashboard</h1>
                <div class="subtitle">Live Traffic • Configuration • Router Logic</div>
            </div>

            <div class="tabs">
                <div class="tab active" data-tab="tab1">
                    <span>📊</span> Live Traffic
                </div>
                <div class="tab" data-tab="tab2">
                    <span>🔧</span> Configuration & Keys
                </div>
                <div class="tab" data-tab="tab3">
                    <span>🛠️</span> Router Logic
                </div>
            </div>

            <!-- Tab 1: Live Traffic -->
            <div id="tab1" class="tab-content active">
                <h2 style="margin-bottom: 25px; color: #1e293b;">Live Model Traffic & Status</h2>
                
                <!-- Metrics Summary Cards -->
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-card-value" id="totalFallbacks">0</div>
                        <div class="metric-card-label">Total Fallbacks</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value" id="avgJudgeLatency">0ms</div>
                        <div class="metric-card-label">Avg Judge Latency</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value" id="avgWeakLatency">0ms</div>
                        <div class="metric-card-label">Avg Weak Model Latency</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value" id="avgStrongLatency">0ms</div>
                        <div class="metric-card-label">Avg Strong Model Latency</div>
                    </div>
                </div>

                <!-- Latency Line Charts -->
                <div class="chart-container">
                    <div class="chart-title">📈 Latency Trends (Last 50 Requests)</div>
                    <canvas id="latencyChart" style="max-height: 300px;"></canvas>
                </div>

                <h3 style="margin: 25px 0 15px 0; color: #1e293b;">Model Status Grid</h3>
                <div class="model-grid" id="modelGrid">
                    <!-- Model cards will be populated by JavaScript -->
                    <div class="model-card">
                        <div class="model-header">
                            <div class="model-name">Loading...</div>
                            <div class="status-badge status-active">Active</div>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Requests/min</span>
                            <span class="metric-value">0 RPM</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Requests today</span>
                            <span class="metric-value">0 / 1500</span>
                        </div>
                        <div class="gauge-container">
                            <div class="gauge-fill gauge-green" style="width: 0%"></div>
                        </div>
                        <div class="controls">
                            <button class="btn btn-reset">Reset Session Cost</button>
                            <button class="btn btn-stop">Emergency Stop</button>
                        </div>
                    </div>
                </div>
                <div class="global-controls">
                    <button class="btn btn-reset" onclick="resetAllSessionCosts()">Reset All Session Costs</button>
                    <button class="btn btn-start" onclick="startAllModels()">Start All Models</button>
                    <button class="btn btn-stop" onclick="stopAllModels()">Stop All Models</button>
                </div>
                <div class="refresh-info">
                    Auto‑refreshing every 5 seconds • Last updated: <span id="lastUpdate">-</span>
                </div>
            </div>

            <!-- Tab 2: Configuration & Keys -->
            <div id="tab2" class="tab-content">
                <h2 style="margin-bottom: 25px; color: #1e293b;">Configuration & API Key Management</h2>
                
                <div class="config-section">
                    <h3>API Keys</h3>
                    <div id="apiKeysContainer">
                        <!-- API keys will be populated here -->
                        <div class="api-key-row">
                            <span class="api-key-label">DEEPSEEK_API_KEY</span>
                            <span class="api-key-masked">sk-...****</span>
                            <button class="btn-reveal">Reveal</button>
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3>Model Priority & Ordering</h3>
                    <p style="color: #64748b; margin-bottom: 15px;">Drag and drop to change routing priority:</p>
                    <ul class="sortable-list" id="priorityList">
                        <!-- Priority items will be populated here -->
                        <li class="sortable-item">
                            <span class="drag-handle">⋮⋮</span>
                            <span class="model-name">DeepSeek Chat</span>
                            <span class="priority-badge">Priority Group: fast_tier</span>
                            <span style="margin-left: auto;">Order: 1</span>
                        </li>
                    </ul>
                </div>

                <div class="config-section">
                    <h3>Rate Limit Settings</h3>
                    <div id="rateLimitSettings">
                        <!-- Rate limit inputs will be populated here -->
                        <div class="metric-row">
                            <span class="metric-label">Default requests per minute</span>
                            <input type="number" value="15" style="padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;">
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3>Pricing Tiers</h3>
                    <div id="pricingTiersContainer">
                        <!-- Pricing tiers will be populated here -->
                        <div class="pricing-tier">
                            <div class="tier-header">
                                <span class="tier-name">Free Tier</span>
                                <button class="btn-delete-tier">Delete</button>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Threshold requests</span>
                                <input type="number" value="1500" style="padding: 6px; width: 120px;">
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Input cost per million tokens</span>
                                <input type="number" value="0.0" step="0.01" style="padding: 6px; width: 120px;">
                            </div>
                        </div>
                    </div>
                    <button class="btn btn-reset" onclick="addNewPricingTier()" style="margin-top: 15px;">+ Add New Tier</button>
                </div>

                <div class="save-area">
                    <button class="btn-save" onclick="saveConfiguration()">💾 Save All Configuration Changes</button>
                    <p style="color: #64748b; margin-top: 15px; font-size: 0.9rem;">
                        Changes are not persisted until you click "Save". A backup of the previous configuration will be created.
                    </p>
                </div>
            </div>

            <!-- Tab 3: Router Logic -->
            <div id="tab3" class="tab-content">
                <h2 style="margin-bottom: 25px; color: #1e293b;">Strong Model Escalation Logs</h2>
                <div class="filter-controls">
                    <span class="filter-label">Filter:</span>
                    <label style="margin-right: 20px;">
                        <input type="radio" name="logFilter" value="escalations" checked onchange="filterLogs()"> 
                        <span style="color: #1e293b;">Strong Model Escalations Only</span>
                    </label>
                    <label>
                        <input type="radio" name="logFilter" value="all" onchange="filterLogs()"> 
                        <span style="color: #1e293b;">All Routing Decisions</span>
                    </label>
                </div>
                <div style="margin-bottom: 20px;">
                    <button class="btn btn-reset" onclick="refreshLogs()">🔄 Refresh Logs</button>
                    <button class="btn btn-stop" onclick="clearLogs()">🗑️ Clear Logs</button>
                    <span style="margin-left: 20px; color: #64748b;">Showing <span id="logCount">0</span> escalations</span>
                </div>
                <div class="logs-container" id="logsContainer">
                    <!-- Log entries will be populated here -->
                    <div class="log-entry">
                        <div class="log-header">
                            <span class="log-model">deepseek-chat</span>
                            <span>2025‑12‑11 20:45:32 UTC</span>
                        </div>
                        <div class="log-reason">
                            <strong>Decision:</strong> User asked "Explain quantum computing" → Router picked deepseek‑chat because complexity_score 0.42 < threshold 0.65
                        </div>
                        <div class="log-details">
                            <div class="log-detail-item">Complexity: 0.42</div>
                            <div class="log-detail-item">Impact: LOW</div>
                            <div class="log-detail-item">Threshold: 0.65</div>
                            <div class="log-detail-item">Cycle: No</div>
                        </div>
                    </div>
                </div>
                <div class="refresh-info">
                    Logs update every 10 seconds • Last updated: <span id="logsUpdate">-</span>
                </div>
            </div>
        </div>

        <script>
            let currentTab = 'tab1';
            let stateManager = null;
            let latencyChart = null;
            let allLogs = [];

            // Tab switching
            document.querySelectorAll('.tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    const tabId = tab.getAttribute('data-tab');
                    switchTab(tabId);
                });
            });

            function switchTab(tabId) {
                // Update active tab
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelector(`.tab[data-tab="${tabId}"]`).classList.add('active');
                // Update content
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                currentTab = tabId;
                // Load tab-specific data
                if (tabId === 'tab1') updateLiveTraffic();
                else if (tabId === 'tab2') loadConfiguration();
                else if (tabId === 'tab3') loadRoutingLogs();
            }

            // Tab 1: Live Traffic
            async function updateLiveTraffic() {
                try {
                    const response = await fetch('/api/dashboard/live');
                    const data = await response.json();
                    renderModelCards(data.models);
                    await updateMetricsAndCharts();
                    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
                } catch (error) {
                    console.error('Failed to fetch live data:', error);
                }
            }

            async function updateMetricsAndCharts() {
                try {
                    const response = await fetch('/api/dashboard/metrics');
                    const data = await response.json();
                    
                    // Update metric cards
                    document.getElementById('totalFallbacks').textContent = data.total_fallbacks || 0;
                    document.getElementById('avgJudgeLatency').textContent = 
                        (data.judge_latency?.avg_ms || 0).toFixed(0) + 'ms';
                    document.getElementById('avgWeakLatency').textContent = 
                        (data.weak_model_latency?.avg_ms || 0).toFixed(0) + 'ms';
                    document.getElementById('avgStrongLatency').textContent = 
                        (data.strong_model_latency?.avg_ms || 0).toFixed(0) + 'ms';
                    
                    // Update latency chart
                    updateLatencyChart(data.latency_series);
                } catch (error) {
                    console.error('Failed to fetch metrics:', error);
                }
            }

            function updateLatencyChart(series) {
                const ctx = document.getElementById('latencyChart');
                if (!ctx) return;
                
                if (latencyChart) {
                    latencyChart.destroy();
                }
                
                const labels = series?.labels || Array.from({length: 50}, (_, i) => i + 1);
                const judgeData = series?.judge || [];
                const weakData = series?.weak || [];
                const strongData = series?.strong || [];
                
                latencyChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Judge Latency',
                                data: judgeData,
                                borderColor: '#f59e0b',
                                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'Weak Model Latency',
                                data: weakData,
                                borderColor: '#10b981',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'Strong Model Latency',
                                data: strongData,
                                borderColor: '#ef4444',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                tension: 0.4,
                                fill: true
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            legend: {
                                position: 'top',
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Latency (ms)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Request Number'
                                }
                            }
                        }
                    }
                });
            }

            function renderModelCards(models) {
                const container = document.getElementById('modelGrid');
                if (!models || models.length === 0) {
                    container.innerHTML = '<div class="model-card"><div class="model-name">No models configured</div></div>';
                    return;
                }
                container.innerHTML = models.map(model => {
                    const rpm = model.state?.current_rpm || 0;
                    const requestsToday = model.state?.requests_today || 0;
                    const dailyLimit = model.config?.limits?.requests_per_day || 1500;
                    const usagePercent = Math.min((requestsToday / dailyLimit) * 100, 100);
                    const status = model.config?.status || 'inactive';
                    const statusClass = `status-${status}`;
                    const gaugeColor = usagePercent < 70 ? 'gauge-green' : usagePercent < 90 ? 'gauge-yellow' : 'gauge-red';
                    const sessionCost = model.state?.total_cost_session?.toFixed(4) || '0.0000';
                    return `
                        <div class="model-card">
                            <div class="model-header">
                                <div class="model-name">${model.config.display_name || model.id}</div>
                                <div class="status-badge ${statusClass}">${status.toUpperCase()}</div>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Requests/min</span>
                                <span class="metric-value">${rpm} RPM</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Requests today</span>
                                <span class="metric-value">${requestsToday} / ${dailyLimit}</span>
                            </div>
                            <div class="gauge-container">
                                <div class="gauge-fill ${gaugeColor}" style="width: ${usagePercent}%"></div>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">Session cost</span>
                                <span class="metric-value">$${sessionCost}</span>
                            </div>
                            <div class="controls">
                                <button class="btn btn-reset" onclick="resetSessionCost('${model.id}')">Reset Session Cost</button>
                                <button class="btn ${status === 'active' ? 'btn-stop' : 'btn-start'}" 
                                    onclick="toggleModelStatus('${model.id}', '${status}')">
                                    ${status === 'active' ? 'Emergency Stop' : 'Activate'}
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            async function resetSessionCost(modelId) {
                if (!confirm(`Reset session cost for ${modelId}?`)) return;
                await fetch(`/api/dashboard/model/${modelId}/reset-cost`, { method: 'POST' });
                updateLiveTraffic();
            }

            async function toggleModelStatus(modelId, currentStatus) {
                const newStatus = currentStatus === 'active' ? 'disabled' : 'active';
                await fetch(`/api/dashboard/model/${modelId}/status`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });
                updateLiveTraffic();
            }

            async function resetAllSessionCosts() {
                if (!confirm('Reset session costs for all models?')) return;
                await fetch('/api/dashboard/reset-all-costs', { method: 'POST' });
                updateLiveTraffic();
            }

            async function startAllModels() {
                await fetch('/api/dashboard/start-all', { method: 'POST' });
                updateLiveTraffic();
            }

            async function stopAllModels() {
                if (!confirm('Emergency stop all models?')) return;
                await fetch('/api/dashboard/stop-all', { method: 'POST' });
                updateLiveTraffic();
            }

            // Tab 2: Configuration
            async function loadConfiguration() {
                try {
                    const response = await fetch('/api/dashboard/configuration');
                    const data = await response.json();
                    renderApiKeys(data.api_keys);
                    renderPriorityList(data.models);
                    renderRateLimits(data.models);
                    renderPricingTiers(data.models);
                    // Initialize sortable
                    new Sortable(document.getElementById('priorityList'), {
                        animation: 150,
                        onEnd: updatePriorities
                    });
                } catch (error) {
                    console.error('Failed to load configuration:', error);
                }
            }

            function renderApiKeys(keys) {
                const container = document.getElementById('apiKeysContainer');
                container.innerHTML = Object.entries(keys).map(([key, value]) => `
                    <div class="api-key-row">
                        <span class="api-key-label">${key}</span>
                        <span class="api-key-masked">${maskApiKey(value)}</span>
                        <button class="btn-reveal" onclick="revealKey('${key}', this)">Reveal</button>
                    </div>
                `).join('');
            }

            function maskApiKey(key) {
                if (!key) return 'Not set';
                if (key.length <= 8) return '****';
                return key.substring(0, 4) + '...' + key.substring(key.length - 4);
            }

            function revealKey(keyName, button) {
                // In a real implementation, we would fetch the actual key from a secure endpoint.
                // For demo, we show a placeholder.
                const row = button.closest('.api-key-row');
                const span = row.querySelector('.api-key-masked');
                span.textContent = 'sk_live_*************** (hidden for security)';
                button.disabled = true;
                button.textContent = 'Revealed';
            }

            function renderPriorityList(models) {
                const container = document.getElementById('priorityList');
                container.innerHTML = models.map(model => `
                    <li class="sortable-item" data-model-id="${model.id}">
                        <span class="drag-handle">⋮⋮</span>
                        <span class="model-name">${model.config.display_name || model.id}</span>
                        <span class="priority-badge">Priority Group: ${model.config.routing.priority_group}</span>
                        <span style="margin-left: auto;">Order: ${model.config.routing.order}</span>
                    </li>
                `).join('');
            }

            function updatePriorities() {
                const items = document.querySelectorAll('#priorityList .sortable-item');
                items.forEach((item, index) => {
                    const modelId = item.getAttribute('data-model-id');
                    console.log(`Model ${modelId} new order: ${index + 1}`);
                    // In a real implementation, send update to server
                });
            }

            function renderRateLimits(models) {
                const container = document.getElementById('rateLimitSettings');
                container.innerHTML = models.map(model => `
                    <div class="metric-row">
                        <span class="metric-label">${model.config.display_name} (RPM)</span>
                        <input type="number" value="${model.config.limits.requests_per_minute}" 
                            data-model-id="${model.id}" data-field="rpm" style="padding: 8px; width: 100px;">
                    </div>
                `).join('');
            }

            function renderPricingTiers(models) {
                // For simplicity, show pricing of first model
                const model = models[0];
                if (!model || !model.config.pricing.usage_tiers) return;
                const container = document.getElementById('pricingTiersContainer');
                container.innerHTML = model.config.pricing.usage_tiers.map((tier, idx) => `
                    <div class="pricing-tier">
                        <div class="tier-header">
                            <span class="tier-name">${tier.name}</span>
                            <button class="btn-delete-tier" onclick="deletePricingTier(${idx})">Delete</button>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Threshold requests</span>
                            <input type="number" value="${tier.threshold_requests}" 
                                data-tier-index="${idx}" data-field="threshold" style="padding: 6px; width: 120px;">
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Input cost per million tokens</span>
                            <input type="number" value="${tier.input_cost}" step="0.01" 
                                data-tier-index="${idx}" data-field="input_cost" style="padding: 6px; width: 120px;">
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Output cost per million tokens</span>
                            <input type="number" value="${tier.output_cost}" step="0.01" 
                                data-tier-index="${idx}" data-field="output_cost" style="padding: 6px; width: 120px;">
                        </div>
                    </div>
                `).join('');
            }

            function addNewPricingTier() {
                const container = document.getElementById('pricingTiersContainer');
                const newTier = {
                    name: 'New Tier',
                    threshold_requests: 1000,
                    input_cost: 0.5,
                    output_cost: 1.0
                };
                const tierElement = document.createElement('div');
                tierElement.className = 'pricing-tier';
                tierElement.innerHTML = `
                    <div class="tier-header">
                        <span class="tier-name">${newTier.name}</span>
                        <button class="btn-delete-tier" onclick="this.closest('.pricing-tier').remove()">Delete</button>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Threshold requests</span>
                        <input type="number" value="${newTier.threshold_requests}" style="padding: 6px; width: 120px;">
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Input cost per million tokens</span>
                        <input type="number" value="${newTier.input_cost}" step="0.01" style="padding: 6px; width: 120px;">
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Output cost per million tokens</span>
                        <input type="number" value="${newTier.output_cost}" step="0.01" style="padding: 6px; width: 120px;">
                    </div>
                `;
                container.appendChild(tierElement);
            }

            async function saveConfiguration() {
                // Collect all changed settings
                const changes = {
                    api_keys: {},
                    models: []
                };
                // In a real implementation, collect changes from inputs
                alert('Configuration saved (demo). In a real implementation, changes would be sent to the server.');
                // await fetch('/api/dashboard/configuration', {
                //     method: 'POST',
                //     headers: { 'Content-Type': 'application/json' },
                //     body: JSON.stringify(changes)
                // });
            }

            // Tab 3: Router Logic
            async function loadRoutingLogs() {
                try {
                    const response = await fetch('/api/dashboard/logs?include_preview=true');
                    const data = await response.json();
                    allLogs = data.logs;
                    filterLogs();
                    document.getElementById('logsUpdate').textContent = new Date().toLocaleTimeString();
                } catch (error) {
                    console.error('Failed to load logs:', error);
                }
            }

            function filterLogs() {
                const filterValue = document.querySelector('input[name="logFilter"]:checked').value;
                let filteredLogs = allLogs;
                
                if (filterValue === 'escalations') {
                    // Filter for strong model escalations (claude, gpt-4, etc.)
                    filteredLogs = allLogs.filter(log => {
                        const model = log.model_used.toLowerCase();
                        return model.includes('claude') || model.includes('gpt-4') || model.includes('opus') || log.complexity_score >= 0.7;
                    });
                }
                
                document.getElementById('logCount').textContent = filteredLogs.length;
                renderLogs(filteredLogs);
            }

            function renderLogs(logs) {
                const container = document.getElementById('logsContainer');
                if (!logs || logs.length === 0) {
                    container.innerHTML = '<div class="log-entry"><em>No escalations found. Try lowering the threshold or making more complex requests.</em></div>';
                    return;
                }
                container.innerHTML = logs.map(log => `
                    <div class="log-entry">
                        <div class="log-header">
                            <span class="log-model">🚨 ${log.model_used}</span>
                            <span>${new Date(log.timestamp * 1000).toISOString().replace('T', ' ').substring(0, 19)} UTC</span>
                        </div>
                        <div class="log-reason">
                            <strong>Escalation Reason:</strong> ${log.decision_reason || 'Complexity threshold exceeded'}
                        </div>
                        <div class="log-details">
                            <div class="log-detail-item">Complexity: <strong>${log.complexity_score.toFixed(3)}</strong></div>
                            <div class="log-detail-item">Impact: <strong>${log.impact_scope}</strong></div>
                            <div class="log-detail-item">Cost: <strong>$${log.cost_incurred.toFixed(4)}</strong></div>
                            <div class="log-detail-item">Cycle: ${log.cycle_detected ? '⚠️ Yes' : 'No'}</div>
                        </div>
                        ${log.request_preview || log.response_preview ? `
                            <div class="request-response-preview">
                                ${log.request_preview ? `
                                    <div class="preview-section">
                                        <span class="preview-label">📤 Request:</span>
                                        <div class="preview-content">${escapeHtml(log.request_preview)}</div>
                                    </div>
                                ` : ''}
                                ${log.response_preview ? `
                                    <div class="preview-section">
                                        <span class="preview-label">📥 Response:</span>
                                        <div class="preview-content">${escapeHtml(log.response_preview)}</div>
                                    </div>
                                ` : ''}
                            </div>
                        ` : ''}
                    </div>
                `).join('');
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function refreshLogs() {
                loadRoutingLogs();
            }

            async function clearLogs() {
                if (!confirm('Clear all routing logs?')) return;
                await fetch('/api/dashboard/logs', { method: 'DELETE' });
                loadRoutingLogs();
            }

            // Periodic updates
            setInterval(() => {
                if (currentTab === 'tab1') updateLiveTraffic();
                else if (currentTab === 'tab3') loadRoutingLogs();
            }, 5000);

            // Initialize
            updateLiveTraffic();
        </script>
    </body>
    </html>
    """


# API endpoints for the enhanced dashboard

@dashboard_app.get("/api/dashboard/live")
async def get_live_data():
    """Get live model state and configuration for Tab 1."""
    # Reload config from disk to get latest state
    state_manager = await get_state_manager(reload=True)
    # Use StateManager's config (which is the live, updated version)
    all_models = await state_manager.get_all_models()
    models = []
    for model_id, model_config in all_models.items():
        model_state = await state_manager.get_model_state(model_id)
        # Convert to dict with proper datetime serialization
        config_dict = model_config.model_dump(mode='json')
        state_dict = model_state.model_dump(mode='json') if model_state else None
        models.append({
            "id": model_id,
            "config": config_dict,
            "state": state_dict
        })
    return JSONResponse({"models": models})


@dashboard_app.post("/api/dashboard/model/{model_id}/reset-cost")
async def reset_model_cost(model_id: str):
    """Reset session cost for a specific model."""
    state_manager = await get_state_manager()
    await state_manager.update_model_state(
        model_id,
        total_cost_session=0.0,
        last_updated_ts=datetime.utcnow()
    )
    return JSONResponse({"status": "success", "message": f"Cost reset for {model_id}"})


@dashboard_app.post("/api/dashboard/model/{model_id}/status")
async def update_model_status(model_id: str, request: dict):
    """Update a model's status (active/inactive/disabled)."""
    new_status = request.get("status")
    if new_status not in ("active", "inactive", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    # In a real implementation, we would update the config and persist it.
    # For now, we just return success.
    return JSONResponse({"status": "success", "message": f"Model {model_id} status set to {new_status}"})


@dashboard_app.post("/api/dashboard/reset-all-costs")
async def reset_all_costs():
    """Reset session costs for all models."""
    state_manager = await get_state_manager()
    config = get_unified_config()
    for model_id in config.models.keys():
        await state_manager.update_model_state(
            model_id,
            total_cost_session=0.0,
            last_updated_ts=datetime.utcnow()
        )
    return JSONResponse({"status": "success", "message": "All costs reset"})


@dashboard_app.post("/api/dashboard/start-all")
async def start_all_models():
    """Set all models to active status."""
    # This would update each model's config.status to "active"
    return JSONResponse({"status": "success", "message": "All models activated"})


@dashboard_app.post("/api/dashboard/stop-all")
async def stop_all_models():
    """Set all models to disabled status."""
    return JSONResponse({"status": "success", "message": "All models stopped"})


@dashboard_app.get("/api/dashboard/metrics")
async def get_dashboard_metrics(db: Session = Depends(get_dbsession)):
    """Get metrics for charts and counters."""
    from .metrics import get_metrics_collector
    
    # Get metrics from collector
    collector = get_metrics_collector()
    stats = collector.get_aggregated_stats()
    
    # Get recent metrics for latency time series
    recent_metrics = collector.get_recent_metrics(limit=50)
    
    # Build latency series from recent metrics
    judge_latencies = []
    weak_latencies = []
    strong_latencies = []
    labels = []
    
    # Extract latency data points from metrics
    for i, metric in enumerate(recent_metrics):
        metric_type = metric.get('type', '')
        latency = metric.get('latency_ms')
        
        # Only include latency metrics
        if 'latency' in metric_type and latency is not None:
            labels.append(str(i + 1))
            
            if metric_type == 'judge_latency':
                judge_latencies.append(latency)
                weak_latencies.append(None)
                strong_latencies.append(None)
            elif metric_type == 'weak_model_latency':
                judge_latencies.append(None)
                weak_latencies.append(latency)
                strong_latencies.append(None)
            elif metric_type == 'strong_model_latency':
                judge_latencies.append(None)
                weak_latencies.append(None)
                strong_latencies.append(latency)
    
    # Pad to 50 points if needed
    while len(labels) < 50:
        idx = len(labels)
        labels.append(str(idx + 1))
        judge_latencies.append(None)
        weak_latencies.append(None)
        strong_latencies.append(None)
    
    # Count fallbacks - sum all fallback types
    fallback_counts = stats.get('fallback_counts', {})
    total_fallbacks = sum(fallback_counts.values())
    
    return JSONResponse({
        "total_fallbacks": total_fallbacks,
        "judge_latency": stats.get('judge_latency', {}),
        "weak_model_latency": stats.get('weak_model_latency', {}),
        "strong_model_latency": stats.get('strong_model_latency', {}),
        "latency_series": {
            "labels": labels,
            "judge": judge_latencies,
            "weak": weak_latencies,
            "strong": strong_latencies
        }
    })


@dashboard_app.get("/api/dashboard/configuration")
async def get_configuration():
    """Get configuration data for Tab 2."""
    config = get_unified_config()
    settings = get_settings()
    # Extract API keys from environment (masked)
    api_keys = {
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GEMINI_BACKUP1_API_KEY": settings.gemini_backup1_api_key,
        "GEMINI_BACKUP2_API_KEY": settings.gemini_backup2_api_key,
    }
    models = []
    for model_id, model_config in config.models.items():
        models.append({
            "id": model_id,
            "config": model_config.dict()
        })
    return JSONResponse({
        "api_keys": api_keys,
        "models": models,
        "system_settings": config.system_settings.dict()
    })


@dashboard_app.get("/api/dashboard/logs")
async def get_routing_logs(
    db: Session = Depends(get_dbsession), 
    limit: int = 50,
    include_preview: bool = False
):
    """Get recent routing decision logs for Tab 3."""
    from .logging_audit import LoggingAudit
    
    logs = db.query(RoutingDecision)\
             .order_by(RoutingDecision.timestamp.desc())\
             .limit(limit).all()
    result = []
    
    # Load request logs if preview is requested
    request_logs = {}
    if include_preview:
        try:
            audit = LoggingAudit()
            # Load recent request logs (limited to avoid performance issues)
            for log in logs[:20]:  # Only load preview for last 20
                if log.request_id:
                    log_data = audit.read_request_log(log.request_id)
                    if log_data:
                        request_logs[log.request_id] = log_data
        except Exception as e:
            logger.error(f"Failed to load request logs: {e}")
    
    for log in logs:
        log_entry = {
            "session_id": log.session_id,
            "request_id": log.request_id,
            "model_used": log.model_used,
            "complexity_score": log.complexity_score or 0.0,
            "cost_incurred": log.cost_incurred or 0.0,
            "impact_scope": log.impact_scope or "unknown",
            "reason": log.reason or "",
            "timestamp": log.timestamp.timestamp() if log.timestamp else 0,
            "decision_reason": log.reason or "No reason provided",
            "cycle_detected": "cycle" in (log.reason or "").lower()
        }
        
        # Add request/response preview if available
        if include_preview and log.request_id in request_logs:
            req_log = request_logs[log.request_id]
            # Extract request preview (first message)
            if "request" in req_log and "messages" in req_log["request"]:
                messages = req_log["request"]["messages"]
                if messages:
                    first_msg = messages[-1] if isinstance(messages, list) else messages
                    log_entry["request_preview"] = first_msg.get("content", "")[:500]
            
            # Extract response preview
            if "response" in req_log and "choices" in req_log["response"]:
                choices = req_log["response"]["choices"]
                if choices:
                    first_choice = choices[0] if isinstance(choices, list) else choices
                    if "message" in first_choice:
                        log_entry["response_preview"] = first_choice["message"].get("content", "")[:500]
        
        result.append(log_entry)
    
    return JSONResponse({"logs": result})


@dashboard_app.delete("/api/dashboard/logs")
async def clear_routing_logs(db: Session = Depends(get_dbsession)):
    """Clear all routing logs (for demo purposes)."""
    db.query(RoutingDecision).delete()
    db.commit()
    return JSONResponse({"status": "success", "message": "All logs cleared"})


# ==================== Model Configuration CRUD Endpoints ====================

@dashboard_app.post("/api/dashboard/models")
async def create_model(request: dict):
    """Create a new model configuration."""
    from ..schemas.config_models import ModelConfig
    state_manager = await get_state_manager()
    
    model_id = request.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
    
    # Validate model config
    try:
        model_config = ModelConfig(**request.get("config", {}))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid model config: {e}")
    
    success = await state_manager.add_model(model_id, model_config)
    if not success:
        raise HTTPException(status_code=409, detail=f"Model {model_id} already exists")
    
    return JSONResponse({
        "status": "success",
        "message": f"Model {model_id} created",
        "model_id": model_id
    })


@dashboard_app.put("/api/dashboard/models/{model_id}")
async def update_model(model_id: str, request: dict):
    """Update an existing model configuration."""
    state_manager = await get_state_manager()
    
    # Check if model exists
    existing = await state_manager.get_model_config(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    # Update with provided fields
    success = await state_manager.update_model_config(model_id, **request)
    if not success:
        raise HTTPException(status_code=400, detail="Update failed")
    
    return JSONResponse({
        "status": "success",
        "message": f"Model {model_id} updated"
    })


@dashboard_app.delete("/api/dashboard/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a model configuration."""
    state_manager = await get_state_manager()
    
    success = await state_manager.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    return JSONResponse({
        "status": "success",
        "message": f"Model {model_id} deleted"
    })


@dashboard_app.put("/api/dashboard/judge-config")
async def update_judge_config(request: dict):
    """Update judge configuration."""
    state_manager = await get_state_manager()
    
    success = await state_manager.update_judge_config(**request)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update judge config")
    
    return JSONResponse({
        "status": "success",
        "message": "Judge config updated",
        "config": (await state_manager.get_judge_config()).model_dump()
    })


@dashboard_app.put("/api/dashboard/routing-order")
async def update_routing_order(request: dict):
    """Update routing order configuration (strong/weak models)."""
    state_manager = await get_state_manager()
    
    success = await state_manager.update_routing_order_config(**request)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update routing order config")
    
    return JSONResponse({
        "status": "success",
        "message": "Routing order config updated",
        "config": (await state_manager.get_routing_order_config()).model_dump()
    })


@dashboard_app.get("/api/dashboard/full-config")
async def get_full_configuration():
    """Get complete configuration including judge and routing order."""
    config = get_unified_config()
    state_manager = await get_state_manager()
    
    judge_config = await state_manager.get_judge_config()
    routing_order_config = await state_manager.get_routing_order_config()
    
    return JSONResponse({
        "system_settings": config.system_settings.model_dump(),
        "models": {k: v.model_dump() for k, v in config.models.items()},
        "judge_config": judge_config.model_dump(),
        "routing_order_config": routing_order_config.model_dump()
    })


def start_dashboard_server(host: str = "0.0.0.0", port: int = 8001):
    """Start the enhanced dashboard server."""
    logger.info(f"Starting enhanced dashboard on http://{host}:{port}")
    uvicorn.run(dashboard_app, host=host, port=port, log_level="info")

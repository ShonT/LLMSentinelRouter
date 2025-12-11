"""
Web dashboard for SentinelRouter metrics.

Provides:
- Real-time metrics visualization
- Historical data charts
- System health overview
- Accessible via http://localhost:8001/dashboard
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from typing import Dict, Any
import logging

from .metrics import get_metrics_collector

logger = logging.getLogger(__name__)

# Create dashboard app
dashboard_app = FastAPI(title="SentinelRouter Metrics Dashboard")


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_home():
    """Serve the main dashboard page."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SentinelRouter Metrics Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            h1 {
                color: white;
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5rem;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .header-controls {
                display: flex;
                justify-content: center;
                align-items: center;
                margin-bottom: 30px;
                gap: 20px;
            }
            .reset-button {
                background: #ef4444;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            .reset-button:hover {
                background: #dc2626;
                transform: translateY(-2px);
                box-shadow: 0 6px 12px rgba(0,0,0,0.2);
            }
            .reset-button:active {
                transform: translateY(0);
            }
            .reset-button:disabled {
                background: #9ca3af;
                cursor: not-allowed;
                transform: none;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 12px rgba(0,0,0,0.15);
            }
            .stat-label {
                font-size: 0.9rem;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 8px;
            }
            .stat-value {
                font-size: 2rem;
                font-weight: bold;
                color: #333;
            }
            .stat-unit {
                font-size: 1rem;
                color: #999;
                margin-left: 5px;
            }
            .charts-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                gap: 20px;
            }
            .chart-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            .chart-title {
                font-size: 1.2rem;
                font-weight: 600;
                margin-bottom: 15px;
                color: #333;
            }
            .status-indicator {
                display: inline-block;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 8px;
            }
            .status-healthy { background: #10b981; }
            .status-warning { background: #f59e0b; }
            .status-error { background: #ef4444; }
            .refresh-info {
                text-align: center;
                color: white;
                margin-top: 20px;
                font-size: 0.9rem;
                opacity: 0.8;
            }
            .strong-model-section {
                margin-top: 30px;
            }
            .section-title {
                color: white;
                font-size: 1.8rem;
                margin-bottom: 20px;
                text-align: center;
            }
            .escalations-table-wrapper {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                overflow-x: auto;
            }
            .escalations-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.9rem;
            }
            .escalations-table thead {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .escalations-table th {
                padding: 12px;
                text-align: left;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.75rem;
                letter-spacing: 0.5px;
                white-space: nowrap;
            }
            .escalations-table td {
                padding: 12px;
                border-bottom: 1px solid #e5e7eb;
                vertical-align: top;
            }
            .escalations-table tbody tr:hover {
                background-color: #f9fafb;
            }
            .escalations-table tbody tr:last-child td {
                border-bottom: none;
            }
            .timestamp-cell {
                color: #6b7280;
                font-size: 0.85rem;
                white-space: nowrap;
            }
            .model-cell {
                font-weight: 700;
                color: #ef4444;
            }
            .reason-cell {
                background: #fef3c7;
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 0.85rem;
                color: #92400e;
                font-weight: 500;
                max-width: 300px;
            }
            .text-preview {
                max-width: 400px;
                max-height: 100px;
                overflow-y: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.8rem;
                background: #f3f4f6;
                padding: 8px;
                border-radius: 6px;
                line-height: 1.4;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .cycle-badge {
                background: #fee2e2;
                color: #991b1b;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
                display: inline-block;
                margin-bottom: 4px;
            }
            .no-usage {
                text-align: center;
                color: white;
                font-size: 1.1rem;
                padding: 40px;
                opacity: 0.7;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 SentinelRouter Metrics Dashboard</h1>
            
            <div class="header-controls">
                <button class="reset-button" id="resetButton" onclick="resetMetrics()">🗑️ Reset All Metrics</button>
            </div>
            
            <div class="stats-grid" id="statsGrid">
                <!-- Stats will be populated by JavaScript -->
            </div>
            
            <div class="charts-grid">
                <div class="chart-card">
                    <div class="chart-title">Judge Latency (ms)</div>
                    <canvas id="judgeLatencyChart"></canvas>
                </div>
                
                <div class="chart-card">
                    <div class="chart-title">Model Latency (ms)</div>
                    <canvas id="modelLatencyChart"></canvas>
                </div>
                
                <div class="chart-card">
                    <div class="chart-title">Fallback Occurrences</div>
                    <canvas id="fallbackChart"></canvas>
                </div>
                
                <div class="chart-card">
                    <div class="chart-title">Tokens Per Second</div>
                    <canvas id="tpsChart"></canvas>
                </div>
            </div>
            
            <div class="strong-model-section">
                <h2 class="section-title">🔴 Escalations to Strong Model</h2>
                <div id="strongModelUsages">
                    <div class="no-usage">No escalations recorded yet</div>
                </div>
            </div>
            
            <div class="refresh-info">
                Auto-refreshing every 5 seconds • Last updated: <span id="lastUpdate">-</span>
            </div>
        </div>
        
        <script>
            let charts = {};
            
            // Initialize charts
            function initCharts() {
                // Judge Latency Chart
                charts.judgeLatency = new Chart(document.getElementById('judgeLatencyChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Avg', 'Min', 'Max', 'P95', 'P99'],
                        datasets: [{
                            label: 'Latency (ms)',
                            data: [0, 0, 0, 0, 0],
                            backgroundColor: 'rgba(102, 126, 234, 0.8)',
                            borderColor: 'rgba(102, 126, 234, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        scales: { y: { beginAtZero: true } }
                    }
                });
                
                // Model Latency Chart
                charts.modelLatency = new Chart(document.getElementById('modelLatencyChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Weak Avg', 'Weak P95', 'Strong Avg', 'Strong P95'],
                        datasets: [{
                            label: 'Latency (ms)',
                            data: [0, 0, 0, 0],
                            backgroundColor: [
                                'rgba(16, 185, 129, 0.8)',
                                'rgba(16, 185, 129, 0.6)',
                                'rgba(245, 158, 11, 0.8)',
                                'rgba(245, 158, 11, 0.6)'
                            ],
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        scales: { y: { beginAtZero: true } }
                    }
                });
                
                // Fallback Chart
                charts.fallback = new Chart(document.getElementById('fallbackChart'), {
                    type: 'doughnut',
                    data: {
                        labels: ['Judge', 'Weak Model', 'Strong Model'],
                        datasets: [{
                            data: [0, 0, 0],
                            backgroundColor: [
                                'rgba(239, 68, 68, 0.8)',
                                'rgba(245, 158, 11, 0.8)',
                                'rgba(59, 130, 246, 0.8)'
                            ]
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true
                    }
                });
                
                // TPS Chart
                charts.tps = new Chart(document.getElementById('tpsChart'), {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'Tokens/sec',
                            data: [],
                            borderColor: 'rgba(118, 75, 162, 1)',
                            backgroundColor: 'rgba(118, 75, 162, 0.2)',
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        scales: { y: { beginAtZero: true } }
                    }
                });
            }
            
            // Update dashboard
            async function updateDashboard() {
                try {
                    const response = await fetch('/api/metrics');
                    const data = await response.json();
                    
                    // Update stats cards
                    updateStatsCards(data);
                    
                    // Update charts
                    updateCharts(data);
                    
                    // Update strong model usage
                    updateStrongModelUsages(data);
                    
                    // Update timestamp
                    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
                } catch (error) {
                    console.error('Failed to fetch metrics:', error);
                }
            }
            
            function updateStatsCards(data) {
                const stats = data.aggregated_stats;
                const html = `
                    <div class="stat-card">
                        <div class="stat-label">Total Requests</div>
                        <div class="stat-value">${stats.total_metrics || 0}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Avg Judge Latency</div>
                        <div class="stat-value">
                            ${(stats.judge_latency?.avg || 0).toFixed(1)}
                            <span class="stat-unit">ms</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Avg Weak Model Latency</div>
                        <div class="stat-value">
                            ${(stats.weak_model_latency?.avg || 0).toFixed(1)}
                            <span class="stat-unit">ms</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Avg Strong Model Latency</div>
                        <div class="stat-value">
                            ${(stats.strong_model_latency?.avg || 0).toFixed(1)}
                            <span class="stat-unit">ms</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Cycle Detections</div>
                        <div class="stat-value">${stats.cycle_detection_count || 0}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Avg Tokens/sec</div>
                        <div class="stat-value">
                            ${(stats.tokens_per_second?.avg || 0).toFixed(1)}
                            <span class="stat-unit">tok/s</span>
                        </div>
                    </div>
                `;
                document.getElementById('statsGrid').innerHTML = html;
            }
            
            function updateCharts(data) {
                const stats = data.aggregated_stats;
                
                // Update Judge Latency
                const jl = stats.judge_latency || {};
                charts.judgeLatency.data.datasets[0].data = [
                    jl.avg || 0, jl.min || 0, jl.max || 0, jl.p95 || 0, jl.p99 || 0
                ];
                charts.judgeLatency.update();
                
                // Update Model Latency
                const wl = stats.weak_model_latency || {};
                const sl = stats.strong_model_latency || {};
                charts.modelLatency.data.datasets[0].data = [
                    wl.avg || 0, wl.p95 || 0, sl.avg || 0, sl.p95 || 0
                ];
                charts.modelLatency.update();
                
                // Update Fallback
                const fb = stats.fallback_counts || {};
                charts.fallback.data.datasets[0].data = [
                    fb.judge_fallback || 0,
                    fb.weak_model_fallback || 0,
                    fb.strong_model_fallback || 0
                ];
                charts.fallback.update();
                
                // Update TPS (show last 20 data points)
                const recentMetrics = data.recent_metrics || [];
                const tpsMetrics = recentMetrics
                    .filter(m => m.type === 'tokens_per_second')
                    .slice(-20);
                
                charts.tps.data.labels = tpsMetrics.map((_, i) => i + 1);
                charts.tps.data.datasets[0].data = tpsMetrics.map(m => m.tps);
                charts.tps.update();
            }
            
            function updateStrongModelUsages(data) {
                const usages = data.aggregated_stats?.strong_model_usages || [];
                const container = document.getElementById('strongModelUsages');
                
                if (usages.length === 0) {
                    container.innerHTML = '<div class="no-usage">No escalations recorded yet</div>';
                    return;
                }
                
                // Show most recent usages (last 20) in reverse order (newest first)
                const recentUsages = usages.slice(-20).reverse();
                
                const rows = recentUsages.map(usage => {
                    const date = new Date(usage.timestamp * 1000);
                    const timeStr = date.toLocaleString();
                    
                    // Build reason with cycle badge if applicable
                    let reasonHtml = escapeHtml(usage.reason);
                    if (usage.cycle_detected) {
                        reasonHtml = '<span class="cycle-badge">⚠️ CYCLE DETECTED</span><br>' + reasonHtml;
                        if (usage.cycle_history && usage.cycle_history.length > 0) {
                            reasonHtml += '<br><small style="font-size:0.75rem;color:#7f1d1d;">Hashes: ' + 
                                         usage.cycle_history.slice(-3).join(' → ') + '</small>';
                        }
                    }
                    
                    // Truncate and escape request/response
                    const requestPreview = usage.request_preview ? 
                        escapeHtml(usage.request_preview.substring(0, 200) + (usage.request_preview.length > 200 ? '...' : '')) : 
                        '<em>N/A</em>';
                    
                    const responsePreview = usage.response_preview ? 
                        escapeHtml(usage.response_preview.substring(0, 200) + (usage.response_preview.length > 200 ? '...' : '')) : 
                        '<em>N/A</em>';
                    
                    return `
                        <tr>
                            <td class="timestamp-cell">${timeStr}</td>
                            <td class="text-preview">${requestPreview}</td>
                            <td class="text-preview">${responsePreview}</td>
                            <td class="model-cell">${escapeHtml(usage.model_id)}</td>
                            <td class="reason-cell">${reasonHtml}</td>
                        </tr>
                    `;
                }).join('');
                
                const tableHtml = `
                    <div class="escalations-table-wrapper">
                        <table class="escalations-table">
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Request</th>
                                    <th>Response</th>
                                    <th>Model</th>
                                    <th>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rows}
                            </tbody>
                        </table>
                    </div>
                `;
                
                container.innerHTML = tableHtml;
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // Reset metrics function
            async function resetMetrics() {
                if (!confirm('Are you sure you want to reset all metrics to zero? This action cannot be undone.')) {
                    return;
                }
                
                const button = document.getElementById('resetButton');
                button.disabled = true;
                button.textContent = '⏳ Resetting...';
                
                try {
                    const response = await fetch('/api/metrics/reset', {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        alert(data.message || 'Metrics reset successfully!');
                        // Immediately refresh dashboard
                        await updateDashboard();
                    } else {
                        alert('Failed to reset metrics. Please try again.');
                    }
                } catch (error) {
                    console.error('Reset failed:', error);
                    alert('Error resetting metrics: ' + error.message);
                } finally {
                    button.disabled = false;
                    button.textContent = '🗑️ Reset All Metrics';
                }
            }
            
            // Initialize and start auto-refresh
            initCharts();
            updateDashboard();
            setInterval(updateDashboard, 5000);
        </script>
    </body>
    </html>
    """


@dashboard_app.get("/api/metrics")
async def get_metrics() -> JSONResponse:
    """API endpoint to get current metrics."""
    collector = get_metrics_collector()
    
    # Reload recent metrics from file to get latest data
    collector._load_recent_metrics()
    
    return JSONResponse({
        "aggregated_stats": collector.get_aggregated_stats(),
        "recent_metrics": collector.get_recent_metrics(limit=100),
        "timestamp": collector.recent_metrics[-1]["timestamp"] if collector.recent_metrics else 0
    })


@dashboard_app.delete("/api/metrics/reset")
async def reset_metrics() -> JSONResponse:
    """API endpoint to reset all metrics to zero."""
    collector = get_metrics_collector()
    collector.reset_metrics()
    return JSONResponse({
        "status": "success",
        "message": "All metrics have been reset to zero"
    })


def start_dashboard_server(host: str = "0.0.0.0", port: int = 8001):
    """Start the dashboard server."""
    logger.info(f"Starting metrics dashboard on http://{host}:{port}/dashboard")
    uvicorn.run(dashboard_app, host=host, port=port, log_level="info")

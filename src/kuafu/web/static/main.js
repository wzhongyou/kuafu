// kuafu Dashboard — SSE + REST 客户端

let eventSource = null;
let resultCount = 0;
let elapsedInterval = null;
let startTime = 0;

// ── SSE ──

function connectSSE() {
    if (eventSource) eventSource.close();

    eventSource = new EventSource('/api/events');

    eventSource.addEventListener('crawl_started', (e) => {
        const data = JSON.parse(e.data);
        showStatusPanel();
        setState('running', 'Running');
        startElapsed();
    });

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        document.getElementById('pages-crawled').textContent = data.pages_crawled || 0;
        document.getElementById('pages-failed').textContent = data.pages_failed || 0;
        document.getElementById('urls-discovered').textContent = data.urls_discovered || 0;
    });

    eventSource.addEventListener('url_fetched', (e) => {
        const data = JSON.parse(e.data);
        resultCount++;
        document.getElementById('result-count').textContent = resultCount;
        addResultRow(data);
    });

    eventSource.addEventListener('url_failed', (e) => {
        const data = JSON.parse(e.data);
    });

    eventSource.addEventListener('crawl_stopped', (e) => {
        const data = JSON.parse(e.data);
        setState('completed', 'Completed');
        stopElapsed();
        showActionsPanel();
        // 刷新最终状态
        fetch('/api/status').then(r => r.json()).then(s => {
            document.getElementById('pages-crawled').textContent = s.pages_crawled || 0;
            document.getElementById('pages-failed').textContent = s.pages_failed || 0;
            document.getElementById('urls-discovered').textContent = s.urls_discovered || 0;
        });
    });

    eventSource.onerror = () => {
        eventSource.close();
        setTimeout(connectSSE, 3000);
    };
}

// ── Crawl Control ──

async function startCrawl(event) {
    event.preventDefault();
    const url = document.getElementById('seed-url').value;
    const maxDepth = parseInt(document.getElementById('max-depth').value) || 2;
    const maxPages = parseInt(document.getElementById('max-pages').value) || 100;

    clearResults();
    resultCount = 0;
    document.getElementById('result-count').textContent = '0';

    const resp = await fetch('/api/crawl/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, max_depth: maxDepth, max_pages: maxPages}),
    });

    if (resp.ok) {
        document.getElementById('start-btn').disabled = true;
    } else {
        const err = await resp.json();
        alert(err.detail || 'Failed to start crawl');
    }
}

async function controlCrawl(action) {
    const resp = await fetch(`/api/crawl/${action}`, {method: 'POST'});
    if (resp.ok) {
        if (action === 'pause') {
            setState('paused', 'Paused');
            document.getElementById('pause-btn').style.display = 'none';
            document.getElementById('resume-btn').style.display = '';
        } else if (action === 'resume') {
            setState('running', 'Running');
            document.getElementById('pause-btn').style.display = '';
            document.getElementById('resume-btn').style.display = 'none';
        } else if (action === 'stop') {
            setState('stopped', 'Stopped');
            stopElapsed();
            showActionsPanel();
        }
    }
}

// ── Export ──

async function exportJsonl() {
    const resp = await fetch('/api/crawl/export', {method: 'POST'});
    if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'search-index.jsonl';
        a.click();
        URL.revokeObjectURL(url);
    } else {
        const err = await resp.json();
        alert(err.detail || 'Export failed');
    }
}

// ── Build Vortex Index ──

async function buildIndex() {
    const vortexUrl = document.getElementById('vortex-url').value.trim();
    if (!vortexUrl) {
        alert('Please enter Vortex URL');
        return;
    }

    const resultEl = document.getElementById('index-result');
    resultEl.style.display = 'block';
    resultEl.className = 'result-msg';
    resultEl.textContent = 'Building index...';

    try {
        const resp = await fetch('/api/crawl/build-index', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({vortex_url: vortexUrl}),
        });
        const data = await resp.json();
        if (resp.ok) {
            resultEl.className = 'result-msg success';
            resultEl.textContent = `Index built: ${data.success} success, ${data.failed} failed (total: ${data.total})`;
        } else {
            resultEl.className = 'result-msg error';
            resultEl.textContent = `Error: ${data.detail}`;
        }
    } catch (e) {
        resultEl.className = 'result-msg error';
        resultEl.textContent = `Error: ${e.message}`;
    }
}

// ── UI Helpers ──

function showStatusPanel() {
    document.getElementById('status-panel').style.display = '';
    document.getElementById('pause-btn').style.display = '';
    document.getElementById('resume-btn').style.display = 'none';
}

function showActionsPanel() {
    document.getElementById('actions-panel').style.display = '';
    document.getElementById('start-btn').disabled = false;
}

function setState(state, text) {
    const dot = document.getElementById('state-indicator');
    dot.className = 'state-dot ' + state;
    document.getElementById('state-text').textContent = text;
}

function startElapsed() {
    startTime = Date.now();
    if (elapsedInterval) clearInterval(elapsedInterval);
    elapsedInterval = setInterval(() => {
        const s = Math.round((Date.now() - startTime) / 1000);
        const m = Math.floor(s / 60);
        document.getElementById('elapsed').textContent = m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
    }, 1000);
}

function stopElapsed() {
    if (elapsedInterval) clearInterval(elapsedInterval);
}

function addResultRow(data) {
    const tbody = document.getElementById('results-body');
    const row = document.createElement('tr');
    const statusClass = data.status_code >= 400 ? 'color:var(--danger)' : '';
    const detailUrl = `/detail?url=${encodeURIComponent(data.url)}`;
    row.innerHTML = `
        <td style="${statusClass}">${data.status_code}</td>
        <td><a href="${detailUrl}">${escapeHtml(data.url)}</a></td>
        <td>${escapeHtml(data.title)}</td>
        <td>${data.duration}s</td>
    `;
    tbody.insertBefore(row, tbody.firstChild);
}

function clearResults() {
    document.getElementById('results-body').innerHTML = '';
    document.getElementById('pages-crawled').textContent = '0';
    document.getElementById('pages-failed').textContent = '0';
    document.getElementById('urls-discovered').textContent = '0';
    document.getElementById('elapsed').textContent = '0s';
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

// ── Init ──
connectSSE();

// 加载初始状态
fetch('/api/status').then(r => r.json()).then(s => {
    if (s.state && s.state !== 'idle') {
        showStatusPanel();
        setState(s.state, s.state.charAt(0).toUpperCase() + s.state.slice(1));
        if (s.state === 'paused') {
            document.getElementById('pause-btn').style.display = 'none';
            document.getElementById('resume-btn').style.display = '';
        }
        if (s.state === 'completed' || s.state === 'stopped') {
            stopElapsed();
            showActionsPanel();
        } else {
            startElapsed();
        }
        document.getElementById('pages-crawled').textContent = s.pages_crawled || 0;
        document.getElementById('pages-failed').textContent = s.pages_failed || 0;
        document.getElementById('urls-discovered').textContent = s.urls_discovered || 0;
        document.getElementById('result-count').textContent = s.result_count || 0;
        resultCount = s.result_count || 0;

        // 加载已有结果
        fetch('/api/results').then(r => r.json()).then(results => {
            results.reverse().forEach(addResultRow);
        });
    }
});

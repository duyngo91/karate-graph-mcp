// KARATE COMMAND CENTER - CORE LOGIC

var isFocused = false;
var currentTab = 'HOTSPOTS';

// --- SIDEBAR & TABS ---
function switchTab(tabId) {
    currentTab = tabId;
    
    // Toggle tab active class
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(t => {
        const isMatch = t.getAttribute('onclick').includes(`'${tabId}'`);
        t.classList.toggle('active', isMatch);
    });
    
    // Toggle content visibility
    document.getElementById('hotspots-content').style.display = tabId === 'hotspots' ? 'block' : 'none';
    document.getElementById('timeline-content').style.display = tabId === 'timeline' ? 'block' : 'none';
    document.getElementById('legend-content').style.display = tabId === 'legend' ? 'block' : 'none';
}

function jumpToNode(nodeId) {
    focusOnNode(nodeId);
}

// --- SEARCH ---
function handleSearch(query) {
    const resultsDiv = document.getElementById('search-results');
    if (!query || query.length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }

    const matches = [];
    const searchTerms = query.toLowerCase().split(' ');
    
    for (const id in nodeMetadata) {
        const node = nodeMetadata[id];
        const data = node.additional_data?.display_data;
        if (!data) continue;

        const text = (data.name + ' ' + (data.type_label || '')).toLowerCase();
        if (searchTerms.every(t => text.includes(t))) {
            matches.push({ id, ...data });
        }
        if (matches.length >= 15) break;
    }

    if (matches.length > 0) {
        resultsDiv.innerHTML = matches.map(m => `
            <div class="search-result-item" onclick="focusOnNode('${m.id}')" style="padding: 8px; border-bottom: 1px solid #eee; cursor: pointer; display: flex; justify-content: space-between;">
                <span style="font-size: 13px;">${m.name}</span>
                <span style="font-size: 10px; background: #eee; padding: 2px 4px; border-radius: 4px;">${m.type_label}</span>
            </div>
        `).join('');
        resultsDiv.style.display = 'block';
    } else {
        resultsDiv.style.display = 'none';
    }
}

// --- NODE INTERACTION (X-RAY MODE) ---
function focusOnNode(nodeId) {
    document.getElementById('search-results').style.display = 'none';
    const node = nodeMetadata[nodeId];
    if (!node) return;
    
    const affectedIds = new Set([nodeId]);
    if (hotspotData) {
        const hs = hotspotData.find(h => h.node_id === nodeId);
        if (hs) hs.affected_failed_test_cases.forEach(tc => affectedIds.add(tc.id));
    }

    // Ghost out others
    const allIds = nodes.getIds();
    nodes.update(allIds.map(id => ({
        id: id,
        opacity: affectedIds.has(id) ? 1.0 : 0.1,
        font: { color: affectedIds.has(id) ? '#000' : 'rgba(0,0,0,0.1)' }
    })));
    
    isFocused = true;
    network.focus(nodeId, { scale: 1.0, animation: { duration: 800 } });
    network.selectNodes([nodeId]);
    showDetails(nodeId);
}

function resetFocus() {
    if (!isFocused) return;
    const allIds = nodes.getIds();
    nodes.update(allIds.map(id => ({ id, opacity: 1.0, font: { color: '#000' } })));
    isFocused = false;
    hideDetails();
}

function hideDetails() {
    document.getElementById('node-details-side').style.display = 'none';
}

function showDetails(nodeId) {
    const node = nodeMetadata[nodeId];
    if (!node || !node.additional_data?.display_data) return;

    const data = node.additional_data.display_data;
    const sidePanel = document.getElementById('node-details-side');
    const content = document.getElementById('details-content');
    
    let html = `
        <div class="detail-section">
            <div class="detail-label">Component Name</div>
            <div class="detail-value" style="font-size: 16px; font-weight: 700;">${data.name}</div>
            <div style="font-size: 10px; color: #888; margin-top: 4px;">ID: ${nodeId}</div>
        </div>
        
        <div class="detail-section">
            <div class="detail-label">Type & Status</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                ${data.badges.map(b => `<span class="impact-badge badge-type">${b}</span>`).join('')}
                <span class="impact-badge ${data.status === 'PASSED' ? 'badge-passed' : 'badge-failed'}" 
                      style="background: ${data.status === 'PASSED' ? '#e8f5e9' : '#ffebee'}; color: ${data.status === 'PASSED' ? '#2e7d32' : '#c62828'};">
                    ${data.status}
                </span>
            </div>
        </div>
    `;

    // File Info
    if (data.file_path) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Source Location</div>
                <div class="detail-value" style="font-family: monospace; font-size: 11px;">
                    ${data.file_path}${data.line_number ? `:${data.line_number}` : ''}
                </div>
            </div>
        `;
    }

    // Execution History
    if (data.execution_history && data.execution_history.length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Execution History (Last 10)</div>
                <div class="history-timeline">
                    ${data.execution_history.slice(-10).map(s => `
                        <div class="dot ${s === 'PASSED' ? 'pass' : 'fail'}" title="${s}"></div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Jira Links
    if (data.jira_tags && data.jira_tags.length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label">Jira Traceability</div>
                <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px;">
                    ${data.jira_tags.map(tag => {
                        const cleanTag = tag.replace('@', '');
                        const url = jiraBaseUrl ? `${jiraBaseUrl}${cleanTag}` : '#';
                        return `<a href="${url}" target="_blank" class="badge-utility" style="text-decoration: none; font-size: 10px;">${tag}</a>`;
                    }).join('')}
                </div>
            </div>
        `;
    }

    // AI Expert Analysis (The fix for missing notes)
    if (data.expert_notes && data.expert_notes.length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label" style="color: #1976D2;"><i class="fas fa-robot"></i> Expert Analysis</div>
                ${data.expert_notes.map(note => `
                    <div style="background: #E3F2FD; padding: 10px; border-radius: 8px; border: 1px solid #BBDEFB; margin-top: 10px; font-size: 11px;">
                        <div style="color: #0D47A1; font-weight: 700; margin-bottom: 3px;">${note.timestamp ? `Note from AI Assistant (${note.timestamp}):` : 'Architectural Note:'}</div>
                        <div>${note.note}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // AI Suggestions
    if (data.suggestions && data.suggestions.length > 0) {
        html += `
            <div class="detail-section">
                <div class="detail-label">💡 AI Fix Intelligence</div>
                ${data.suggestions.map(s => `
                    <div style="background: #fffde7; padding: 10px; border-radius: 8px; border: 1px solid #fff59d; margin-top: 10px;">
                        <div style="font-weight: 700; color: #827717; font-size: 12px;">${s.description}</div>
                        ${s.solution ? `<div style="font-family: monospace; font-size: 11px; margin-top: 5px; background: #fff; padding: 5px; border: 1px solid #eee;">${s.solution}</div>` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Internal Failures (for hotspots)
    if (data.status !== 'PASSED') {
        const failedChildren = [];
        edges.get().forEach(edge => {
            if (edge.from === nodeId) {
                const child = nodeMetadata[edge.to];
                if (child && (child.execution_status === 'FAILED' || child.execution_status === 'PARTIAL_FAIL')) {
                    failedChildren.push({ id: edge.to, name: child.name });
                }
            }
        });

        if (failedChildren.length > 0) {
            html += `
                <div class="detail-section">
                    <div class="detail-label" style="color: #d32f2f;"><i class="fas fa-search-location"></i> Failing Components Inside</div>
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                        ${failedChildren.map(child => `
                            <div class="error-box" style="border-left: 4px solid #f44336; cursor: pointer; transition: 0.2s;" 
                                 onclick="jumpToNode('${child.id}')" onmouseover="this.style.background='#ffebee'" onmouseout="this.style.background='#fff5f5'">
                                <div style="font-weight: 700; font-size: 11px; color: #b71c1c;">${child.name}</div>
                                <div style="font-size: 9px; color: #1976d2; margin-top: 4px; font-weight: 800;">🔍 CLICK TO FOCUS ON MAP</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
    }

    content.innerHTML = html;
    sidePanel.style.display = 'block';
}

// --- DASHBOARD RENDERING ---
function renderDashboard() {
    // 1. Hotspots in Sidebar
    const hotspotList = document.getElementById('hotspot-list');
    
    // Calculate total project failures first for contribution ratio
    let totalProjectFailures = 0;
    for (const id in nodeMetadata) {
        const node = nodeMetadata[id];
        const data = node.additional_data?.display_data;
        if (!data) continue;
        
        // Ensure we count all terminal failure points (Test Cases or Scenarios)
        if ((data.type_label === 'TEST_CASE' || data.type_label === 'SCENARIO') && data.status === 'FAILED') {
            totalProjectFailures++;
        }
    }

    if (hotspotData && hotspotData.length > 0) {
        hotspotList.innerHTML = hotspotData.map(hs => {
            const failedCount = hs.failed_test_cases || 0;
            const totalCount = hs.total_test_cases || 1;
            
            // Safe calculation for contribution
            const contribution = totalProjectFailures > 0 
                ? Math.round((failedCount / totalProjectFailures) * 100) 
                : 0;
            
            const isRootCause = contribution >= 50; // If responsible for half of failures
            
            return `
                <div class="hotspot-item ${isRootCause ? 'pulse-fail' : ''}" onclick="focusOnNode('${hs.node_id}')" 
                     style="border-left: 4px solid ${isRootCause ? '#d32f2f' : '#ffa000'};">
                    <div class="hotspot-header">
                        <div style="font-weight: 800; font-size: 13px; color: #1a237e;">${hs.name}</div>
                        <span class="impact-badge" style="background: ${isRootCause ? '#d32f2f' : '#ff9800'}; font-size: 10px;">
                            ${contribution}% OF TOTAL FAILURES
                        </span>
                    </div>
                    <div style="margin-top: 8px; font-size: 11px; color: #444;">
                        <i class="fas fa-exclamation-triangle" style="color: #f44336;"></i> 
                        <b>${hs.failed_test_cases} / ${hs.total_test_cases}</b> tests failed in this path
                    </div>
                    ${isRootCause ? '<div style="margin-top: 5px; font-size: 9px; font-weight: 900; color: #d32f2f; text-transform: uppercase;">🚩 CRITICAL ROOT CAUSE</div>' : ''}
                </div>
            `;
        }).join('');
    }

    // 2. Summary HUD
    let total = 0, passed = 0, failed = 0;
    for (const id in nodeMetadata) {
        const node = nodeMetadata[id];
        if (node.type === 'TEST_CASE') {
            total++;
            if (node.execution_status === 'PASSED') passed++;
            else if (node.execution_status === 'FAILED') failed++;
        }
    }

    if (total > 0 && activeMode === 'EXECUTION') {
        const rate = Math.round((passed / total) * 100);
        const summary = document.getElementById('status-summary');
        summary.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div onclick="filterNodes('all')" style="cursor: pointer;">
                    <div style="font-size: 10px; color: #999; font-weight: 800;">SUCCESS RATE</div>
                    <div style="font-size: 32px; font-weight: 900; color: ${rate >= 90 ? '#4caf50' : '#f44336'};">${rate}%</div>
                </div>
                <div style="display: flex; gap: 20px; text-align: right;">
                    <div onclick="filterNodes('passed')" style="cursor: pointer;">
                        <div style="font-size: 10px; color: #4caf50; font-weight: 800;">PASS</div>
                        <div style="font-size: 18px; font-weight: 800; color: #2e7d32;">${passed}</div>
                    </div>
                    <div onclick="filterNodes('failed')" style="cursor: pointer;">
                        <div style="font-size: 10px; color: #f44336; font-weight: 800;">FAIL</div>
                        <div style="font-size: 18px; font-weight: 800; color: #c62828;">${failed}</div>
                    </div>
                    <div onclick="filterNodes('all')" style="cursor: pointer;">
                        <div style="font-size: 10px; color: #999; font-weight: 800;">TOTAL</div>
                        <div style="font-size: 18px; font-weight: 800; color: #444;">${total}</div>
                    </div>
                    <div onclick="switchTab('legend')" style="cursor: pointer; border-left: 1px solid #ddd; padding-left: 15px; margin-left: 5px;">
                        <div style="font-size: 10px; color: #1976d2; font-weight: 800;">LEGEND</div>
                        <div style="font-size: 18px; font-weight: 800; color: #1976d2;">📖</div>
                    </div>
                </div>
            </div>
        `;
        summary.style.display = 'block';
    }
}

// --- FILTERING & TABS ---
function filterNodes(status) {
    const allNodes = nodes.get();
    const updates = allNodes.map(node => {
        const metadata = nodeMetadata[node.id];
        let hidden = false;
        
        if (status === 'failed') {
            hidden = (metadata.execution_status !== 'FAILED');
        } else if (status === 'passed') {
            hidden = (metadata.execution_status !== 'PASSED');
        }
        
        return { id: node.id, hidden: hidden };
    });
    
    nodes.update(updates);
}

function switchTab(tabId) {
    // Update tab styles
    document.querySelectorAll('.sidebar-tabs .tab').forEach(t => {
        t.classList.remove('active');
        if (t.innerText.toLowerCase().includes(tabId)) t.classList.add('active');
    });
    
    // Switch content
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    const content = document.getElementById(tabId + '-content');
    if (content) {
        content.style.display = 'block';
        if (tabId === 'legend') renderLegend();
    }
}

function renderLegend() {
    const content = document.getElementById('legend-content');
    content.innerHTML = `
        <div style="padding: 10px;">
            <!-- 1. API FLOW -->
            <div style="font-weight: 700; color: #666; margin-bottom: 10px; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">🌐 API Flow</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 16px; height: 16px; background: #5c6bc0; transform: rotate(45deg); margin: 0 11px 0 1px;"></div>
                <span><b>API Endpoint / Common API</b></span>
            </div>

            <!-- 2. UI FLOW -->
            <div style="font-weight: 700; color: #666; margin: 15px 0 10px 0; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">💻 UI Flow</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #9c27b0; border-radius: 50%; margin-right: 10px;"></div>
                <span><b>Page Object (Ellipse)</b></span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 0; height: 0; border-left: 9px solid transparent; border-right: 9px solid transparent; border-bottom: 18px solid #009688; margin-right: 10px;"></div>
                <span><b>UI Action (Triangle)</b></span>
            </div>

            <!-- 3. DB FLOW -->
            <div style="font-weight: 700; color: #666; margin: 15px 0 10px 0; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">🗄️ DB Flow</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #795548; border-radius: 9px / 4px; border-bottom: 3px solid #5d4037; margin-right: 10px;"></div>
                <span><b>Database / SQL</b></span>
            </div>

            <!-- 4. TEST FLOW -->
            <div style="font-weight: 700; color: #666; margin: 15px 0 10px 0; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">🧪 Test Flow</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #03a9f4; margin-right: 10px;"></div>
                <span><b>Feature / Test Case (Square)</b></span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #03a9f4; clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%); margin-right: 10px;"></div>
                <span><b>Workflow (Star)</b></span>
            </div>

            <!-- 5. DATA FLOW -->
            <div style="font-weight: 700; color: #666; margin: 15px 0 10px 0; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">📊 Data Flow</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #00bcd4; border: 1px solid #0097a7; margin-right: 10px;"></div>
                <span><b>Data File (Box)</b></span>
            </div>

            <div style="font-weight: 700; color: #666; margin: 20px 0 15px 0; font-size: 11px; text-transform: uppercase;">Status Colors</div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #4caf50; border-radius: 2px; margin-right: 10px;"></div>
                <span>Passed</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #f44336; border-radius: 2px; margin-right: 10px;"></div>
                <span>Failed</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #ff9800; border-radius: 2px; margin-right: 10px;"></div>
                <span>Impacted</span>
            </div>
        </div>
    `;
}

// --- EVENTS ---
function initEvents() {
    network.on("click", function(params) {
        if (params.nodes.length === 0) resetFocus();
        else showDetails(params.nodes[0]);
    });

    network.on("doubleClick", function(params) {
        if (params.nodes.length > 0) focusOnNode(params.nodes[0]);
    });
}

function jumpToNode(nodeId) {
    network.selectNodes([nodeId]);
    network.focus(nodeId, {
        scale: 1.2,
        animation: {
            duration: 1000,
            easingFunction: 'easeInOutQuad'
        }
    });
    showDetails(nodeId);
}

// Initialization
window.onload = function() {
    renderDashboard();
    switchTab('hotspots'); // Default tab
    initEvents();
    
    // Ctrl+K to search
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            document.getElementById('node-search').focus();
        }
    });
};

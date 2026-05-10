// KARATE COMMAND CENTER - CORE LOGIC

var isFocused = false;
var currentTab = 'HOTSPOTS';
var currentHotspotNodeId = null;
var hotspotSortKey = 'impact';
var hotspotSortDir = 'desc';
var hotspotTypeFilter = 'ALL';

function getStatusTone(status) {
    if (status === 'PASSED') {
        return { klass: 'badge-passed', bg: '#e8f5e9', color: '#2e7d32', label: 'PASSED' };
    }
    if (status === 'FAILED') {
        return { klass: 'badge-failed', bg: '#ffebee', color: '#c62828', label: 'FAILED' };
    }
    if (status === 'PARTIAL_FAIL') {
        return { klass: 'badge-partial', bg: '#fff3e0', color: '#e65100', label: 'PARTIAL_FAIL' };
    }
    return { klass: 'badge-neutral', bg: '#eceff1', color: '#455a64', label: status || 'NEUTRAL' };
}

function classifyHotspot(hs) {
    const node = nodeMetadata[hs.node_id];
    const nodeType = hs.type || node?.type || '';
    const lowered = String(nodeType).toUpperCase();
    if (lowered === 'TEST_CASE' || lowered === 'SCENARIO' || lowered === 'ACTION') {
        return { label: 'Failing Component', color: '#d32f2f', note: 'Directly involved in failed execution.' };
    }
    if (lowered === 'DATA' || lowered === 'LOCATOR' || lowered === 'FILE' || lowered === 'FOLDER') {
        return { label: 'Supporting Asset', color: '#455a64', note: 'Used by failed tests, not a direct failure verdict.' };
    }
    return { label: 'Shared Dependency', color: '#1565c0', note: 'Shared path in failing tests. Investigate with context.' };
}

// --- SHARED HELPERS ---

function escapeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getDisplayData(nodeId) {
    return nodeMetadata[nodeId]?.additional_data?.display_data || {};
}

function normalizeCaseId(value) {
    return String(value || '').trim().replace(/^@+/, '');
}

function formatCaseId(value) {
    const clean = normalizeCaseId(value);
    return clean ? `@${clean}` : '';
}

function getNodeTags(node, data) {
    if (Array.isArray(data?.jira_tags) && data.jira_tags.length) {
        return data.jira_tags;
    }
    const details = data?.details || {};
    if (Array.isArray(details.jira_tags) && details.jira_tags.length) {
        return details.jira_tags;
    }
    if (Array.isArray(node?.additional_data?.jira_tags)) {
        return node.additional_data.jira_tags;
    }
    return [];
}

function getPrimaryTestCaseId(nodeId, dataOverride) {
    const node = nodeMetadata[nodeId];
    const data = dataOverride || getDisplayData(nodeId);
    const directId = normalizeCaseId(data.test_case_id || node?.additional_data?.test_case_id);
    if (directId) return directId;

    const tags = getNodeTags(node, data).map(normalizeCaseId).filter(Boolean);
    return tags[0] || '';
}

function isCaseLikeNode(node, data) {
    const type = String(data?.type_label || node?.type || '').toUpperCase();
    return type === 'TEST_CASE' || type === 'SCENARIO' || type === 'ACTION';
}

function stripCaseIdPrefix(name, testCaseId) {
    const cleanId = normalizeCaseId(testCaseId);
    if (!cleanId) return String(name || '');
    return String(name || '')
        .replace(new RegExp(`^@?${cleanId}\\s*[-:|]?\\s*`, 'i'), '')
        .trim();
}

function getNodeDisplayName(nodeId, fallbackName) {
    const node = nodeMetadata[nodeId];
    const data = getDisplayData(nodeId);
    const baseName = data.display_name || data.name || fallbackName || node?.name || nodeId;
    const testCaseId = getPrimaryTestCaseId(nodeId, data);

    if (!testCaseId || !isCaseLikeNode(node, data)) {
        return baseName;
    }

    const cleanName = stripCaseIdPrefix(baseName, testCaseId) || node?.name || fallbackName || nodeId;
    return `${formatCaseId(testCaseId)} - ${cleanName}`;
}

function buildCaseTitleHtml(nodeId, fallbackName) {
    const testCaseId = getPrimaryTestCaseId(nodeId);
    const displayName = getNodeDisplayName(nodeId, fallbackName);
    const cleanName = stripCaseIdPrefix(displayName, testCaseId);

    if (!testCaseId) {
        return `<span class="test-case-name">${escapeHtml(displayName)}</span>`;
    }

    return `
        <span class="test-case-id-badge">${escapeHtml(formatCaseId(testCaseId))}</span>
        <span class="test-case-name">${escapeHtml(cleanName)}</span>
    `;
}

function getHotspotDisplayName(hotspot) {
    return getNodeDisplayName(hotspot?.node_id, hotspot?.name || hotspot?.node_id || '');
}

function getTerminalStatus(testCaseNodeId) {
    const node = nodeMetadata[testCaseNodeId];
    if (!node) return 'UNKNOWN';
    return node.execution_status || node.additional_data?.display_data?.status || 'UNKNOWN';
}

function getFailureReason(testCaseNodeId) {
    const node = nodeMetadata[testCaseNodeId];
    if (!node) return 'Unknown error';
    const display = node.additional_data?.display_data || {};
    const details = node.execution_details || {};
    return details.error || display.details?.last_error || node.additional_data?.last_error || 'Unknown error';
}

function getFailedStep(testCaseNodeId) {
    const node = nodeMetadata[testCaseNodeId];
    return node?.execution_details?.failed_step || 'N/A';
}

function focusGraphNode(nodeId) {
    if (!nodeId || !nodeMetadata[nodeId]) return;
    network.selectNodes([nodeId]);
    network.focus(nodeId, { scale: 1.0, animation: { duration: 700 } });
}

function selectHotspot(nodeId) {
    currentHotspotNodeId = nodeId;
    renderDashboard();
    focusGraphNode(nodeId);
}

function setHotspotFilter(type) {
    hotspotTypeFilter = type || 'ALL';
    renderDashboard();
}

function setHotspotSort(key) {
    if (hotspotSortKey === key) {
        hotspotSortDir = hotspotSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        hotspotSortKey = key;
        hotspotSortDir = 'desc';
    }
    renderDashboard();
}

function getHotspots() {
    return Array.isArray(hotspotData) ? hotspotData : [];
}

function getHotspotTestCaseId(testCase) {
    return testCase?.node_id || testCase?.id || '';
}

function getTotalProjectFailures() {
    let total = 0;
    for (const id in nodeMetadata) {
        const data = nodeMetadata[id].additional_data?.display_data;
        if (!data) continue;

        const isTerminal = data.type_label === 'TEST_CASE' || data.type_label === 'SCENARIO';
        if (isTerminal && data.status === 'FAILED') total++;
    }
    return total;
}

function getUniqueFailedTestCases(hotspots) {
    const uniqueCases = new Map();
    hotspots.forEach(hs => {
        (hs.affected_failed_test_cases || []).forEach(tc => {
            const id = getHotspotTestCaseId(tc);
            if (id) uniqueCases.set(id, tc);
        });
    });
    return uniqueCases;
}

function getHotspotType(hotspot) {
    return String(hotspot?.type || 'UNKNOWN').toUpperCase();
}

function getHotspotContribution(hotspot, totalProjectFailures) {
    if (!totalProjectFailures) return 0;
    return Math.round(((hotspot.failed_test_cases || 0) / totalProjectFailures) * 100);
}

function getHotspotTypeOptions(hotspots) {
    return ['ALL', ...new Set(hotspots.map(getHotspotType))];
}

function getVisibleHotspots(hotspots) {
    if (hotspotTypeFilter === 'ALL') return hotspots;
    return hotspots.filter(hs => getHotspotType(hs) === hotspotTypeFilter);
}

function ensureSelectedHotspot(hotspots, visibleHotspots) {
    if (!hotspots.length) {
        currentHotspotNodeId = null;
        return null;
    }

    const existsInAll = hotspots.some(hs => hs.node_id === currentHotspotNodeId);
    if (!currentHotspotNodeId || !existsInAll) {
        currentHotspotNodeId = hotspots[0].node_id;
    }

    const existsInVisible = visibleHotspots.some(hs => hs.node_id === currentHotspotNodeId);
    if (visibleHotspots.length && !existsInVisible) {
        currentHotspotNodeId = visibleHotspots[0].node_id;
    }

    return hotspots.find(hs => hs.node_id === currentHotspotNodeId) || hotspots[0];
}

function buildHotspotRows(hotspots, totalProjectFailures) {
    return hotspots.map(hs => {
        const failedCount = hs.failed_test_cases || 0;
        const totalCount = hs.total_test_cases || 0;
        const errorSet = new Set(
            (hs.affected_failed_test_cases || []).map(tc => getFailureReason(getHotspotTestCaseId(tc)))
        );

        return {
            hs,
            failedCount,
            totalCount,
            contribution: getHotspotContribution(hs, totalProjectFailures),
            profile: classifyHotspot(hs),
            isSelected: hs.node_id === currentHotspotNodeId,
            errorCount: errorSet.size
        };
    }).sort(compareHotspotRows);
}

function compareHotspotRows(a, b) {
    const dir = hotspotSortDir === 'asc' ? 1 : -1;
    if (hotspotSortKey === 'name') return dir * getHotspotDisplayName(a.hs).localeCompare(getHotspotDisplayName(b.hs));
    if (hotspotSortKey === 'type') return dir * getHotspotType(a.hs).localeCompare(getHotspotType(b.hs));
    if (hotspotSortKey === 'failed') return dir * (a.failedCount - b.failedCount);
    if (hotspotSortKey === 'rate') return dir * ((a.hs.failure_percentage || 0) - (b.hs.failure_percentage || 0));
    if (hotspotSortKey === 'errors') return dir * (a.errorCount - b.errorCount);
    return dir * (a.contribution - b.contribution);
}

function getSelectedFailedCases(selectedHotspot) {
    return (selectedHotspot?.affected_failed_test_cases || []).map(tc => {
        const id = getHotspotTestCaseId(tc);
        const testCaseId = getPrimaryTestCaseId(id) || normalizeCaseId((tc.jira_tags || [])[0]);
        const displayName = getNodeDisplayName(id, tc.name || id);
        return {
            id: id,
            name: tc.name || id,
            displayName,
            testCaseId,
            testCaseLabel: testCaseId ? formatCaseId(testCaseId) : '',
            line: tc.line_number || '',
            file: tc.file_path || '',
            depth: tc.depth || 0,
            status: getTerminalStatus(id),
            reason: getFailureReason(id),
            failedStep: getFailedStep(id),
            path: Array.isArray(tc.dependency_path) ? tc.dependency_path : []
        };
    });
}

function getErrorGroups(failedCases) {
    const groupedErrors = {};
    failedCases.forEach(tc => {
        const key = tc.reason || 'Unknown error';
        groupedErrors[key] = (groupedErrors[key] || 0) + 1;
    });
    return Object.entries(groupedErrors).sort((a, b) => b[1] - a[1]);
}

// --- SEARCH ---
function normalizeSearchTerm(value) {
    return normalizeCaseId(value).toLowerCase();
}

function getNodeSearchText(nodeId, node, data) {
    const details = data.details || {};
    const tags = getNodeTags(node, data);
    const testCaseId = getPrimaryTestCaseId(nodeId, data);

    return [
        nodeId,
        node?.name,
        data.name,
        data.display_name,
        getNodeDisplayName(nodeId),
        data.type_label,
        data.file_path,
        details.file_path,
        details.workflow_path,
        details.scenario_tag,
        testCaseId,
        formatCaseId(testCaseId),
        ...tags,
        ...tags.map(normalizeCaseId)
    ].filter(Boolean).join(' ').toLowerCase();
}

function renderSearchResultItem(match) {
    return `
        <div class="search-result-item" onclick="focusOnNode('${match.id}')">
            <div class="search-result-content">
                <div class="search-result-title">
                    ${buildCaseTitleHtml(match.id, match.name)}
                </div>
                <div class="search-result-meta">${escapeHtml(match.filePath || match.id)}</div>
            </div>
            <span class="search-result-type">${escapeHtml(match.typeLabel)}</span>
        </div>
    `;
}

function handleSearch(query) {
    const resultsDiv = document.getElementById('search-results');
    if (!query || query.length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }

    const matches = [];
    const searchTerms = query.split(/\s+/).map(normalizeSearchTerm).filter(Boolean);
    
    for (const id in nodeMetadata) {
        const node = nodeMetadata[id];
        const data = node.additional_data?.display_data;
        if (!data) continue;

        const text = getNodeSearchText(id, node, data);
        if (searchTerms.every(t => text.includes(t))) {
            matches.push({
                id,
                name: data.name,
                displayName: getNodeDisplayName(id),
                typeLabel: data.type_label || node.type || 'UNKNOWN',
                filePath: data.file_path || data.details?.workflow_path || ''
            });
        }
        if (matches.length >= 15) break;
    }

    if (matches.length > 0) {
        resultsDiv.innerHTML = matches.map(renderSearchResultItem).join('');
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
        if (hs) hs.affected_failed_test_cases.forEach(tc => affectedIds.add(tc.node_id || tc.id));
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
    const timelineContent = document.getElementById('timeline-content');
    if (timelineContent) {
        timelineContent.innerHTML = `
            <div style="padding: 20px; color: #666; font-size: 13px;">
                <i class="fas fa-info-circle"></i> Select a node to see its detailed execution history.
            </div>
        `;
    }
}

const NODE_DETAIL_FIELDS = {
    'http_method': 'HTTP Method',
    'endpoint': 'Endpoint',
    'physical_url': 'Physical URL',
    'resolved_from': 'Resolved From',
    'variable': 'Variable Name',
    'database': 'Database',
    'table': 'Table',
    'operation': 'DB Operation',
    'host': 'Host',
    'scenario_tag': 'Scenario Tag',
    'workflow_path': 'Workflow File',
    'key': 'Key',
    'value': 'Value'
};

function buildNodeDetailsModel(nodeId) {
    const node = nodeMetadata[nodeId];
    if (!node || !node.additional_data?.display_data) return null;
    return { nodeId, node, data: node.additional_data.display_data };
}

function renderNodeDetails(model) {
    const sections = [
        renderNodeIdentitySection(model),
        renderNodeStatusSection(model.data),
        renderNodeFailureContextSection(model.data),
        renderNodeSourceSection(model.data),
        renderNodeExecutionHistory(model.data),
        renderNodeTechnicalDetails(model.data),
        renderEnvironmentVariants(model.node),
        renderJiraLinks(model.data),
        renderExpertNotes(model.data),
        renderAiSuggestions(model.data),
        renderRelatedFailedComponents(model)
    ];

    return `<div style="padding: 12px;">${sections.filter(Boolean).join('')}</div>`;
}

function renderNodeIdentitySection(model) {
    const testCaseId = getPrimaryTestCaseId(model.nodeId, model.data);
    return `
        <div class="detail-section">
            <div class="detail-label">${testCaseId ? 'Test Case' : 'Component Name'}</div>
            <div class="detail-value detail-title-row" style="font-size: 16px; font-weight: 700;">
                ${buildCaseTitleHtml(model.nodeId, model.data.name)}
            </div>
            ${testCaseId ? `<div class="detail-subvalue">Name: ${escapeHtml(stripCaseIdPrefix(getNodeDisplayName(model.nodeId), testCaseId))}</div>` : ''}
            <div style="font-size: 10px; color: #888; margin-top: 4px;">ID: ${escapeHtml(model.nodeId)}</div>
        </div>
    `;
}

function renderNodeStatusSection(data) {
    const tone = getStatusTone(data.status);
    return `
        <div class="detail-section">
            <div class="detail-label">Type & Status</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                ${(data.badges || []).map(b => `<span class="impact-badge badge-type">${escapeHtml(b)}</span>`).join('')}
                <span class="impact-badge ${tone.klass}" style="background: ${tone.bg}; color: ${tone.color};">
                    ${escapeHtml(tone.label)}
                </span>
            </div>
        </div>
    `;
}

function renderNodeFailureContextSection(data) {
    const details = data.details || {};
    const fingerprint = data.failure_fingerprint || details.failure_fingerprint;
    const category = data.failure_category || details.failure_category;
    const failedStep = details.last_run?.failed_step || details.last_run?.failedStep || details.last_failed_step;
    const lastRun = data.last_run || details.last_run || {};
    const runContext = lastRun.run_context || details.run_context || {};
    const artifacts = data.last_artifacts || details.last_artifacts || [];

    if (!fingerprint && !category && !runContext.run_id && !artifacts.length) return '';

    return `
        <div class="detail-section failure-context-section">
            <div class="detail-label">Failure Context</div>
            <div class="failure-context-grid">
                ${category ? `<div><span>Category</span><b>${escapeHtml(category)}</b></div>` : ''}
                ${runContext.run_id ? `<div><span>Run ID</span><b>${escapeHtml(runContext.run_id)}</b></div>` : ''}
                ${runContext.report_file ? `<div><span>Report</span><b>${escapeHtml(runContext.report_file)}</b></div>` : ''}
                ${artifacts.length ? `<div><span>Artifacts</span><b>${artifacts.length}</b></div>` : ''}
            </div>
            ${failedStep ? `<div class="failure-context-line"><b>Failed Step:</b> ${escapeHtml(failedStep)}</div>` : ''}
            ${fingerprint ? `<div class="failure-fingerprint">${escapeHtml(fingerprint)}</div>` : ''}
        </div>
    `;
}

function renderNodeSourceSection(data) {
    if (!data.file_path) return '';
    const location = `${data.file_path}${data.line_number ? `:${data.line_number}` : ''}`;
    return `
        <div class="detail-section">
            <div class="detail-label">Source Location</div>
            <div class="detail-value" style="font-family: monospace; font-size: 11px;">
                ${escapeHtml(location)}
            </div>
        </div>
    `;
}

function renderNodeExecutionHistory(data) {
    const history = Array.isArray(data.execution_history) ? data.execution_history.slice(-10) : [];
    const runs = Array.isArray(data.execution_runs) ? data.execution_runs.slice(-5).reverse() : [];
    if (!history.length && !runs.length) return '';

    const runStatuses = runs.map(run => run.status).filter(Boolean);
    const trendStatuses = runStatuses.length ? runStatuses : history;
    const passCount = trendStatuses.filter(status => status === 'PASSED').length;
    const failCount = trendStatuses.filter(status => status === 'FAILED').length;
    const total = passCount + failCount;
    const failRate = total ? Math.round((failCount / total) * 100) : 0;

    return `
        <div class="detail-section">
            <div class="detail-label">Execution History (Last 10)</div>
            <div class="execution-trend-row">
                <div><span>Runs</span><b>${total}</b></div>
                <div><span>Pass</span><b>${passCount}</b></div>
                <div><span>Fail</span><b>${failCount}</b></div>
                <div><span>Fail Rate</span><b>${failRate}%</b></div>
            </div>
            <div class="history-timeline">
                ${history.map(status => `
                    <div class="dot ${status === 'PASSED' ? 'pass' : 'fail'}" title="${escapeHtml(status)}"></div>
                `).join('')}
            </div>
            ${runs.length ? `
                <div class="run-history-list">
                    ${runs.map(renderExecutionRunItem).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function renderExecutionRunItem(run) {
    const context = run.run_context || {};
    const statusClass = run.status === 'PASSED' ? 'pass' : 'fail';
    return `
        <div class="run-history-item ${statusClass}">
            <div>
                <b>${escapeHtml(run.status || 'UNKNOWN')}</b>
                <span>${escapeHtml(context.report_file || context.run_id || 'manual run')}</span>
            </div>
            ${run.failure_category ? `<em>${escapeHtml(run.failure_category)}</em>` : ''}
        </div>
    `;
}

function renderNodeTechnicalDetails(data) {
    const details = data.details || {};
    const rows = Object.entries(NODE_DETAIL_FIELDS)
        .filter(([key]) => details[key])
        .map(([key, label]) => `
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 12px;">
                <span style="color: #666;">${label}:</span>
                <span style="font-weight: 600; color: #333; text-align: right; max-width: 200px; word-break: break-all;">${escapeHtml(details[key])}</span>
            </div>
        `).join('');

    if (!rows) return '';
    return `
        <div class="detail-section" style="background: rgba(0,0,0,0.02); margin: 10px -15px; padding: 15px;">
            <div class="detail-label">Technical Details</div>
            <div style="margin-top: 10px;">${rows}</div>
        </div>
    `;
}

function renderEnvironmentVariants(node) {
    const variants = node.environment_variants || {};
    if (!Object.keys(variants).length) return '';

    return `
        <div class="detail-section" style="border: 1px solid #e3f2fd; background: #f9fcff;">
            <div class="detail-label" style="color: #1976d2;"><i class="fas fa-globe"></i> Environment Variants</div>
            <div style="margin-top: 10px;">
                ${Object.entries(variants).map(([env, value]) => `
                    <div style="margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #eee;">
                        <div style="font-size: 9px; font-weight: 700; color: #1976d2; text-transform: uppercase;">${escapeHtml(env)}</div>
                        <div style="font-size: 11px; color: #555; word-break: break-all; font-family: monospace;">${escapeHtml(value)}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function renderJiraLinks(data) {
    const tags = Array.isArray(data.jira_tags) ? data.jira_tags : [];
    if (!tags.length) return '';

    return `
        <div class="detail-section">
            <div class="detail-label">Jira Traceability</div>
            <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px;">
                ${tags.map(tag => {
                    const cleanTag = String(tag).replace('@', '');
                    const url = jiraBaseUrl ? `${jiraBaseUrl}${cleanTag}` : '#';
                    return `<a href="${escapeHtml(url)}" target="_blank" class="badge-utility" style="text-decoration: none; font-size: 10px;">${escapeHtml(tag)}</a>`;
                }).join('')}
            </div>
        </div>
    `;
}

function renderExpertNotes(data) {
    const notes = Array.isArray(data.expert_notes) ? data.expert_notes : [];
    if (!notes.length) return '';

    return `
        <div class="detail-section">
            <div class="detail-label" style="color: #1976D2;"><i class="fas fa-robot"></i> Expert Analysis</div>
            ${notes.map(note => {
                const title = note.timestamp ? `Note from AI Assistant (${note.timestamp}):` : 'Architectural Note:';
                return `
                    <div style="background: #E3F2FD; padding: 10px; border-radius: 8px; border: 1px solid #BBDEFB; margin-top: 10px; font-size: 11px;">
                        <div style="color: #0D47A1; font-weight: 700; margin-bottom: 3px;">${escapeHtml(title)}</div>
                        <div>${escapeHtml(note.note)}</div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderAiSuggestions(data) {
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    if (!suggestions.length) return '';

    return `
        <div class="detail-section">
            <div class="detail-label">AI Fix Intelligence</div>
            ${suggestions.map(suggestion => `
                <div style="background: #fffde7; padding: 10px; border-radius: 8px; border: 1px solid #fff59d; margin-top: 10px;">
                    <div style="font-weight: 700; color: #827717; font-size: 12px;">${escapeHtml(suggestion.description)}</div>
                    ${suggestion.solution ? `<div style="font-family: monospace; font-size: 11px; margin-top: 5px; background: #fff; padding: 5px; border: 1px solid #eee;">${escapeHtml(suggestion.solution)}</div>` : ''}
                </div>
            `).join('')}
        </div>
    `;
}

function getRelatedFailedChildren(nodeId) {
    const failedChildren = [];
    edges.get().forEach(edge => {
        if (edge.from !== nodeId) return;
        const child = nodeMetadata[edge.to];
        if (child && (child.execution_status === 'FAILED' || child.execution_status === 'PARTIAL_FAIL')) {
            failedChildren.push({ id: edge.to, name: child.name });
        }
    });
    return failedChildren;
}

function renderRelatedFailedComponents(model) {
    if (model.data.status !== 'FAILED' && model.data.status !== 'PARTIAL_FAIL') return '';

    const failedChildren = getRelatedFailedChildren(model.nodeId);
    if (!failedChildren.length) return '';

    return `
        <div class="detail-section">
            <div class="detail-label" style="color: #d32f2f;"><i class="fas fa-search-location"></i> Related Failed Components</div>
            <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                ${failedChildren.map(child => `
                    <div class="error-box" style="border-left: 4px solid #f44336; cursor: pointer; transition: 0.2s;"
                         onclick="jumpToNode('${child.id}')" onmouseover="this.style.background='#ffebee'" onmouseout="this.style.background='#fff5f5'">
                        <div style="font-weight: 700; font-size: 11px; color: #b71c1c;">${escapeHtml(child.name)}</div>
                        <div style="font-size: 9px; color: #1976d2; margin-top: 4px; font-weight: 800;">CLICK TO FOCUS ON MAP</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function showDetails(nodeId) {
    const model = buildNodeDetailsModel(nodeId);
    const timelineContent = document.getElementById('timeline-content');
    if (!model || !timelineContent) return;

    timelineContent.innerHTML = renderNodeDetails(model);
    switchTab('timeline');
}

// --- DASHBOARD RENDERING ---
function renderDashboard() {
    const hotspotList = document.getElementById('hotspot-list');
    if (!hotspotList) return;

    const model = buildHotspotDashboardModel();
    hotspotList.innerHTML = model.hotspots.length
        ? renderHotspotDashboard(model)
        : renderEmptyHotspots(model.totalProjectFailures);

    renderStatusSummary();
}

function buildHotspotDashboardModel() {
    const totalProjectFailures = getTotalProjectFailures();
    const hotspots = getHotspots();
    const visibleHotspots = getVisibleHotspots(hotspots);
    const selectedHotspot = ensureSelectedHotspot(hotspots, visibleHotspots);
    const selectedFailedCases = getSelectedFailedCases(selectedHotspot);
    const errorGroups = getErrorGroups(selectedFailedCases);

    return {
        totalProjectFailures,
        hotspots,
        selectedHotspot,
        selectedProfile: classifyHotspot(selectedHotspot || {}),
        selectedFailedCases,
        errorGroups,
        topError: errorGroups.length ? errorGroups[0][0] : 'N/A',
        rows: buildHotspotRows(visibleHotspots, totalProjectFailures),
        typeOptions: getHotspotTypeOptions(hotspots),
        uniqueFailedCaseCount: getUniqueFailedTestCases(hotspots).size,
        insights: buildReportInsights(hotspots)
    };
}

function buildReportInsights(hotspots) {
    const values = Object.values(nodeMetadata || {});
    const jsFileCount = values.filter(n => n && n.type === 'JAVASCRIPT').length;
    const jsFunctionCount = values.filter(n => n && n.type === 'JS_FUNCTION').length;

    const jsRelatedCaseIds = new Set();
    const typeImpactMap = {};
    const reasonCountMap = {};

    hotspots.forEach(hs => {
        const type = getHotspotType(hs);
        typeImpactMap[type] = (typeImpactMap[type] || 0) + (hs.failed_test_cases || 0);
        const failedCases = hs.affected_failed_test_cases || [];
        failedCases.forEach(testCase => {
            const caseId = testCase.node_id || testCase.id;
            if (caseId && (type === 'JAVASCRIPT' || type === 'JS_FUNCTION')) {
                jsRelatedCaseIds.add(caseId);
            }
            const reason = (testCase.reason || '').trim() || 'Unknown error';
            reasonCountMap[reason] = (reasonCountMap[reason] || 0) + 1;
        });
    });

    const topTypes = Object.entries(typeImpactMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([type, failedCount]) => ({ type, failedCount }));

    const topReasons = Object.entries(reasonCountMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([reason, count]) => ({ reason, count }));

    return {
        jsFileCount,
        jsFunctionCount,
        jsRelatedFailedCases: jsRelatedCaseIds.size,
        topTypes,
        topReasons
    };
}

function renderEmptyHotspots(totalProjectFailures) {
    return `
        <div class="dashboard-summary-grid">
            ${renderSummaryCard('Failed Test Cases', totalProjectFailures)}
            ${renderSummaryCard('Hotspots', 0)}
        </div>
        <div class="empty-hotspot">No failure hotspot data available in current report.</div>
    `;
}

function renderHotspotDashboard(model) {
    return `
        <div class="dashboard-summary-grid">
            ${renderSummaryCard('Failed Test Cases', model.totalProjectFailures)}
            ${renderSummaryCard('Unique Failing Cases', model.uniqueFailedCaseCount)}
            ${renderSummaryCard('Hotspots', model.hotspots.length)}
            ${renderSummaryCard('JS Files', model.insights.jsFileCount)}
            ${renderSummaryCard('JS Functions', model.insights.jsFunctionCount)}
            ${renderSummaryCard('JS-Related Failed Cases', model.insights.jsRelatedFailedCases)}
        </div>
        ${renderReportInsights(model.insights)}
        <div class="hotspot-section-title">Hotspot Dashboard Table</div>
        ${renderHotspotFilters(model.typeOptions)}
        ${renderHotspotTable(model.rows)}
        ${renderHotspotAnalysis(model)}
    `;
}

function renderReportInsights(insights) {
    return `
        <div class="report-insights-panel">
            <div class="hotspot-section-title">Report Insights</div>
            <div class="report-insights-grid">
                <div class="report-insights-card">
                    <div class="hotspot-section-subtitle">Top Hotspot Types (by failed cases)</div>
                    ${renderTopTypes(insights.topTypes)}
                </div>
                <div class="report-insights-card">
                    <div class="hotspot-section-subtitle">Top Error Reasons (global)</div>
                    ${renderTopReasons(insights.topReasons)}
                </div>
            </div>
        </div>
    `;
}

function renderTopTypes(rows) {
    if (!rows.length) return '<div class="report-insights-empty">No type impact data.</div>';
    return `
        <div class="report-insights-list">
            ${rows.map((row, idx) => `
                <div class="report-insights-row">
                    <span>#${idx + 1} ${escapeHtml(row.type)}</span>
                    <b>${row.failedCount}</b>
                </div>
            `).join('')}
        </div>
    `;
}

function renderTopReasons(rows) {
    if (!rows.length) return '<div class="report-insights-empty">No error reasons in report.</div>';
    return `
        <div class="report-insights-list">
            ${rows.map((row, idx) => `
                <div class="report-insights-row">
                    <span>#${idx + 1} ${escapeHtml(row.reason)}</span>
                    <b>${row.count}</b>
                </div>
            `).join('')}
        </div>
    `;
}

function renderSummaryCard(label, value) {
    return `
        <div class="dashboard-summary-card">
            <div class="summary-label">${label}</div>
            <div class="summary-value">${value}</div>
        </div>
    `;
}

function renderHotspotFilters(typeOptions) {
    return `
        <div class="hotspot-toolbar">
            <div class="hotspot-filter-group">
                ${typeOptions.map(type => `
                    <button class="hotspot-filter-btn ${type === hotspotTypeFilter ? 'active' : ''}" onclick="setHotspotFilter('${type}')">${type}</button>
                `).join('')}
            </div>
        </div>
    `;
}

function renderHotspotTable(rows) {
    return `
        <div class="hotspot-table-wrap">
            <table class="hotspot-table">
                <thead>
                    <tr>
                        <th onclick="setHotspotSort('name')">Hotspot</th>
                        <th onclick="setHotspotSort('type')">Type</th>
                        <th onclick="setHotspotSort('failed')">Failed/Total</th>
                        <th onclick="setHotspotSort('impact')">Impact %</th>
                        <th onclick="setHotspotSort('rate')">Fail Rate %</th>
                        <th onclick="setHotspotSort('errors')">Error Groups</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows.map(renderHotspotTableRow).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderHotspotTableRow(row) {
    const hotspotName = getHotspotDisplayName(row.hs);
    return `
        <tr class="${row.isSelected ? 'selected' : ''}" onclick="selectHotspot('${row.hs.node_id}')">
            <td>
                <div class="hotspot-name-cell">
                    <span class="hotspot-color-dot" style="background:${row.profile.color};"></span>
                    <span>${escapeHtml(hotspotName)}</span>
                </div>
            </td>
            <td>${escapeHtml(getHotspotType(row.hs))}</td>
            <td>${row.failedCount}/${row.totalCount}</td>
            <td>${row.contribution}%</td>
            <td>${row.hs.failure_percentage || 0}%</td>
            <td>${row.errorCount}</td>
        </tr>
    `;
}

function renderHotspotAnalysis(model) {
    if (!model.selectedHotspot) return '';
    const selectedHotspotName = getHotspotDisplayName(model.selectedHotspot);

    return `
        <div class="hotspot-analysis-panel">
            <div class="hotspot-section-title">Selected Hotspot Analysis</div>
            <div class="hotspot-analysis-header">
                <div class="hotspot-analysis-name">${escapeHtml(selectedHotspotName)}</div>
                <span class="impact-badge" style="background: ${model.selectedProfile.color}; font-size: 10px;">
                    ${model.selectedProfile.label}
                </span>
            </div>
            <div class="hotspot-analysis-kpis">
                <div><b>Impact:</b> ${model.selectedHotspot.failed_test_cases || 0}/${model.selectedHotspot.total_test_cases || 0} failed</div>
                <div><b>Failure Rate:</b> ${model.selectedHotspot.failure_percentage || 0}%</div>
                <div><b>Main Error:</b> ${escapeHtml(model.topError)}</div>
            </div>
            <div class="hotspot-section-subtitle">Error Groups</div>
            <div class="hotspot-error-groups">
                ${renderErrorGroups(model.errorGroups)}
            </div>

            <div class="hotspot-section-subtitle">Related Failed Test Cases</div>
            <div class="hotspot-case-list">
                ${renderFailedCaseList(model.selectedFailedCases)}
            </div>
        </div>
    `;
}

function renderErrorGroups(errorGroups) {
    if (!errorGroups.length) return '<div style="font-size:11px;color:#777;">No error groups.</div>';
    return errorGroups.map(([reason, count]) => `
        <div class="hotspot-error-group">
            <div class="hotspot-error-count">${count}x</div>
            <div class="hotspot-error-text">${escapeHtml(reason)}</div>
        </div>
    `).join('');
}

function renderFailedCaseList(failedCases) {
    if (!failedCases.length) {
        return '<div style="font-size:11px;color:#777;">No related failed test cases.</div>';
    }
    return failedCases.map(renderFailedCaseItem).join('');
}

function renderFailedCaseItem(testCase) {
    return `
        <div class="hotspot-case-item" onclick="focusOnNode('${testCase.id}')">
            <div class="hotspot-case-title test-case-title-row">
                ${buildCaseTitleHtml(testCase.id, testCase.displayName || testCase.name)}
            </div>
            <div class="hotspot-case-meta">
                ${testCase.testCaseLabel ? `<span>Test Case ID: <b>${escapeHtml(testCase.testCaseLabel)}</b></span>` : ''}
                <span>Status: <b>${escapeHtml(testCase.status)}</b></span>
                <span>Depth: <b>${testCase.depth}</b></span>
                <span>Line: <b>${testCase.line || 'N/A'}</b></span>
            </div>
            <div class="hotspot-case-error">${escapeHtml(testCase.reason)}</div>
            <div class="hotspot-case-step">Failed Step: ${escapeHtml(testCase.failedStep)}</div>
            <div class="hotspot-case-path">Path: ${escapeHtml(testCase.path.join(' -> '))}</div>
        </div>
    `;
}

function renderStatusSummary() {
    let total = 0, passed = 0, failed = 0, partial = 0;
    for (const id in nodeMetadata) {
        const node = nodeMetadata[id];
        if (node.type === 'TEST_CASE') {
            total++;
            if (node.execution_status === 'PASSED') passed++;
            else if (node.execution_status === 'FAILED') failed++;
        }
        if (node.execution_status === 'PARTIAL_FAIL') partial++;
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
                    <div onclick="filterNodes('partial')" style="cursor: pointer;">
                        <div style="font-size: 10px; color: #e65100; font-weight: 800;">PARTIAL</div>
                        <div style="font-size: 18px; font-weight: 800; color: #e65100;">${partial}</div>
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
        } else if (status === 'partial') {
            hidden = (metadata.execution_status !== 'PARTIAL_FAIL');
        }
        
        return { id: node.id, hidden: hidden };
    });
    
    nodes.update(updates);
}

function toggleLayer(layer, isVisible) {
    const allNodes = nodes.get();
    const updates = allNodes.map(node => {
        const metadata = nodeMetadata[node.id];
        const data = metadata.additional_data?.display_data;
        if (!data) return null;

        const isStructural = (data.flow === 'Structural');
        
        if (layer === 'structural' && isStructural) {
            return { id: node.id, hidden: !isVisible };
        }
        if (layer === 'functional' && !isStructural) {
            return { id: node.id, hidden: !isVisible };
        }
        return null;
    }).filter(u => u !== null);
    
    nodes.update(updates);
}

function switchTab(tabId) {
    currentTab = tabId;
    
    // Update tab styles
    document.querySelectorAll('.sidebar-tabs .tab').forEach(t => {
        t.classList.remove('active');
        if (t.getAttribute('onclick').includes(`'${tabId}'`)) t.classList.add('active');
    });
    
    // Switch content
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    const content = document.getElementById(tabId + '-content');
    if (content) {
        content.style.display = 'block';
        if (tabId === 'hotspots') renderDashboard();
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

            <!-- 6. STRUCTURAL LAYER -->
            <div style="font-weight: 700; color: #666; margin: 15px 0 10px 0; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 5px;">🏗️ Structural Layer</div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #00897b; transform: rotate(45deg); margin: 0 11px 0 1px;"></div>
                <span><b>Folder (Hexagon)</b></span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 12px; font-size: 12px;">
                <div style="width: 18px; height: 18px; background: #78909c; margin-right: 10px;"></div>
                <span><b>File (Box)</b></span>
            </div>

            <div style="font-weight: 700; color: #666; margin: 20px 0 15px 0; font-size: 11px; text-transform: uppercase;">Execution Signals</div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #4caf50; border-radius: 2px; margin-right: 10px;"></div>
                <span>Passed execution</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #f44336; border-radius: 2px; margin-right: 10px;"></div>
                <span>Failed execution</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px; font-size: 12px;">
                <div style="width: 12px; height: 12px; background: #ff9800; border-radius: 2px; margin-right: 10px;"></div>
                <span>Partial fail / affected by failed descendants</span>
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


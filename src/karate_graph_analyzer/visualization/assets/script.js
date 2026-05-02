function toggleLegend() {
    var legend = document.getElementById('legend');
    if (legend.style.display === 'none') {
        legend.style.display = 'block';
    } else {
        legend.style.display = 'none';
    }
}

var nodeData = DATA_PLACEHOLDER;
var isFocused = false;

// Search functionality
function handleSearch(query) {
    const resultsDiv = document.getElementById('search-results');
    if (!query || query.length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }

    const searchTerms = query.toLowerCase().split(' ');
    const matches = [];
    
    for (const id in nodeData) {
        const node = nodeData[id];
        const searchableText = (node.name + ' ' + node.type + ' ' + (node.file_path || '')).toLowerCase();
        
        if (searchTerms.every(term => searchableText.includes(term))) {
            matches.push({ id, ...node });
        }
        if (matches.length >= 10) break;
    }

    if (matches.length > 0) {
        resultsDiv.innerHTML = matches.map(m => `
            <div class="search-result-item" onclick="focusOnNode('${m.id}')">
                <span>${m.name.length > 35 ? '...' + m.name.slice(-32) : m.name}</span>
                <span class="search-result-type">${m.type}</span>
            </div>
        `).join('');
        resultsDiv.style.display = 'block';
    } else {
        resultsDiv.style.display = 'none';
    }
}

function focusOnNode(nodeId) {
    document.getElementById('search-results').style.display = 'none';
    document.getElementById('node-search').value = nodeData[nodeId].name;
    
    // Show all nodes first if we were focused
    if (isFocused) {
        resetFocus();
    }

    network.focus(nodeId, {
        scale: 1.2,
        animation: {
            duration: 1000,
            easingFunction: 'easeInOutQuad'
        }
    });
    
    // Trigger click to show details
    network.selectNodes([nodeId]);
    showDetails(nodeId);
}

function applyLegendFilter() {
    // Filter legend based on mode
    var mode = null;
    for (var id in nodeData) {
        mode = nodeData[id].visualization_mode;
        if (mode) break;
    }
    
    if (mode) {
        var legendDiv = document.getElementById('legend');
        var groups = legendDiv.querySelectorAll('h3');
        groups.forEach(function(g) {
            var text = g.innerText;
            var parent = g; // In the new template, h3 and its following items are siblings or inside groups. 
            // Actually, let's just hide the H3 and the next legend-items until the next H3 or HR
            var toHide = [g];
            var next = g.nextElementSibling;
            while (next && next.tagName !== 'H3' && next.tagName !== 'HR') {
                toHide.push(next);
                next = next.nextElementSibling;
            }

            var shouldHide = false;
            if (mode === "EXECUTION") {
                if (text.includes("Comparison") || text.includes("Components")) shouldHide = true;
            } else if (mode === "DIFF") {
                if (text.includes("Execution") || text.includes("Components")) shouldHide = true;
            } else {
                if (text.includes("Execution") || text.includes("Comparison")) shouldHide = true;
            }

            if (shouldHide) {
                toHide.forEach(el => el.style.display = "none");
            }
        });
    }
}

// Keyboard shortcut Ctrl+K to search
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('node-search').focus();
    }
});

function showDetails(nodeId) {
    var detailsDiv = document.getElementById('node-details');
    var data = nodeData[nodeId];
    if (data) {
        let diffClass = "";
        if (data.diff_status === "ADDED") diffClass = "diff-added";
        else if (data.diff_status === "REMOVED") diffClass = "diff-removed";
        else if (data.diff_status === "MODIFIED") diffClass = "diff-modified";

        var html = `<div class="detail-header ${diffClass}">` + data.name + '</div>';
        
        // Execution Status Section
        if (data.execution_status) {
            let statusClass = data.execution_status === "PASSED" ? "status-passed" : "status-failed";
            html += `<div class="detail-row"><span class="detail-label">Result:</span><span class="${statusClass}">${data.execution_status}</span></div>`;
            
            if (data.execution_details && data.execution_details.error) {
                html += `<div class="error-message"><strong>Error at ${data.execution_details.failed_step || 'unknown step'}:</strong>\n${data.execution_details.error}</div>`;
            }
        }

        html += '<div class="detail-row"><span class="detail-label">Type:</span><span class="detail-value">' + data.type + '</span></div>';
        
        if (data.file_path) {
            html += '<div class="detail-row"><span class="detail-label">File:</span><span class="detail-value">' + data.file_path + '</span></div>';
        }
        if (data.line_number) {
            html += '<div class="detail-row"><span class="detail-label">Line:</span><span class="detail-value">' + data.line_number + '</span></div>';
        }
        
        if (data.jira_tags && data.jira_tags.length > 0) {
            html += '<div class="detail-row"><span class="detail-label">Jira:</span>';
            data.jira_tags.forEach(function(tag) {
                html += '<span class="jira-tag">' + tag + '</span>';
            });
            html += '</div>';
        }

        if (data.additional_data) {
            html += '<hr><div style="font-weight:bold; margin-bottom:5px;">Metadata:</div>';
            for (var key in data.additional_data) {
                var val = data.additional_data[key];
                if (val !== null && val !== undefined) {
                    if (typeof val === 'object') {
                        html += '<div class="detail-row" style="font-size:12px; align-items:flex-start;"><span class="detail-label" style="margin-top:2px;">' + key + ':</span><div style="display:flex; flex-direction:column; gap:2px;">';
                        for (var subKey in val) {
                            html += '<div><span style="color:#666; font-weight:600; text-transform:uppercase;">[' + subKey + ']</span> <span style="word-break:break-all;">' + val[subKey] + '</span></div>';
                        }
                        html += '</div></div>';
                    } else {
                        html += '<div class="detail-row" style="font-size:12px;"><span class="detail-label">' + key + ':</span><span class="detail-value">' + val + '</span></div>';
                    }
                }
            }
        }

        document.getElementById('details-content').innerHTML = html;
        detailsDiv.style.display = 'block';
    }
}

// Safe initialization for custom events
function initEvents() {
    if (typeof network !== 'undefined') {
        // Disable physics after initial stabilization to keep UI responsive
        network.on("stabilizationIterationsDone", function() {
            console.log("Karate Graph: Stabilization complete, disabling physics for performance.");
            network.setOptions({ physics: { enabled: false } });
        });

        // Handle double click to focus on a node and its full recursive dependency chain
        network.on("doubleClick", function(params) {
            if (params.nodes.length > 0) {
                // Disable physics during focus to prevent lag
                network.setOptions({ physics: { enabled: false } });
                
                var targetId = params.nodes[0];
                var nodesToKeep = new Set();
                nodesToKeep.add(targetId);

                function findDescendants(nodeId) {
                    var children = network.getConnectedNodes(nodeId, 'to');
                    children.forEach(function(childId) {
                        if (!nodesToKeep.has(childId)) {
                            nodesToKeep.add(childId);
                            findDescendants(childId);
                        }
                    });
                }

                function findAncestors(nodeId) {
                    var parents = network.getConnectedNodes(nodeId, 'from');
                    parents.forEach(function(parentId) {
                        if (!nodesToKeep.has(parentId)) {
                            nodesToKeep.add(parentId);
                            findAncestors(parentId);
                        }
                    });
                }

                findDescendants(targetId);
                findAncestors(targetId);

                var contextNodes = new Set();
                nodesToKeep.forEach(function(nodeId) {
                    var neighbors = network.getConnectedNodes(nodeId);
                    neighbors.forEach(function(neighborId) {
                        contextNodes.add(neighborId);
                    });
                });
                
                contextNodes.forEach(id => nodesToKeep.add(id));

                var allNodeIds = nodes.getIds();
                var updates = allNodeIds.map(function(id) {
                    return { id: id, hidden: !nodesToKeep.has(id) };
                });
                nodes.update(updates);
                isFocused = true;
                
                setTimeout(function() {
                    network.fit({
                        nodes: Array.from(nodesToKeep),
                        animation: {
                            duration: 800,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                }, 50);
            }
        });

        // Handle single click to show details or reset focus
        network.on("click", function(params) {
            var detailsDiv = document.getElementById('node-details');
            if (params.nodes.length === 0) {
                if (isFocused) {
                    resetFocus();
                }
                detailsDiv.style.display = 'none';
                document.getElementById('search-results').style.display = 'none';
                return;
            }
            showDetails(params.nodes[0]);
        });

        console.log("Karate Graph: Custom events initialized successfully.");
    } else {
        setTimeout(initEvents, 100);
    }
}

function resetFocus() {
    var allNodeIds = nodes.getIds();
    var updates = allNodeIds.map(function(id) {
        return { id: id, hidden: false };
    });
    nodes.update(updates);
    isFocused = false;
    network.fit({ animation: true });
}

// Global Startup
applyLegendFilter();
initEvents();

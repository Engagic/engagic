<script lang="ts">
    import { ApiService } from '$lib/api';
    import IconCalendar from '$components/icons/Calendar.svelte';
    import IconLocation from '$components/icons/Location.svelte';
    import IconBookmark from '$components/icons/Bookmark.svelte';
    
    export let meetingData: any;
    export let summary: string = '';
    
    let isProcessing = $state(false);
    let processedSummary = $state('');
    let showFullSummary = $state(false);
    
    // Parse the AI summary into structured sections
    const parseSummary = (summaryText: string) => {
        if (!summaryText) return [];
        
        const sections = summaryText.split('--- SECTION').filter(section => section.trim());
        
        return sections.map((section, index) => {
            const lines = section.split('\n').filter(line => line.trim());
            const title = lines[0]?.replace(/^\d+\s*SUMMARY\s*---/, '').trim() || `Section ${index + 1}`;
            const content = lines.slice(1).join('\n').trim();
            
            // Extract key items from bullet points
            const items = content.split('\n')
                .filter(line => line.trim().startsWith('•') || line.trim().startsWith('-') || line.trim().startsWith('*'))
                .map(line => line.replace(/^[•\-\*]\s*/, '').trim())
                .filter(item => item.length > 0);
            
            return {
                title,
                content,
                items,
                highlight: items.some(item => 
                    item.toLowerCase().includes('public hearing') || 
                    item.toLowerCase().includes('action required') ||
                    item.toLowerCase().includes('deadline')
                )
            };
        });
    };
    
    const processAgenda = async () => {
        if (!meetingData?.packet_url || isProcessing) return;
        
        isProcessing = true;
        
        try {
            // This would call your backend API to process the agenda
            const response = await fetch(`${ApiService.API_BASE_URL}/api/process-agenda`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    packet_url: meetingData.packet_url,
                    city_slug: meetingData.city_slug || 'cityofpaloalto',
                    meeting_name: meetingData.title,
                    meeting_date: meetingData.start,
                    meeting_id: meetingData.meeting_id?.toString()
                })
            });
            
            if (!response.ok) {
                throw new Error(`Processing failed: ${response.status}`);
            }
            
            const result = await response.json();
            processedSummary = result.summary || 'Processing completed but no summary available.';
            
        } catch (error) {
            console.error('Error processing agenda:', error);
            processedSummary = 'Failed to process agenda. Please try again later.';
        } finally {
            isProcessing = false;
        }
    };
    
    $: summaryToShow = processedSummary || summary;
    $: parsedSections = parseSummary(summaryToShow);
    $: hasContent = summaryToShow && summaryToShow.trim().length > 0;
</script>

<div class="agenda-detail">
    <div class="meeting-header">
        <div class="meeting-info">
            <h1 class="meeting-title">{meetingData?.title || 'City Council Meeting'}</h1>
            
            <div class="meeting-meta">
                {#if meetingData?.start}
                    <div class="meta-item">
                        <IconCalendar />
                        <span>{new Date(meetingData.start).toLocaleDateString('en-US', {
                            weekday: 'long',
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit'
                        })}</span>
                    </div>
                {/if}
                
                {#if meetingData?.city_name}
                    <div class="meta-item">
                        <IconLocation />
                        <span>{meetingData.city_name}</span>
                    </div>
                {/if}
            </div>
        </div>
        
        <div class="meeting-actions">
            {#if meetingData?.packet_url}
                <a href={meetingData.packet_url} target="_blank" rel="noopener noreferrer" class="action-button primary">
                    View Full Agenda PDF
                </a>
            {/if}
            
            {#if !hasContent}
                <button 
                    class="action-button secondary"
                    onclick={processAgenda}
                    disabled={isProcessing}
                >
                    {isProcessing ? 'Processing...' : 'Get AI Summary'}
                </button>
            {/if}
        </div>
    </div>

    {#if isProcessing}
        <div class="processing-state">
            <div class="spinner"></div>
            <h3>Processing Meeting Agenda</h3>
            <p>Our AI is reading through the meeting packet and extracting key information...</p>
        </div>
    {/if}

    {#if hasContent && !isProcessing}
        <div class="summary-content">
            <div class="summary-header">
                <IconBookmark />
                <h2>Key Agenda Items</h2>
                <p>AI-powered summary of important topics and decisions</p>
            </div>

            <div class="sections-container">
                {#each parsedSections as section, index}
                    <div class="summary-section" class:highlight={section.highlight}>
                        <h3 class="section-title">
                            {section.title}
                            {#if section.highlight}
                                <span class="highlight-badge">Action Required</span>
                            {/if}
                        </h3>
                        
                        {#if section.items.length > 0}
                            <ul class="item-list">
                                {#each section.items.slice(0, showFullSummary ? undefined : 3) as item}
                                    <li class="agenda-item-summary">{item}</li>
                                {/each}
                            </ul>
                            
                            {#if section.items.length > 3 && !showFullSummary}
                                <button 
                                    class="show-more-button"
                                    onclick={() => showFullSummary = true}
                                >
                                    Show {section.items.length - 3} more items...
                                </button>
                            {/if}
                        {:else}
                            <p class="section-content">{section.content}</p>
                        {/if}
                    </div>
                {/each}
            </div>

            <div class="summary-footer">
                <p>
                    <strong>Important:</strong> This is an AI-generated summary. 
                    Please review the full agenda PDF for complete details and official information.
                </p>
            </div>
        </div>
    {/if}
</div>

<style>
    .agenda-detail {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }

    .meeting-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 24px;
        margin-bottom: 32px;
        padding-bottom: 24px;
        border-bottom: 1px solid var(--input-border);
    }

    .meeting-info {
        flex: 1;
    }

    .meeting-title {
        font-size: 2rem;
        font-weight: 700;
        color: var(--secondary);
        margin: 0 0 16px 0;
        line-height: 1.2;
    }

    .meeting-meta {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .meta-item {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--gray);
        font-size: 0.95rem;
    }

    .meta-item :global(svg) {
        width: 16px;
        height: 16px;
        stroke: var(--civic-blue);
    }

    .meeting-actions {
        display: flex;
        flex-direction: column;
        gap: 12px;
        flex-shrink: 0;
    }

    .action-button {
        padding: 12px 20px;
        border-radius: 8px;
        font-weight: 600;
        text-decoration: none;
        text-align: center;
        cursor: pointer;
        border: none;
        transition: all 0.2s ease;
        font-size: 0.9rem;
    }

    .action-button.primary {
        background: var(--civic-gradient);
        color: white;
        box-shadow: 0 4px 12px rgba(29, 78, 216, 0.3);
    }

    .action-button.primary:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(29, 78, 216, 0.4);
    }

    .action-button.secondary {
        background: var(--white);
        color: var(--civic-blue);
        border: 2px solid var(--civic-blue);
    }

    .action-button.secondary:hover {
        background: var(--civic-blue);
        color: white;
    }

    .action-button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }

    .processing-state {
        text-align: center;
        padding: 48px 20px;
        background: var(--light-gray);
        border-radius: 16px;
        border: 1px solid var(--input-border);
    }

    .spinner {
        width: 32px;
        height: 32px;
        border: 3px solid var(--input-border);
        border-top: 3px solid var(--civic-blue);
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 16px;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .processing-state h3 {
        font-size: 1.25rem;
        color: var(--secondary);
        margin: 0 0 8px 0;
    }

    .processing-state p {
        color: var(--gray);
        margin: 0;
    }

    .summary-content {
        background: var(--white);
        border-radius: 16px;
        border: 1px solid var(--input-border);
        overflow: hidden;
    }

    .summary-header {
        padding: 24px;
        background: var(--light-gray);
        text-align: center;
        border-bottom: 1px solid var(--input-border);
    }

    .summary-header :global(svg) {
        width: 24px;
        height: 24px;
        stroke: var(--civic-gold);
        margin-bottom: 8px;
    }

    .summary-header h2 {
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--secondary);
        margin: 0 0 8px 0;
    }

    .summary-header p {
        color: var(--gray);
        margin: 0;
    }

    .sections-container {
        padding: 24px;
    }

    .summary-section {
        margin-bottom: 32px;
        last-child: margin-bottom: 0;
    }

    .summary-section.highlight {
        padding: 20px;
        background: linear-gradient(135deg, rgba(234, 88, 12, 0.05) 0%, rgba(255, 255, 255, 1) 100%);
        border-radius: 12px;
        border: 1px solid rgba(234, 88, 12, 0.2);
    }

    .section-title {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--secondary);
        margin: 0 0 16px 0;
    }

    .highlight-badge {
        font-size: 0.75rem;
        background: var(--civic-orange);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }

    .item-list {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .agenda-item-summary {
        padding: 12px 0;
        border-bottom: 1px solid var(--input-border);
        line-height: 1.6;
        color: var(--secondary);
    }

    .agenda-item-summary:last-child {
        border-bottom: none;
    }

    .section-content {
        line-height: 1.6;
        color: var(--secondary);
        margin: 0;
    }

    .show-more-button {
        margin-top: 12px;
        padding: 8px 16px;
        background: transparent;
        border: 1px solid var(--civic-blue);
        border-radius: 6px;
        color: var(--civic-blue);
        cursor: pointer;
        font-size: 0.875rem;
        transition: all 0.2s ease;
    }

    .show-more-button:hover {
        background: var(--civic-blue);
        color: white;
    }

    .summary-footer {
        padding: 20px 24px;
        background: var(--light-gray);
        border-top: 1px solid var(--input-border);
    }

    .summary-footer p {
        margin: 0;
        font-size: 0.875rem;
        color: var(--gray);
        text-align: center;
    }

    @media screen and (max-width: 768px) {
        .meeting-header {
            flex-direction: column;
            align-items: stretch;
        }

        .meeting-title {
            font-size: 1.5rem;
        }

        .action-button {
            width: 100%;
        }

        .agenda-detail {
            padding: 16px;
        }

        .sections-container {
            padding: 16px;
        }

        .summary-header {
            padding: 20px 16px;
        }
    }
</style>
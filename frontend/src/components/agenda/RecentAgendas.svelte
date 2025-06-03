<script lang="ts">
    // Mock data for recent agendas
    let recentAgendas = [
        {
            id: 1,
            city: "Palo Alto",
            date: "2024-01-15",
            title: "City Council Regular Meeting",
            summary: "Budget discussions, zoning updates, and public hearings",
            urgent: true
        },
        {
            id: 2,
            city: "Mountain View",
            date: "2024-01-12",
            title: "Planning Commission Meeting",
            summary: "New housing development proposals",
            urgent: false
        },
        {
            id: 3,
            city: "San Francisco",
            date: "2024-01-10",
            title: "Board of Supervisors Meeting",
            summary: "Transportation infrastructure and climate initiatives",
            urgent: false
        }
    ];
</script>

<div class="recent-agendas">
    <h3>Recent Agendas</h3>
    <div class="agenda-list">
        {#each recentAgendas as agenda}
            <a href="/agenda/{agenda.id}" class="agenda-item" class:urgent={agenda.urgent}>
                <div class="agenda-header">
                    <div class="city-name">{agenda.city}</div>
                    <div class="agenda-date">{agenda.date}</div>
                </div>
                <div class="agenda-title">{agenda.title}</div>
                <div class="agenda-summary">{agenda.summary}</div>
                {#if agenda.urgent}
                    <div class="urgent-badge">Action Required</div>
                {/if}
            </a>
        {/each}
    </div>
</div>

<style>
    .recent-agendas {
        position: absolute;
        top: var(--padding);
        left: var(--padding);
        right: var(--padding);
        max-width: 300px;
    }

    .recent-agendas h3 {
        font-size: 14px;
        color: var(--gray);
        margin-bottom: 8px;
        font-weight: 600;
    }

    .agenda-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .agenda-item {
        display: block;
        padding: 10px;
        background: var(--button);
        border-radius: var(--border-radius);
        text-decoration: none;
        color: inherit;
        transition: all 0.15s;
        border-left: 3px solid transparent;
    }

    .agenda-item:hover {
        background: var(--button-hover);
        transform: translateX(2px);
    }

    .agenda-item.urgent {
        border-left-color: var(--civic-orange);
    }

    .agenda-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }

    .city-name {
        font-size: 12px;
        font-weight: 600;
        color: var(--civic-blue);
    }

    .agenda-date {
        font-size: 11px;
        color: var(--gray);
    }

    .agenda-title {
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 2px;
        line-height: 1.3;
    }

    .agenda-summary {
        font-size: 11px;
        color: var(--gray);
        line-height: 1.3;
    }

    .urgent-badge {
        font-size: 10px;
        background: var(--civic-orange);
        color: var(--white);
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin-top: 6px;
        font-weight: 600;
    }

    @media screen and (max-width: 768px) {
        .recent-agendas {
            display: none;
        }
    }
</style>
<script lang="ts">
    import { browser } from "$app/environment";
    import IconSettings from "$components/icons/Settings.svelte";
    import IconBookmark from "$components/icons/Bookmark.svelte";
    
    let notificationsEnabled = $state(false);
    let emailAddress = $state('');
    let selectedTopics = $state<string[]>([]);
    let reminderTime = $state('24'); // hours before meeting
    
    const topicOptions = [
        { id: 'housing', label: 'Housing & Development', icon: '🏠' },
        { id: 'transportation', label: 'Transportation', icon: '🚌' },
        { id: 'environment', label: 'Environment', icon: '🌱' },
        { id: 'budget', label: 'Budget & Finance', icon: '💰' },
        { id: 'safety', label: 'Public Safety', icon: '🚨' },
        { id: 'parks', label: 'Parks & Recreation', icon: '🌳' },
        { id: 'business', label: 'Business & Economy', icon: '🏢' },
        { id: 'education', label: 'Education', icon: '📚' }
    ];
    
    const reminderOptions = [
        { value: '1', label: '1 hour before' },
        { value: '6', label: '6 hours before' },
        { value: '24', label: '1 day before' },
        { value: '72', label: '3 days before' },
        { value: '168', label: '1 week before' }
    ];
    
    const toggleTopic = (topicId: string) => {
        if (selectedTopics.includes(topicId)) {
            selectedTopics = selectedTopics.filter(id => id !== topicId);
        } else {
            selectedTopics = [...selectedTopics, topicId];
        }
        savePreferences();
    };
    
    const savePreferences = () => {
        if (!browser) return;
        
        const preferences = {
            notificationsEnabled,
            emailAddress,
            selectedTopics,
            reminderTime
        };
        
        localStorage.setItem('notificationPreferences', JSON.stringify(preferences));
        
        // In a real app, you'd also send this to your backend
        console.log('Notification preferences saved:', preferences);
    };
    
    const loadPreferences = () => {
        if (!browser) return;
        
        const saved = localStorage.getItem('notificationPreferences');
        if (saved) {
            try {
                const preferences = JSON.parse(saved);
                notificationsEnabled = preferences.notificationsEnabled || false;
                emailAddress = preferences.emailAddress || '';
                selectedTopics = preferences.selectedTopics || [];
                reminderTime = preferences.reminderTime || '24';
            } catch (e) {
                console.error('Failed to load notification preferences:', e);
            }
        }
    };
    
    const requestNotificationPermission = async () => {
        if (!browser || !('Notification' in window)) {
            alert('Browser notifications are not supported in this browser.');
            return;
        }
        
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
            notificationsEnabled = true;
            savePreferences();
            
            // Show a test notification
            new Notification('engagic Notifications Enabled', {
                body: 'You\'ll now receive notifications about topics you care about!',
                icon: '/favicon.png'
            });
        } else {
            notificationsEnabled = false;
        }
    };
    
    // Load preferences on mount
    if (browser) {
        loadPreferences();
    }
</script>

<div class="notification-preferences">
    <div class="preferences-header">
        <IconSettings />
        <h2>Notification Preferences</h2>
        <p>Stay informed about local government decisions that matter to you</p>
    </div>

    <div class="preference-section">
        <div class="section-header">
            <h3>Notification Method</h3>
        </div>
        
        <div class="notification-methods">
            <label class="checkbox-label">
                <input 
                    type="checkbox" 
                    bind:checked={notificationsEnabled}
                    onchange={notificationsEnabled ? requestNotificationPermission : savePreferences}
                />
                <span class="checkbox-custom"></span>
                Browser Notifications
            </label>
            
            <div class="email-input-group">
                <label for="email-notifications">Email Address (optional)</label>
                <input 
                    id="email-notifications"
                    type="email" 
                    bind:value={emailAddress}
                    onchange={savePreferences}
                    placeholder="your.email@example.com"
                    class="email-input"
                />
            </div>
        </div>
    </div>

    <div class="preference-section">
        <div class="section-header">
            <IconBookmark />
            <h3>Topics of Interest</h3>
            <p>Select topics you want to be notified about</p>
        </div>
        
        <div class="topics-grid">
            {#each topicOptions as topic}
                <button 
                    class="topic-button"
                    class:selected={selectedTopics.includes(topic.id)}
                    onclick={() => toggleTopic(topic.id)}
                >
                    <span class="topic-icon">{topic.icon}</span>
                    <span class="topic-label">{topic.label}</span>
                </button>
            {/each}
        </div>
    </div>

    <div class="preference-section">
        <div class="section-header">
            <h3>Reminder Timing</h3>
            <p>When would you like to be reminded about upcoming meetings?</p>
        </div>
        
        <select 
            bind:value={reminderTime}
            onchange={savePreferences}
            class="reminder-select"
        >
            {#each reminderOptions as option}
                <option value={option.value}>{option.label}</option>
            {/each}
        </select>
    </div>

    {#if selectedTopics.length > 0}
        <div class="preferences-summary">
            <h4>Your Notification Setup</h4>
            <div class="summary-items">
                <div class="summary-item">
                    <strong>Topics:</strong> {selectedTopics.length} selected
                </div>
                <div class="summary-item">
                    <strong>Timing:</strong> {reminderOptions.find(r => r.value === reminderTime)?.label}
                </div>
                {#if notificationsEnabled}
                    <div class="summary-item">
                        <strong>Method:</strong> Browser notifications enabled
                    </div>
                {/if}
                {#if emailAddress}
                    <div class="summary-item">
                        <strong>Email:</strong> {emailAddress}
                    </div>
                {/if}
            </div>
        </div>
    {/if}
</div>

<style>
    .notification-preferences {
        max-width: 600px;
        margin: 0 auto;
        padding: 20px;
    }

    .preferences-header {
        text-align: center;
        margin-bottom: 32px;
    }

    .preferences-header :global(svg) {
        width: 24px;
        height: 24px;
        stroke: var(--civic-blue);
        margin-bottom: 8px;
    }

    .preferences-header h2 {
        font-size: 1.75rem;
        font-weight: 600;
        color: var(--secondary);
        margin: 0 0 8px 0;
    }

    .preferences-header p {
        color: var(--gray);
        margin: 0;
        font-size: 1rem;
    }

    .preference-section {
        margin-bottom: 32px;
        padding: 24px;
        background: var(--white);
        border: 1px solid var(--input-border);
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }

    .section-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 16px;
    }

    .section-header :global(svg) {
        width: 20px;
        height: 20px;
        stroke: var(--civic-blue);
    }

    .section-header h3 {
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--secondary);
        margin: 0;
    }

    .section-header p {
        color: var(--gray);
        margin: 4px 0 0 0;
        font-size: 0.9rem;
    }

    .notification-methods {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 12px;
        cursor: pointer;
        font-weight: 500;
    }

    .checkbox-label input[type="checkbox"] {
        display: none;
    }

    .checkbox-custom {
        width: 20px;
        height: 20px;
        border: 2px solid var(--input-border);
        border-radius: 4px;
        position: relative;
        transition: all 0.2s ease;
    }

    .checkbox-label input[type="checkbox"]:checked + .checkbox-custom {
        background: var(--civic-blue);
        border-color: var(--civic-blue);
    }

    .checkbox-label input[type="checkbox"]:checked + .checkbox-custom::after {
        content: '';
        position: absolute;
        left: 6px;
        top: 2px;
        width: 6px;
        height: 10px;
        border: solid white;
        border-width: 0 2px 2px 0;
        transform: rotate(45deg);
    }

    .email-input-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .email-input-group label {
        font-weight: 500;
        color: var(--secondary);
        font-size: 0.9rem;
    }

    .email-input {
        padding: 12px 16px;
        border: 1px solid var(--input-border);
        border-radius: 8px;
        font-size: 1rem;
        background: var(--input-bg);
        transition: all 0.2s ease;
    }

    .email-input:focus {
        outline: none;
        border-color: var(--civic-blue);
        box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.1);
    }

    .topics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
    }

    .topic-button {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        background: var(--white);
        border: 2px solid var(--input-border);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 0.9rem;
        font-weight: 500;
    }

    .topic-button:hover {
        border-color: var(--civic-blue);
    }

    .topic-button.selected {
        background: var(--civic-blue);
        border-color: var(--civic-blue);
        color: white;
    }

    .topic-icon {
        font-size: 1.1rem;
    }

    .reminder-select {
        width: 100%;
        padding: 12px 16px;
        border: 1px solid var(--input-border);
        border-radius: 8px;
        background: var(--input-bg);
        font-size: 1rem;
        cursor: pointer;
    }

    .reminder-select:focus {
        outline: none;
        border-color: var(--civic-blue);
        box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.1);
    }

    .preferences-summary {
        padding: 20px;
        background: var(--civic-gradient-success);
        color: white;
        border-radius: 12px;
    }

    .preferences-summary h4 {
        margin: 0 0 12px 0;
        font-size: 1.1rem;
        font-weight: 600;
    }

    .summary-items {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .summary-item {
        font-size: 0.9rem;
        opacity: 0.95;
    }

    @media screen and (max-width: 640px) {
        .notification-preferences {
            padding: 16px;
        }

        .preference-section {
            padding: 16px;
        }

        .topics-grid {
            grid-template-columns: 1fr;
        }

        .notification-methods {
            gap: 12px;
        }
    }
</style>
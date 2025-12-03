<script lang="ts">
	import { reportIssue } from '$lib/api';
	import type { IssueType } from '$lib/api/types';

	interface Props {
		entityType: 'item' | 'meeting' | 'matter';
		entityId: string;
		buttonText?: string;
		size?: 'small' | 'medium';
	}

	let { entityType, entityId, buttonText = 'Report Issue', size = 'medium' }: Props = $props();

	let isOpen = $state(false);
	let issueType = $state<IssueType>('inaccurate');
	let description = $state('');
	let submitting = $state(false);
	let submitted = $state(false);
	let error = $state<string | null>(null);

	const issueTypes: { value: IssueType; label: string; description: string }[] = [
		{ value: 'inaccurate', label: 'Inaccurate', description: 'Information is factually incorrect' },
		{ value: 'incomplete', label: 'Incomplete', description: 'Missing important details' },
		{ value: 'misleading', label: 'Misleading', description: 'Could be misinterpreted' },
		{ value: 'offensive', label: 'Offensive', description: 'Contains inappropriate content' },
		{ value: 'other', label: 'Other', description: 'Something else is wrong' }
	];

	function openModal() {
		isOpen = true;
		submitted = false;
		error = null;
	}

	function closeModal() {
		isOpen = false;
		// Reset form after close animation
		setTimeout(() => {
			issueType = 'inaccurate';
			description = '';
			error = null;
		}, 200);
	}

	function handleBackdropClick(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			closeModal();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			closeModal();
		}
	}

	async function handleSubmit() {
		if (submitting) return;

		submitting = true;
		error = null;

		try {
			await reportIssue(entityType, entityId, issueType, description.trim());
			submitted = true;
			// Auto-close after showing success message
			setTimeout(() => {
				closeModal();
			}, 2000);
		} catch (e) {
			console.error('Failed to report issue:', e);
			error = 'Failed to submit report. Please try again.';
		} finally {
			submitting = false;
		}
	}
</script>

<button class="report-trigger {size}" onclick={openModal} aria-label="Report an issue">
	{buttonText}
</button>

{#if isOpen}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<!-- svelte-ignore a11y_interactive_supports_focus -->
	<div
		class="modal-backdrop"
		role="dialog"
		aria-modal="true"
		aria-labelledby="report-title"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
	>
		<div class="modal-content">
			{#if submitted}
				<div class="success-state">
					<div class="success-icon">OK</div>
					<h3 class="success-title">Report Submitted</h3>
					<p class="success-message">Thank you for helping improve our content.</p>
				</div>
			{:else}
				<div class="modal-header">
					<h2 id="report-title" class="modal-title">Report an Issue</h2>
					<button class="close-button" onclick={closeModal} aria-label="Close">
						<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
							<line x1="18" y1="6" x2="6" y2="18"></line>
							<line x1="6" y1="6" x2="18" y2="18"></line>
						</svg>
					</button>
				</div>

				<form class="report-form" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
					<div class="form-group">
						<label for="issue-type" class="form-label">Issue Type</label>
						<select id="issue-type" class="form-select" bind:value={issueType}>
							{#each issueTypes as type}
								<option value={type.value}>{type.label} - {type.description}</option>
							{/each}
						</select>
					</div>

					<div class="form-group">
						<label for="description" class="form-label">Description (optional)</label>
						<textarea
							id="description"
							class="form-textarea"
							bind:value={description}
							placeholder="Provide additional details about the issue..."
							rows="4"
						></textarea>
					</div>

					{#if error}
						<div class="error-message" role="alert">{error}</div>
					{/if}

					<div class="form-actions">
						<button type="button" class="cancel-button" onclick={closeModal} disabled={submitting}>
							Cancel
						</button>
						<button type="submit" class="submit-button" disabled={submitting}>
							{submitting ? 'Submitting...' : 'Submit Report'}
						</button>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
	.report-trigger {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 500;
		background: none;
		border: none;
		color: var(--civic-gray);
		cursor: pointer;
		transition: color 0.2s ease;
		padding: 0;
	}

	.report-trigger:hover {
		color: var(--civic-blue);
		text-decoration: underline;
	}

	.report-trigger.medium {
		font-size: 0.8rem;
	}

	.report-trigger.small {
		font-size: 0.7rem;
	}

	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal-content {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		width: 100%;
		max-width: 480px;
		padding: 1.5rem;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
		animation: slideIn 0.2s ease;
	}

	@keyframes slideIn {
		from {
			opacity: 0;
			transform: translateY(-10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1.25rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid var(--border-primary);
	}

	.modal-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.close-button {
		background: none;
		border: none;
		padding: 0.25rem;
		cursor: pointer;
		color: var(--civic-gray);
		transition: color 0.2s ease;
	}

	.close-button:hover {
		color: var(--text-primary);
	}

	.report-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.form-select,
	.form-textarea {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		padding: 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		color: var(--text-primary);
		transition: border-color 0.2s ease;
	}

	.form-select:focus,
	.form-textarea:focus {
		outline: none;
		border-color: var(--civic-blue);
	}

	.form-textarea {
		resize: vertical;
		min-height: 80px;
	}

	.form-textarea::placeholder {
		color: var(--civic-gray);
	}

	.error-message {
		--error-bg: #fee2e2;
		--error-text: #ef4444;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--error-text);
		padding: 0.5rem 0.75rem;
		background: var(--error-bg);
		border-radius: 6px;
	}

	:global(.dark) .error-message {
		--error-bg: #7f1d1d;
		--error-text: #fca5a5;
	}

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}

	.cancel-button,
	.submit-button {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.6rem 1.25rem;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.cancel-button {
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		color: var(--text-secondary);
	}

	.cancel-button:hover:not(:disabled) {
		background: var(--surface-primary);
		border-color: var(--civic-gray);
	}

	.submit-button {
		background: var(--civic-blue);
		border: 1px solid var(--civic-blue);
		color: white;
	}

	.submit-button:hover:not(:disabled) {
		background: var(--civic-accent);
		border-color: var(--civic-accent);
	}

	.cancel-button:disabled,
	.submit-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* Success state */
	.success-state {
		text-align: center;
		padding: 2rem 1rem;
	}

	.success-icon {
		--success-bg: #dcfce7;
		--success-text: #16a34a;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 48px;
		height: 48px;
		background: var(--success-bg);
		color: var(--success-text);
		border-radius: 50%;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 700;
		margin-bottom: 1rem;
	}

	:global(.dark) .success-icon {
		--success-bg: #14532d;
		--success-text: #86efac;
	}

	.success-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0 0 0.5rem;
	}

	.success-message {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		margin: 0;
	}

	@media (max-width: 480px) {
		.modal-content {
			padding: 1.25rem;
		}

		.form-actions {
			flex-direction: column-reverse;
		}

		.cancel-button,
		.submit-button {
			width: 100%;
		}
	}
</style>

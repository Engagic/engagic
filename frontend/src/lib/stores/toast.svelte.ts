/**
 * Toast Store
 *
 * Global notification system for transient messages.
 */

type ToastType = 'success' | 'error' | 'info';

interface Toast {
	id: string;
	message: string;
	type: ToastType;
}

class ToastStore {
	toasts = $state<Toast[]>([]);
	private timers = new Map<string, ReturnType<typeof setTimeout>>();

	show(message: string, type: ToastType = 'success', duration = 3000) {
		const id = crypto.randomUUID();
		this.toasts = [...this.toasts, { id, message, type }];
		this.timers.set(id, setTimeout(() => this.dismiss(id), duration));
	}

	dismiss(id: string) {
		const timer = this.timers.get(id);
		if (timer) {
			clearTimeout(timer);
			this.timers.delete(id);
		}
		this.toasts = this.toasts.filter(t => t.id !== id);
	}

	success(message: string, duration = 3000) {
		this.show(message, 'success', duration);
	}

	error(message: string, duration = 4000) {
		this.show(message, 'error', duration);
	}

	info(message: string, duration = 3000) {
		this.show(message, 'info', duration);
	}
}

export const toastStore = new ToastStore();

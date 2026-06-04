class DevLogExperience {
    constructor() {
        this.feed = document.getElementById('devlogFeed');
        this.composer = document.getElementById('devlogComposer');
        this.loadMoreButton = document.getElementById('loadMoreDevlogs');
        this.bindComposer();
        this.bindActions(document);
        this.bindLoadMore();
        this.bindProgress();
    }

    bindProgress() {
        document.querySelectorAll('[data-progress-input]').forEach((input) => {
            const value = document.querySelector('[data-progress-value]');
            input.addEventListener('input', () => {
                if (value) value.textContent = `${input.value}%`;
            });
        });
    }

    bindComposer() {
        if (!this.composer) return;
        this.composer.addEventListener('submit', async (event) => {
            event.preventDefault();
            const status = document.getElementById('devlogComposerStatus');
            const button = this.composer.querySelector('button[type="submit"]');
            const data = new FormData(this.composer);
            button.disabled = true;
            if (status) status.textContent = 'Publishing...';
            try {
                const response = await fetch('/devlogs', {
                    method: 'POST',
                    body: data,
                    headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.error || 'Could not publish DevLog.');
                this.feed?.insertAdjacentHTML('afterbegin', payload.html);
                this.bindActions(this.feed?.firstElementChild || document);
                this.composer.reset();
                const progressValue = document.querySelector('[data-progress-value]');
                if (progressValue) progressValue.textContent = '25%';
                if (status) status.textContent = 'Published. Keep the streak alive tomorrow.';
                window.HaradiBots?.formatLocalTimes?.(this.feed?.firstElementChild || document);
                window.toast?.show('DevLog posted.', 'success');
            } catch (error) {
                if (status) status.textContent = error.message;
                window.toast?.show(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });
    }

    bindActions(root) {
        root.querySelectorAll?.('.devlog-card').forEach((card) => {
            if (card.dataset.bound === 'true') return;
            card.dataset.bound = 'true';
            card.addEventListener('click', (event) => this.handleCardClick(event, card));
            const commentForm = card.querySelector('[data-role="comment-form"]');
            commentForm?.addEventListener('submit', (event) => this.submitComment(event, card));
        });
    }

    async handleCardClick(event, card) {
        const button = event.target.closest('[data-action]');
        if (!button) return;
        const action = button.dataset.action;
        if (action === 'comment') {
            card.querySelector('[data-role="comment-form"] input')?.focus();
            return;
        }
        if (action === 'delete' && !confirm('Delete this DevLog?')) {
            return;
        }
        const id = card.dataset.devlogId;
        button.disabled = true;
        try {
            const response = await fetch(`/devlogs/${id}/${action}`, {
                method: 'POST',
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || `Could not ${action}.`);
            if (action === 'delete') {
                card.remove();
                window.toast?.show('DevLog deleted.', 'success');
                return;
            }
            button.classList.toggle('active', payload.status && !payload.status.startsWith('un'));
            if (action === 'pin') {
                button.textContent = payload.is_pinned ? 'Unpin' : 'Pin';
                this.togglePinnedChip(card, payload.is_pinned);
            } else {
                const counterName = action === 'like' ? 'likes' : `${action}s`;
                const counter = card.querySelector(`[data-count="${counterName}"]`);
                if (counter && typeof payload.count === 'number') counter.textContent = payload.count;
            }
        } catch (error) {
            window.toast?.show(error.message, 'error');
        } finally {
            button.disabled = false;
        }
    }

    togglePinnedChip(card, isPinned) {
        let chip = card.querySelector('.devlog-chip');
        if (isPinned && !chip) {
            const holder = card.querySelector('.devlog-card-flags');
            holder?.insertAdjacentHTML('afterbegin', '<span class="devlog-chip">Pinned</span>');
        }
        if (!isPinned && chip && chip.textContent.trim() === 'Pinned') chip.remove();
    }

    async submitComment(event, card) {
        event.preventDefault();
        const form = event.target;
        const input = form.querySelector('input[name="content"]');
        const content = input.value.trim();
        if (!content) return;
        const id = card.dataset.devlogId;
        const data = new FormData(form);
        const button = form.querySelector('button');
        button.disabled = true;
        try {
            const response = await fetch(`/devlogs/${id}/comments`, {
                method: 'POST',
                body: data,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || 'Could not comment.');
            card.querySelector('[data-role="comments"]')?.insertAdjacentHTML('beforeend', payload.html);
            this.bindCommentDelete(card);
            const counter = card.querySelector('[data-count="comments"]');
            if (counter) counter.textContent = payload.count;
            input.value = '';
            window.HaradiBots?.formatLocalTimes?.(card);
        } catch (error) {
            window.toast?.show(error.message, 'error');
        } finally {
            button.disabled = false;
        }
    }

    bindLoadMore() {
        if (!this.loadMoreButton) return;
        this.loadMoreButton.addEventListener('click', async () => {
            const page = this.loadMoreButton.dataset.nextPage;
            const sort = this.loadMoreButton.dataset.sort || 'latest';
            this.loadMoreButton.disabled = true;
            this.loadMoreButton.textContent = 'Loading...';
            try {
                const response = await fetch(`/devlogs?page=${page}&sort=${encodeURIComponent(sort)}&ajax=1`, {
                    headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                const payload = await response.json();
                if (!response.ok) throw new Error('Could not load more DevLogs.');
                this.feed?.insertAdjacentHTML('beforeend', payload.html);
                this.bindActions(this.feed || document);
                window.HaradiBots?.formatLocalTimes?.(this.feed || document);
                if (payload.has_next) {
                    this.loadMoreButton.dataset.nextPage = payload.next_page;
                    this.loadMoreButton.disabled = false;
                    this.loadMoreButton.textContent = 'Load more';
                } else {
                    this.loadMoreButton.remove();
                }
            } catch (error) {
                this.loadMoreButton.disabled = false;
                this.loadMoreButton.textContent = 'Try again';
                window.toast?.show(error.message, 'error');
            }
        });
    }

    bindCommentDelete(root) {
        root.querySelectorAll?.('[data-comment-delete]').forEach((button) => {
            if (button.dataset.bound === 'true') return;
            button.dataset.bound = 'true';
            button.addEventListener('click', async () => {
                if (!confirm('Delete this comment?')) return;
                const comment = button.closest('[data-comment-id]');
                const card = button.closest('.devlog-card');
                button.disabled = true;
                try {
                    const response = await fetch(`/devlogs/comments/${button.dataset.commentDelete}/delete`, {
                        method: 'POST',
                        headers: {'X-Requested-With': 'XMLHttpRequest'}
                    });
                    const payload = await response.json();
                    if (!response.ok) throw new Error(payload.error || 'Could not delete comment.');
                    comment?.remove();
                    const counter = card?.querySelector('[data-count="comments"]');
                    if (counter && typeof payload.count === 'number') counter.textContent = payload.count;
                    window.toast?.show('Comment deleted.', 'success');
                } catch (error) {
                    window.toast?.show(error.message, 'error');
                } finally {
                    button.disabled = false;
                }
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const experience = new DevLogExperience();
    experience.bindCommentDelete(document);
});

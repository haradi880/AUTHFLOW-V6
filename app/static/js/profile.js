// =====================================================
// PROFILE INTERACTIONS
// =====================================================

class ProfileManager {
    constructor() {
        this.init();
    }

    init() {
        this.initFollowButtons();
        this.initProfileTabs();
        this.initProfileLinkCopy();
    }

    initFollowButtons() {
        // Use event delegation for dynamically added buttons or just select them all
        document.addEventListener('click', (e) => {
            const followBtn = e.target.closest('.follow-btn');
            if (followBtn) {
                this.handleFollow(followBtn);
            }
        });
    }

    async handleFollow(button) {
        const username = button.getAttribute('data-username');
        if (!username) return;

        try {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = 'Working...';
            const response = await fetch(`/follow/${username}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.AuthFlow?.csrfToken || ''
                }
            });

            const data = await response.json();

            if (response.ok) {
                const isFollowed = data.status === 'followed';
                this.updateFollowButton(button, isFollowed);
                
                if (window.toast) {
                    toast.show(isFollowed ? `Following @${username}` : `Unfollowed @${username}`, isFollowed ? 'success' : 'info');
                }
                
                // Update follower count if on profile page
                const followerCount = document.querySelector('.profile-stat-value');
                if (followerCount && button.closest('.profile-actions')) {
                    let count = parseInt(followerCount.textContent);
                    followerCount.textContent = isFollowed ? count + 1 : count - 1;
                }
            } else {
                if (window.toast) toast.show(data.error || 'Something went wrong', 'error');
            }
        } catch (error) {
            console.error('Follow error:', error);
            if (window.toast) toast.show('Network error', 'error');
        } finally {
            button.disabled = false;
            if (button.innerHTML === 'Working...') {
                button.innerHTML = button.dataset.originalText || 'Follow';
            }
        }
    }

    updateFollowButton(button, isFollowed) {
        if (isFollowed) {
            button.classList.add('following');
            button.classList.remove('btn-primary');
            button.style.background = 'var(--bg-tertiary)';
            button.style.color = 'var(--text-secondary)';
            button.innerHTML = 'Following';
        } else {
            button.classList.remove('following');
            button.classList.add('btn-primary');
            button.style.background = '';
            button.style.color = '';
            button.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="8.5" cy="7" r="4"/>
                    <line x1="20" y1="8" x2="20" y2="14"/>
                    <line x1="23" y1="11" x2="17" y2="11"/>
                </svg>
                Follow
            `;
        }
    }

    initProfileTabs() {
        const tabs = document.querySelectorAll('[data-profile-tab]');
        if (!tabs.length) return;

        const activateTab = (tabName, activeTab) => {
            tabs.forEach(tab => {
                const isActive = tab === activeTab || tab.dataset.profileTab === tabName;
                tab.classList.toggle('active', isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });

            document.querySelectorAll('.tab-content').forEach(content => {
                content.style.display = content.id === `${tabName}-tab` ? 'block' : 'none';
            });
        };

        tabs.forEach(tab => {
            tab.addEventListener('click', event => {
                event.preventDefault();
                const tabName = tab.dataset.profileTab;
                if (!tabName) return;
                history.replaceState(null, '', `#${tabName}`);
                activateTab(tabName, tab);
            });
        });

        const initialTab = (window.location.hash || '#blogs').replace('#', '');
        const initialElement = document.querySelector(`[data-profile-tab="${initialTab}"]`) || tabs[0];
        activateTab(initialElement.dataset.profileTab, initialElement);
    }

    initProfileLinkCopy() {
        document.getElementById('copyProfileLink')?.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(window.location.href.split('#')[0]);
                if (window.toast) toast.show('Profile link copied.', 'success');
            } catch (error) {
                if (window.toast) toast.show('Copy failed. Select the URL manually.', 'warning');
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.profileManager = new ProfileManager();
});

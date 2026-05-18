// =====================================================
// DASHBOARD INTERACTIVITY
// =====================================================

class Dashboard {
    constructor() {
        this.sidebar = document.querySelector('.sidebar');
        this.menuToggle = document.querySelector('.menu-toggle');
        this.overlay = document.querySelector('.sidebar-overlay');
        this.init();
    }

    init() {
        if (this.menuToggle) {
            this.menuToggle.addEventListener('click', () => this.toggleSidebar());
        }
        
        if (this.overlay) {
            this.overlay.addEventListener('click', () => this.closeSidebar());
        }

        // Close sidebar on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeSidebar();
        });

        // Auto-close sidebar when resizing back to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth > 1024) {
                this.closeSidebar();
            }
        });
        
        // Active nav item
        this.setActiveNavItem();
        
        // Initialize search
        this.initSearch();
        
        // Initialize animations
        this.initAnimations();
    }

    toggleSidebar() {
        if (!this.sidebar || !this.overlay) return;
        this.sidebar.classList.toggle('open');
        this.overlay.classList.toggle('active');
        // Prevent body scroll when sidebar is open on mobile
        document.body.style.overflow = this.sidebar.classList.contains('open') ? 'hidden' : '';
    }

    closeSidebar() {
        if (!this.sidebar || !this.overlay) return;
        this.sidebar.classList.remove('open');
        this.overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    setActiveNavItem() {
        const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
        document.querySelectorAll('.nav-item').forEach(item => {
            const href = (item.getAttribute('href') || '').replace(/\/$/, '') || '/';
            if (href === currentPath) {
                item.classList.add('active');
            }
        });
    }

    initSearch() {
        const searchInput = document.querySelector('.search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchTable(e.target.value);
            });
        }
    }

    searchTable(query) {
        const table = document.querySelector('.admin-table tbody');
        if (!table) return;
        
        const rows = table.querySelectorAll('tr');
        const searchTerm = query.toLowerCase();
        
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    }

    initAnimations() {
        // Staggered animations for cards
        const cards = document.querySelectorAll('.stat-card, .content-card');
        cards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                card.style.transition = 'all 0.5s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 100 * index);
        });
    }
}

// =====================================================
// INITIALIZATION
// =====================================================

document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
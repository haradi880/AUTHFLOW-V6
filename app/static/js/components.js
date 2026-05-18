// =====================================================
// REUSABLE COMPONENTS
// =====================================================

class ComponentManager {
    constructor() {
        this.init();
    }

    init() {
        this.initDropdowns();
        this.initModals();
        this.initTooltips();
        this.initSkeletons();
    }

    initDropdowns() {
        document.querySelectorAll('[data-dropdown]').forEach(trigger => {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                const dropdown = document.getElementById(trigger.dataset.dropdown);
                if (dropdown) {
                    dropdown.classList.toggle('active');
                }
            });
        });
        
        document.addEventListener('click', () => {
            document.querySelectorAll('.dropdown.active').forEach(d => d.classList.remove('active'));
        });
    }

    initModals() {
        document.querySelectorAll('[data-modal]').forEach(trigger => {
            trigger.addEventListener('click', () => {
                const modal = document.getElementById(trigger.dataset.modal);
                if (modal) {
                    modal.style.display = 'flex';
                    document.body.style.overflow = 'hidden';
                }
            });
        });
        
        document.querySelectorAll('.modal-close, .modal-overlay').forEach(close => {
            close.addEventListener('click', () => {
                const modal = close.closest('.modal');
                if (modal) {
                    modal.style.display = 'none';
                    document.body.style.overflow = '';
                }
            });
        });
    }

    initTooltips() {
        document.querySelectorAll('[data-tooltip]').forEach(element => {
            element.addEventListener('mouseenter', (e) => {
                const tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.textContent = element.dataset.tooltip;
                document.body.appendChild(tooltip);
                
                const rect = element.getBoundingClientRect();
                tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';
                tooltip.style.left = rect.left + (rect.width - tooltip.offsetWidth) / 2 + 'px';
                
                element.addEventListener('mouseleave', () => tooltip.remove(), { once: true });
            });
        });
    }

    initSkeletons() {
        // Add skeleton loading automatically
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ComponentManager();
});
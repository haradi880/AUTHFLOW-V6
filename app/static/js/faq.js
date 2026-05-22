class FAQCenter {
    constructor() {
        this.search = document.getElementById('faqSearch');
        this.filters = document.getElementById('faqFilters');
        this.items = Array.from(document.querySelectorAll('.faq-item'));
        this.empty = document.getElementById('faqEmpty');
        this.category = 'all';
        this.bind();
    }

    bind() {
        this.search?.addEventListener('input', () => this.apply());
        this.filters?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-category]');
            if (!button) return;
            this.category = button.dataset.category;
            this.filters.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
            this.apply();
        });
        this.items.forEach((item) => {
            item.querySelector('.faq-question')?.addEventListener('click', () => {
                const open = item.classList.toggle('open');
                item.querySelector('.faq-question')?.setAttribute('aria-expanded', String(open));
            });
        });
    }

    apply() {
        const term = (this.search?.value || '').trim().toLowerCase();
        let visible = 0;
        this.items.forEach((item) => {
            const matchesCategory = this.category === 'all' || item.dataset.category === this.category;
            const matchesSearch = !term || item.dataset.search.includes(term);
            const show = matchesCategory && matchesSearch;
            item.hidden = !show;
            if (show) visible += 1;
        });
        if (this.empty) this.empty.hidden = visible !== 0;
    }
}

document.addEventListener('DOMContentLoaded', () => new FAQCenter());

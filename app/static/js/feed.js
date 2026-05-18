document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.feed-filters select').forEach((select) => {
        select.addEventListener('change', () => {
            const form = select.closest('form');
            if (form) form.submit();
        });
    });

    document.querySelectorAll('.feed-filters .search-input').forEach((input) => {
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                const query = input.value.trim();
                if (query) window.location.href = `/search?q=${encodeURIComponent(query)}`;
            }
        });
    });
});

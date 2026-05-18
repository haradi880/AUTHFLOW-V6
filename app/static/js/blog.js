async function postAction(url) {
    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) throw new Error('Request failed');
    return response.json();
}

window.toggleBlogLike = async function toggleBlogLike(blogId, button) {
    try {
        button.disabled = true;
        const data = await postAction(`/blog/${blogId}/like`);
        button.classList.toggle('active', data.status === 'liked');
        const count = button.querySelector('.blog-action-count');
        if (count) count.textContent = data.count;
    } catch (error) {
        if (window.toast) toast.show('Please sign in to like posts.', 'warning');
    } finally {
        button.disabled = false;
    }
};

window.toggleBlogBookmark = async function toggleBlogBookmark(blogId, button) {
    try {
        button.disabled = true;
        const data = await postAction(`/blog/${blogId}/bookmark`);
        button.classList.toggle('active', data.status === 'bookmarked');
        if (window.toast) toast.show(data.status === 'bookmarked' ? 'Post saved.' : 'Post removed.', 'success');
    } catch (error) {
        if (window.toast) toast.show('Please sign in to save posts.', 'warning');
    } finally {
        button.disabled = false;
    }
};

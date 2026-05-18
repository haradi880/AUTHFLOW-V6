// =====================================================
// MARKDOWN EDITOR
// =====================================================

class MarkdownEditor {
    constructor() {
        this.markdownInput = document.getElementById('markdownInput');
        this.preview = document.getElementById('markdownPreview');
        this.title = document.getElementById('blogTitle');
        this.autoSaveTimer = null;
        this.lastSaved = null;
        this.init();
    }

    init() {
        if (this.markdownInput) {
            this.markdownInput.addEventListener('input', () => {
                this.updatePreview();
                this.scheduleAutoSave();
            });
            
            // Load draft if exists
            this.loadDraft();
            
            // Keyboard shortcuts
            this.initKeyboardShortcuts();
        }
    }

    updatePreview() {
        if (this.preview && typeof marked !== 'undefined') {
            this.preview.innerHTML = marked.parse(this.markdownInput.value);
        }
    }

    scheduleAutoSave() {
        clearTimeout(this.autoSaveTimer);
        this.autoSaveTimer = setTimeout(() => {
            this.saveDraft();
        }, 3000);
    }

    saveDraft() {
        const draft = {
            title: this.title?.value || '',
            content: this.markdownInput?.value || '',
            timestamp: new Date().toISOString()
        };
        
        localStorage.setItem('blog_draft', JSON.stringify(draft));
        this.lastSaved = new Date();
        this.updateSaveIndicator();
    }

    loadDraft() {
        const draft = localStorage.getItem('blog_draft');
        if (draft) {
            const data = JSON.parse(draft);
            if (data.content && confirm('You have an unsaved draft. Load it?')) {
                if (this.markdownInput) this.markdownInput.value = data.content;
                if (this.title) this.title.value = data.title;
                this.updatePreview();
            }
        }
    }

    updateSaveIndicator() {
        // Update UI to show saved status
    }

    initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                this.saveDraft();
                toast.show('Draft saved!', 'success');
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new MarkdownEditor();
});
// =====================================================
// UTILITY FUNCTIONS
// =====================================================

class ToastManager {
    constructor() {
        this.container = document.getElementById('toastContainer');
    }

    show(message, type = 'success', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type} animate-fade-up`;
        
        const icon = {
            success: '✓',
            error: '✕',
            warning: '⚠'
        }[type] || 'ℹ';
        
        toast.innerHTML = `
            <span style="font-size: 1.1rem;">${icon}</span>
            <span>${message}</span>
        `;
        
        this.container.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('toast-removing');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

const toast = new ToastManager();
window.toast = toast;

// =====================================================
// LOCAL TIME FORMATTING
// =====================================================

window.AuthFlow = window.AuthFlow || {};

window.AuthFlow.formatLocalTime = function formatLocalTime(value, format = 'datetime') {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';

    if (format === 'time') {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    if (format === 'short-date') {
        const today = new Date();
        const sameDay = date.getFullYear() === today.getFullYear()
            && date.getMonth() === today.getMonth()
            && date.getDate() === today.getDate();
        if (sameDay) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }

    return date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
};

window.AuthFlow.formatLocalTimes = function formatLocalTimes(root = document) {
    root.querySelectorAll('.js-local-time[datetime]').forEach(element => {
        const formatted = window.AuthFlow.formatLocalTime(element.getAttribute('datetime'), element.dataset.format || 'datetime');
        if (formatted) element.textContent = formatted;
    });
};

// =====================================================
// FORM VALIDATION
// =====================================================

class FormValidator {
    constructor(formElement) {
        this.form = formElement;
        this.errors = {};
    }

    validateEmail(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
    }

    validatePassword(password) {
        return password.length >= 8;
    }

    validateRequired(value) {
        return value.trim().length > 0;
    }

    showError(inputElement, message) {
        const wrapper = inputElement.closest('.form-group');
        const errorElement = wrapper.querySelector('.error-message');
        
        inputElement.classList.add('error');
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.classList.add('visible');
        }
    }

    clearError(inputElement) {
        const wrapper = inputElement.closest('.form-group');
        const errorElement = wrapper.querySelector('.error-message');
        
        inputElement.classList.remove('error');
        if (errorElement) {
            errorElement.classList.remove('visible');
        }
    }

    clearAllErrors() {
        this.form.querySelectorAll('.form-input.error').forEach(input => {
            this.clearError(input);
        });
    }
}

// =====================================================
// PASSWORD STRENGTH CHECKER
// =====================================================

class PasswordStrengthChecker {
    constructor(passwordInput) {
        this.input = passwordInput;
        this.init();
    }

    init() {
        const wrapper = this.input.closest('.form-group');
        
        // Create strength indicator
        const strengthDiv = document.createElement('div');
        strengthDiv.className = 'password-strength';
        strengthDiv.innerHTML = '<div class="strength-bar"></div>';
        
        const strengthText = document.createElement('div');
        strengthText.className = 'strength-text';
        
        wrapper.appendChild(strengthDiv);
        wrapper.appendChild(strengthText);
        
        this.bar = strengthDiv.querySelector('.strength-bar');
        this.text = strengthText;
        
        this.input.addEventListener('input', () => this.checkStrength());
    }

    checkStrength() {
        const password = this.input.value;
        let strength = 0;
        
        if (password.length >= 8) strength++;
        if (password.match(/[a-z]/) && password.match(/[A-Z]/)) strength++;
        if (password.match(/[0-9]/)) strength++;
        if (password.match(/[^a-zA-Z0-9]/)) strength++;
        
        this.bar.className = 'strength-bar';
        
        if (password.length === 0) {
            this.bar.style.width = '0';
            this.text.textContent = '';
        } else if (strength <= 1) {
            this.bar.classList.add('strength-weak');
            this.text.textContent = 'Weak password';
            this.text.style.color = 'var(--error)';
        } else if (strength <= 2) {
            this.bar.classList.add('strength-medium');
            this.text.textContent = 'Medium password';
            this.text.style.color = 'var(--warning)';
        } else {
            this.bar.classList.add('strength-strong');
            this.text.textContent = 'Strong password';
            this.text.style.color = 'var(--success)';
        }
    }
}

// =====================================================
// PASSWORD TOGGLE
// =====================================================

class PasswordToggle {
    constructor(toggleButton) {
        this.button = toggleButton;
        this.input = this.button.parentElement.querySelector('input');
        this.init();
    }

    init() {
        this.button.addEventListener('click', () => this.toggle());
    }

    toggle() {
        const type = this.input.type === 'password' ? 'text' : 'password';
        this.input.type = type;
        
        // Toggle icon
        const icon = this.button.querySelector('svg');
        if (type === 'text') {
            icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>';
        } else {
            icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
        }
    }
}

// =====================================================
// BUTTON LOADING STATE
// =====================================================

class ButtonLoader {
    static setLoading(button) {
        button.classList.add('btn-loading');
        button.disabled = true;
        
        const spinner = document.createElement('span');
        spinner.className = 'spinner';
        button.appendChild(spinner);
    }

    static removeLoading(button) {
        button.classList.remove('btn-loading');
        button.disabled = false;
        
        const spinner = button.querySelector('.spinner');
        if (spinner) spinner.remove();
    }
}

// =====================================================
// INITIALIZATION
// =====================================================

document.addEventListener('DOMContentLoaded', () => {
    window.AuthFlow.formatLocalTimes();

    // Initialize password toggles
    document.querySelectorAll('.password-toggle').forEach(button => {
        new PasswordToggle(button);
    });
    
    // Initialize password strength checkers
    document.querySelectorAll('input[type="password"]').forEach(input => {
        if (input.closest('.auth-card')) {
            new PasswordStrengthChecker(input);
        }
    });
});

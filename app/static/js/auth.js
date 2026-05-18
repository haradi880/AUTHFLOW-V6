// =====================================================
// AUTH FORM HANDLERS
// =====================================================

class AuthForm {
    constructor(formElement) {
        this.form = formElement;
        this.validator = new FormValidator(formElement);
        this.submitButton = formElement.querySelector('button[type="submit"]');
        this.init();
    }

    init() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Real-time validation
        this.form.querySelectorAll('.form-input').forEach(input => {
            input.addEventListener('input', () => this.validateField(input));
            input.addEventListener('blur', () => this.validateField(input));
        });
    }

    validateField(input) {
        this.validator.clearError(input);
        
        if (input.required && !input.value.trim()) {
            this.validator.showError(input, 'This field is required');
            return false;
        }
        
        if (input.type === 'email' && input.value) {
            if (!this.validator.validateEmail(input.value)) {
                this.validator.showError(input, 'Please enter a valid email');
                return false;
            }
        }
        
        if (input.type === 'password' && input.value) {
            if (!this.validator.validatePassword(input.value)) {
                this.validator.showError(input, 'Password must be at least 8 characters');
                return false;
            }
        }
        
        return true;
    }

    handleSubmit(e) {
        this.validator.clearAllErrors();
        
        // Validate all fields
        let isValid = true;
        this.form.querySelectorAll('.form-input').forEach(input => {
            if (!this.validateField(input)) {
                isValid = false;
            }
        });
        
        if (!isValid) {
            e.preventDefault();
            return;
        }

        ButtonLoader.setLoading(this.submitButton);
    }
}

// =====================================================
// OTP INPUT HANDLER
// =====================================================

class OTPInput {
    constructor(container) {
        this.container = container;
        this.inputs = container.querySelectorAll('.otp-input');
        this.init();
    }

    init() {
        this.inputs.forEach((input, index) => {
            input.addEventListener('input', (e) => {
                if (e.target.value.length === 1 && index < this.inputs.length - 1) {
                    this.inputs[index + 1].focus();
                }
            });
            
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace' && !e.target.value && index > 0) {
                    this.inputs[index - 1].focus();
                }
            });
            
            input.addEventListener('paste', (e) => {
                e.preventDefault();
                const paste = (e.clipboardData || window.clipboardData).getData('text');
                const digits = paste.replace(/\D/g, '').split('');
                
                this.inputs.forEach((input, i) => {
                    if (digits[i]) {
                        input.value = digits[i];
                    }
                });
            });
        });
    }

    getOTP() {
        return Array.from(this.inputs).map(input => input.value).join('');
    }
}

// =====================================================
// INITIALIZATION
// =====================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize auth forms
    document.querySelectorAll('.auth-card form').forEach(form => {
        new AuthForm(form);
    });
    
    // Initialize OTP inputs
    const otpContainer = document.querySelector('.otp-group');
    if (otpContainer) {
        new OTPInput(otpContainer);
    }
});

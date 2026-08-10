// Custom Toast Notification System
class Toast {
    static show(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        else if (type === 'error') icon = 'fa-exclamation-circle';
        else if (type === 'warning') icon = 'fa-exclamation-triangle';

        toast.innerHTML = `
            <i class="fa-solid ${icon} toast-icon"></i>
            <div class="toast-content">${message}</div>
        `;

        container.appendChild(toast);
        
        // Trigger transition
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Auto dismiss
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 400);
        }, 4000);
    }
}

// Global Auth State
let currentIdentifier = '';

function switchStep(targetStepId) {
    document.querySelectorAll('.auth-step').forEach(step => {
        step.classList.remove('active');
    });
    const targetStep = document.getElementById(targetStepId);
    if (targetStep) {
        targetStep.classList.add('active');
    }
}

function goBackToIdentifier() {
    switchStep('step-identifier');
}

// Handle Phase 1: Identifier check
async function handleIdentifierSubmit(event) {
    event.preventDefault();
    const identifierInput = document.getElementById('auth-identifier');
    const value = identifierInput.value.trim();
    if (!value) return;

    currentIdentifier = value;

    try {
        const response = await fetch('/api/auth/check-user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: value })
        });
        const data = await response.json();

        if (response.ok) {
            if (data.exists) {
                // User exists: slide to login (password entry)
                document.getElementById('login-user-display').textContent = data.username;
                document.getElementById('login-password').value = '';
                switchStep('step-login');
                Toast.show(`Welcome back, ${data.username}! Please enter your password.`, 'success');
            } else {
                // User not found: slide to registration
                const signupUser = document.getElementById('signup-username');
                const signupEmail = document.getElementById('signup-email');
                
                signupUser.value = '';
                signupEmail.value = '';
                
                // Pre-fill email or username based on input format
                if (value.includes('@')) {
                    signupEmail.value = value;
                } else {
                    signupUser.value = value;
                }
                
                document.getElementById('signup-password').value = '';
                document.getElementById('signup-confirm-password').value = '';
                switchStep('step-signup');
                Toast.show("Account not found. Let's create one for you!", 'info');
            }
        } else {
            Toast.show(data.error || "An error occurred. Please try again.", "error");
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection failed.", "error");
    }
}

// Handle Phase 2: Login Submission
async function handleLoginSubmit(event) {
    event.preventDefault();
    const password = document.getElementById('login-password').value;
    if (!password) return;

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: currentIdentifier, password: password })
        });
        const data = await response.json();

        if (response.ok) {
            Toast.show("Login successful! Redirecting...", "success");
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            if (response.status === 404 && data.mode_switch === "signup") {
                Toast.show(data.error || "No account found. Create one.", "warning");
                // Pre-fill signup identifier
                const signupUser = document.getElementById('signup-username');
                const signupEmail = document.getElementById('signup-email');
                signupUser.value = '';
                signupEmail.value = '';
                if (currentIdentifier.includes('@')) {
                    signupEmail.value = currentIdentifier;
                } else {
                    signupUser.value = currentIdentifier;
                }
                switchStep('step-signup');
            } else {
                Toast.show(data.error || "Invalid password.", "error");
            }
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection failed.", "error");
    }
}

// Handle Phase 3: Signup Submission
async function handleSignupSubmit(event) {
    event.preventDefault();
    const username = document.getElementById('signup-username').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const company = document.getElementById('signup-company').value.trim();
    const password = document.getElementById('signup-password').value;
    const confirmPassword = document.getElementById('signup-confirm-password').value;

    if (password !== confirmPassword) {
        Toast.show("Passwords do not match.", "warning");
        return;
    }

    try {
        const response = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username,
                email,
                company_name: company,
                password
            })
        });
        const data = await response.json();

        if (response.ok) {
            Toast.show("Registration complete! Switching to login...", "success");
            
            // Auto switch to login
            currentIdentifier = username;
            document.getElementById('login-user-display').textContent = username;
            document.getElementById('login-password').value = '';
            
            setTimeout(() => {
                switchStep('step-login');
            }, 1200);
        } else {
            if (response.status === 409 && data.mode_switch === "login") {
                Toast.show(data.error || "Account already exists. Please sign in.", "warning");
                currentIdentifier = username || email;
                document.getElementById('login-user-display').textContent = currentIdentifier;
                document.getElementById('login-password').value = '';
                switchStep('step-login');
            } else {
                Toast.show(data.error || "Registration failed.", "error");
            }
        }
    } catch (e) {
        console.error(e);
        Toast.show("Server connection failed.", "error");
    }
}

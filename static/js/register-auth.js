// Register Page Firebase Authentication

// Helper: complete registration with backend
async function completeBackendRegistration(token, email, uid, name, photoURL, provider, isReregistration) {
    const response = await fetch('/firebase-register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            token,
            email,
            uid,
            displayName: name,
            photoURL: photoURL || '',
            provider: provider || 'email',
            is_reregistration: isReregistration || false
        })
    });
    return response.json();
}

// Email/Password Registration
document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('nameInput').value;
    const email = document.getElementById('emailInput').value;
    const password = document.getElementById('passwordInput').value;
    const confirmPassword = document.getElementById('confirmPasswordInput').value;
    const submitBtn = document.getElementById('submitBtn');
    
    // Validate passwords match
    if (password !== confirmPassword) {
        showError('Passwords do not match!');
        return;
    }
    
    const originalText = showLoading(submitBtn);
    
    const result = await signUpWithEmail(email, password, name);
    
    if (result.success) {
        // Normal registration path
        try {
            const token = await getUserToken();
            const data = await completeBackendRegistration(token, result.user.email, result.user.uid, name);
            if (data.success) {
                showSuccess('Account created successfully! Please verify your email. Redirecting...');
                setTimeout(() => {
                    window.location.href = '/login?success=Account created! Please check your email to verify your account.';
                }, 2000);
            } else {
                hideLoading(submitBtn, originalText);
                showError(data.error || 'Registration failed. Please try again.');
            }
        } catch (error) {
            hideLoading(submitBtn, originalText);
            showError('Network error. Please try again.');
        }
    } else if (result.rawCode === 'auth/email-already-in-use') {
        // Firebase still holds this email because client-side deletion failed.
        // Check if this email was previously deleted on our backend.
        try {
            const checkRes = await fetch('/api/check-deleted-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const checkData = await checkRes.json();

            if (checkData.deleted) {
                // Re-registration allowed: sign in to get the existing Firebase account,
                // then tell the backend to treat this as a fresh account.
                const signInResult = await signInWithEmail(email, password);
                if (signInResult.success) {
                    const token = await getUserToken();
                    const data = await completeBackendRegistration(
                        token, signInResult.user.email, signInResult.user.uid, name,
                        null, 'email', true
                    );
                    if (data.success) {
                        showSuccess('Account re-created successfully! Redirecting...');
                        setTimeout(() => { window.location.href = '/dashboard'; }, 1500);
                    } else {
                        hideLoading(submitBtn, originalText);
                        showError(data.error || 'Re-registration failed. Please try again.');
                    }
                } else {
                    hideLoading(submitBtn, originalText);
                    showError('An account with this email exists. Please sign in or use a different email.');
                }
            } else {
                hideLoading(submitBtn, originalText);
                showError(result.error);
            }
        } catch (err) {
            hideLoading(submitBtn, originalText);
            showError(result.error);
        }
    } else {
        hideLoading(submitBtn, originalText);
        showError(result.error);
    }
});

// Google Sign Up
document.getElementById('googleSignUpBtn').addEventListener('click', async () => {
    const btn = document.getElementById('googleSignUpBtn');
    const originalText = showLoading(btn);
    
    const result = await signInWithGoogle();
    
    if (result.success) {
        // Get Firebase token
        const token = await getUserToken();
        
        // Send to backend to create session
        try {
            const response = await fetch('/firebase-register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    token: token,
                    email: result.user.email,
                    uid: result.user.uid,
                    displayName: result.user.displayName,
                    photoURL: result.user.photoURL,
                    provider: 'google'
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showSuccess('Account created successfully! Redirecting...');
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 1000);
            } else {
                hideLoading(btn, originalText);
                showError(data.error || 'Registration failed. Please try again.');
            }
        } catch (error) {
            hideLoading(btn, originalText);
            showError('Network error. Please try again.');
        }
    } else {
        hideLoading(btn, originalText);
        showError(result.error);
    }
});

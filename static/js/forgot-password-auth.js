// Forgot Password Page Firebase Authentication

document.getElementById('forgotPasswordForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('emailInput').value;
    const submitBtn = document.getElementById('submitBtn');
    
    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        showError('Please enter a valid email address.');
        return;
    }
    
    const originalText = showLoading(submitBtn);
    
    console.log('Attempting to send password reset email to:', email);
    
    const result = await resetPassword(email);
    
    if (result.success) {
        showSuccess('Password reset email sent! Please check your inbox (and spam folder).');
        console.log('Password reset email sent successfully');
        setTimeout(() => {
            window.location.href = '/login?success=Password reset email sent. Please check your inbox.';
        }, 2500);
    } else {
        console.error('Password reset failed:', result.error);
        hideLoading(submitBtn, originalText);
        showError(result.error);
    }
});

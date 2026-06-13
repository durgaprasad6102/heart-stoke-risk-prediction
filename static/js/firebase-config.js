// Firebase Configuration and Authentication Module

// Load Firebase configuration from .env values (passed from server)
const firebaseConfig = {
  apiKey: window.FIREBASE_CONFIG?.apiKey || "",
  authDomain: window.FIREBASE_CONFIG?.authDomain || "",
  projectId: window.FIREBASE_CONFIG?.projectId || "",
  storageBucket: window.FIREBASE_CONFIG?.storageBucket || "",
  messagingSenderId: window.FIREBASE_CONFIG?.messagingSenderId || "",
  appId: window.FIREBASE_CONFIG?.appId || "",
  measurementId: window.FIREBASE_CONFIG?.measurementId || ""
};

// Debug: Log Firebase configuration (remove in production)
console.log('Firebase Config loaded:', {
  apiKey: firebaseConfig.apiKey ? '✓ Present' : '✗ Missing',
  authDomain: firebaseConfig.authDomain,
  projectId: firebaseConfig.projectId
});

// Initialize Firebase
let app, auth;
try {
  app = firebase.initializeApp(firebaseConfig);
  auth = firebase.auth();
  console.log('✓ Firebase initialized successfully');
} catch (error) {
  console.error('✗ Firebase initialization error:', error);
  alert('Firebase configuration error. Please check console.');
}

// Google Auth Provider
const googleProvider = new firebase.auth.GoogleAuthProvider();

// Show loading state
function showLoading(button) {
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Please wait...';
    return originalText;
}

// Hide loading state
function hideLoading(button, originalText) {
    button.disabled = false;
    button.innerHTML = originalText;
}

// Show error message
function showError(message) {
    const existingError = document.querySelector('.error-message');
    if (existingError) {
        existingError.remove();
    }
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
    
    const form = document.querySelector('form');
    form.parentNode.insertBefore(errorDiv, form);
    
    // Auto-remove after 5 seconds
    setTimeout(() => errorDiv.remove(), 5000);
}

// Show success message
function showSuccess(message) {
    const existingSuccess = document.querySelector('.success-message');
    if (existingSuccess) {
        existingSuccess.remove();
    }
    
    const successDiv = document.createElement('div');
    successDiv.className = 'success-message';
    successDiv.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    
    const form = document.querySelector('form');
    form.parentNode.insertBefore(successDiv, form);
}

// Email/Password Sign In
async function signInWithEmail(email, password) {
    try {
        console.log('Attempting email sign-in for:', email);
        const userCredential = await auth.signInWithEmailAndPassword(email, password);
        console.log('Email sign-in successful');
        return { success: true, user: userCredential.user };
    } catch (error) {
        console.error('Email sign-in error:', error);
        console.error('Error code:', error.code);
        return { success: false, error: getErrorMessage(error.code) };
    }
}

// Email/Password Sign Up
async function signUpWithEmail(email, password, displayName) {
    try {
        const userCredential = await auth.createUserWithEmailAndPassword(email, password);
        
        // Update user profile with display name
        if (displayName) {
            await userCredential.user.updateProfile({
                displayName: displayName
            });
        }
        
        // Send email verification
        await userCredential.user.sendEmailVerification();
        
        return { success: true, user: userCredential.user };
    } catch (error) {
        return { success: false, error: getErrorMessage(error.code), rawCode: error.code };
    }
}

// Google Sign In
async function signInWithGoogle() {
    try {
        console.log('Attempting Google Sign-In...');
        const result = await auth.signInWithPopup(googleProvider);
        console.log('Google Sign-In successful:', result.user.email);
        return { success: true, user: result.user };
    } catch (error) {
        console.error('Google Sign-In error:', error);
        console.error('Error code:', error.code);
        console.error('Error message:', error.message);
        return { success: false, error: getErrorMessage(error.code) };
    }
}

// Password Reset
async function resetPassword(email) {
    try {
        console.log('Sending password reset email to:', email);
        await auth.sendPasswordResetEmail(email, {
            url: window.location.origin + '/login',
            handleCodeInApp: false
        });
        console.log('Password reset email sent successfully');
        return { success: true };
    } catch (error) {
        console.error('Password reset error:', error);
        console.error('Error code:', error.code);
        console.error('Error message:', error.message);
        return { success: false, error: getErrorMessage(error.code) };
    }
}

// Sign Out
async function signOut() {
    try {
        await auth.signOut();
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// Get current user
function getCurrentUser() {
    return auth.currentUser;
}

// Get user token
async function getUserToken() {
    const user = getCurrentUser();
    if (user) {
        return await user.getIdToken();
    }
    return null;
}

// Convert Firebase error codes to user-friendly messages
function getErrorMessage(errorCode) {
    const errorMessages = {
        'auth/email-already-in-use': 'This email is already registered. Please sign in instead.',
        'auth/invalid-email': 'Please enter a valid email address.',
        'auth/operation-not-allowed': 'Email/password accounts are not enabled. Please contact support.',
        'auth/weak-password': 'Password should be at least 6 characters long.',
        'auth/user-disabled': 'This account has been disabled. Please contact support.',
        'auth/user-not-found': 'No account found with this email. Please sign up first.',
        'auth/wrong-password': 'Incorrect password. Please try again.',
        'auth/invalid-credential': 'Invalid email or password. Please try again.',
        'auth/too-many-requests': 'Too many failed attempts. Please try again later.',
        'auth/network-request-failed': 'Network error. Please check your connection.',
        'auth/popup-closed-by-user': 'Sign-in popup was closed. Please try again.',
        'auth/cancelled-popup-request': 'Sign-in was cancelled.',
        'auth/popup-blocked': 'Popup was blocked by your browser. Please allow popups and try again.',
        'auth/account-exists-with-different-credential': 'An account already exists with the same email but different sign-in credentials.',
        'auth/invalid-action-code': 'The password reset link is invalid or has expired. Please request a new one.',
        'auth/expired-action-code': 'The password reset link has expired. Please request a new one.',
        'auth/missing-email': 'Please enter your email address.',
        'auth/requires-recent-login': 'This operation requires recent authentication. Please sign in again.'
    };
    
    return errorMessages[errorCode] || 'An error occurred. Please try again.';
}

// Monitor authentication state
auth.onAuthStateChanged((user) => {
    if (user) {
        console.log('User is signed in:', user.email);
        // Store user info in sessionStorage for backend
        sessionStorage.setItem('firebaseUser', JSON.stringify({
            uid: user.uid,
            email: user.email,
            displayName: user.displayName,
            emailVerified: user.emailVerified,
            photoURL: user.photoURL
        }));
    } else {
        console.log('User is signed out');
        sessionStorage.removeItem('firebaseUser');
    }
});

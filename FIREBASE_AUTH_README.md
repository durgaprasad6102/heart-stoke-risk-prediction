# Firebase Authentication Setup Guide

## Overview
Your Stroke Prediction application now has Firebase Authentication integrated with:
- ✅ Email/Password login and registration
- ✅ Google Sign-In
- ✅ Forgot Password functionality (Password Reset Email)

## Setup Instructions

### 1. Install Dependencies
Run the following command to install the required packages:
```bash
pip install -r requirements.txt
```

### 2. Firebase Configuration
Your Firebase configuration is already set up in the `.env` file with the following values:
- API Key: AIzaSyCkfNQA5LbXAQQKWciaOhikhpELVMpABKU
- Auth Domain: stroke-prediction-c7251.firebaseapp.com
- Project ID: stroke-prediction-c7251
- Storage Bucket: stroke-prediction-c7251.firebasestorage.app
- Messaging Sender ID: 306603973731
- App ID: 1:306603973731:web:598c07dcfa7a6b090cac56

### 3. Firebase Authentication Settings
Make sure your Firebase project has the following authentication methods enabled:
- [x] Email/Password
- [x] Google Sign-In

## How It Works

### Frontend (Client-Side)
1. **Firebase SDK**: Uses Firebase JavaScript SDK (v9.22.0) for authentication
2. **Authentication Functions**: Located in `/static/js/firebase-config.js`
3. **Page-Specific Scripts**:
   - `/static/js/register-auth.js` - Registration logic
   - `/static/js/forgot-password-auth.js` - Password reset logic

### Backend (Server-Side) 
1. **Flask Routes**: New Firebase routes added in `app.py`
   - `/firebase-login` - Handles Firebase login
   - `/firebase-register` - Handles Firebase registration
2. **Session Management**: Creates Flask sessions after Firebase authentication
3. **User Storage**: Stores user data in local JSON files for app-specific data

## Features

### 1. Email/Password Authentication
- Users can register with email and password
- Minimum 6 characters for password
- Email verification sent automatically
- Login with email and password

### 2. Google Sign-In
- One-click Google authentication
- Automatically creates user account
- No password needed

### 3. Forgot Password
- Users enter their email address
- Firebase sends a password reset link
- User can reset password via email link
- Secure and Firebase-managed

## Usage

### Starting the Application
```bash
python app.py
```

### User Flow
1. **New Users**:
   - Click "Create account" on login page
   - Fill in name, email, and password
   - OR click "Sign up with Google"
   - Verify email (for email/password users)
   - Log in to access dashboard

2. **Existing Users**:
   - Enter email and password
   - OR click "Sign in with Google"
   - Access dashboard

3. **Forgot Password**:
   - Click "Forgot password?" on login page
   - Enter email address
   - Check email for reset link
   - Click link and set new password
   - Log in with new password

## File Structure
```
.
├── app.py                          # Main Flask application with Firebase routes
├── .env                            # Firebase configuration (DO NOT COMMIT TO GIT!)
├── requirements.txt                # Python dependencies including Firebase
├── static/
│   └── js/
│       ├── firebase-config.js       # Firebase initialization and auth functions
│       ├── register-auth.js         # Registration page logic
│       └── forgot-password-auth.js  # Password reset logic
└── templates/
    ├── login.html                  # Login page with Firebase auth
    ├── register.html               # Registration page with Firebase auth
    └── forgot_password.html        # Password reset page
```

## Security Notes

### Important Security Recommendations
1. **Environment Variables**: Never commit `.env` file to version control
2. **API Keys**: While Firebase API keys can be public, consider adding domain restrictions in Firebase Console
3. **Service Account**: For production, set up Firebase Admin SDK with service account credentials
4. **HTTPS**: Always use HTTPS in production
5. **Session Security**: Update `app.secret_key` in production to a strong, random value

### Firebase Console Security Settings
1. Go to Firebase Console → Authentication → Settings
2. Set authorized domains (add your production domain)
3. Enable email enumeration protection
4. Set up email templates for verification and password reset

## Troubleshooting

### Common Issues

**Issue**: Firebase scripts not loading
- **Solution**: Check internet connection and ensure CDN links are accessible

**Issue**: Google Sign-In not working
- **Solution**: Verify Google Sign-In is enabled in Firebase Console

**Issue**: Password reset emails not sending
- **Solution**: Check Firebase Console → Authentication → Templates and verify email configuration

**Issue**: "Firebase app not initialized" error
- **Solution**: Ensure Firebase config is properly passed to templates and scripts load in correct order

### Error Messages
- `Invalid email or password` - Check credentials or verify email first
- `Email already in use` - User already registered, use login instead
- `Too many requests` - Firebase rate limiting, wait a few minutes
- `Network error` - Check internet connection

## Testing

### Test User Credentials
- **Admin User** (legacy JSON auth):
  - Username: admin
  - Password: admin@!23

### Creating Test Firebase Users
1. Use the registration page to create test accounts
2. Or use Firebase Console → Authentication → Users → Add User

## Next Steps

### Recommended Enhancements
1. **Email Verification Enforcement**: Require users to verify email before accessing dashboard
2. **Profile Management**: Allow users to update profile and change password
3. **Two-Factor Authentication**: Add 2FA for enhanced security
4. **Social Logins**: Add more providers (Facebook, Twitter, GitHub, etc.)
5. **Password Strength Meter**: Show password strength during registration
6. **Remember Me**: Add persistent login option
7. **Activity Logs**: Track login history and suspicious activity

### Firebase Admin SDK Setup (Optional)
For server-side token verification:
1. Download service account JSON from Firebase Console
2. Update app.py to initialize Firebase Admin properly
3. Add token verification in authentication routes

## Support
For issues or questions:
1. Check Firebase documentation: https://firebase.google.com/docs/auth
2. Review Flask documentation: https://flask.palletsprojects.com/
3. Check browser console for JavaScript errors
4. Review server logs for backend errors

## License
This application uses Firebase Authentication which is subject to Google's terms of service.

"""
Stroke Prediction Web Application
Flask backend with Authentication, History, Food Recommendations, and Medication Reminders
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
import joblib
import pandas as pd
import numpy as np
import os
import json
import io
from datetime import datetime
from functools import wraps
import re
from fpdf import FPDF
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'stroke_prediction_secret_key_2024'

# Firebase configuration from environment variables
FIREBASE_CONFIG = {
    'api_key': os.getenv('NEXT_PUBLIC_FIREBASE_API_KEY', '').strip(),
    'auth_domain': os.getenv('NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN', '').strip(),
    'project_id': os.getenv('NEXT_PUBLIC_FIREBASE_PROJECT_ID', '').strip(),
    'storage_bucket': os.getenv('NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET', '').strip(),
    'messaging_sender_id': os.getenv('NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID', '').strip(),
    'app_id': os.getenv('NEXT_PUBLIC_FIREBASE_APP_ID', '').strip(),
    'measurement_id': os.getenv('NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID', '').strip()
}

# Debug Firebase config (remove in production)
print("Firebase Config loaded:")
print(f"  API Key: {'✓ Present' if FIREBASE_CONFIG['api_key'] else '✗ Missing'}")
print(f"  Auth Domain: {FIREBASE_CONFIG['auth_domain']}")
print(f"  Project ID: {FIREBASE_CONFIG['project_id']}")

# Email configuration from environment variables
EMAIL_CONFIG = {
    'sender': os.getenv('EMAIL_SENDER', '').strip(),
    'password': os.getenv('EMAIL_PASSWORD', '').strip(),
    'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com').strip(),
    'smtp_port': int(os.getenv('SMTP_PORT', '587'))
}

print("\nEmail Config loaded:")
print(f"  Sender: {'✓ Present' if EMAIL_CONFIG['sender'] else '✗ Missing'}")
print(f"  SMTP Server: {EMAIL_CONFIG['smtp_server']}:{EMAIL_CONFIG['smtp_port']}")

# Initialize Firebase Admin SDK (for server-side verification)
try:
    # Using default credentials or application default
    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": FIREBASE_CONFIG['project_id'],
            # For production, use a proper service account JSON file
            # For now, we'll use client-side authentication only
        })
except Exception as e:
    print(f"Firebase Admin initialization skipped: {e}")
    print("Using client-side Firebase authentication only")

# File paths for JSON storage
DATA_PATH = 'data'
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
RESULTS_FILE = os.path.join(DATA_PATH, 'results.json')
MEDICATIONS_FILE = os.path.join(DATA_PATH, 'medications.json')
DOCTOR_ADVICE_FILE = os.path.join(DATA_PATH, 'doctor_advice_history.json')

# Create data directory if not exists
if not os.path.exists(DATA_PATH):
    os.makedirs(DATA_PATH)

# Initialize JSON files if they don't exist
def init_json_files():
    # Initialize users file as empty (all auth is Firebase-only)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({}, f, indent=4)
    
    if not os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'w') as f:
            json.dump({}, f)
    
    if not os.path.exists(MEDICATIONS_FILE):
        with open(MEDICATIONS_FILE, 'w') as f:
            json.dump({}, f)

    if not os.path.exists(DOCTOR_ADVICE_FILE):
        with open(DOCTOR_ADVICE_FILE, 'w') as f:
            json.dump({}, f)

init_json_files()

# Helper function to remove emojis and special Unicode characters for PDF
def remove_emojis(text):
    """Remove emojis and non-latin characters from text for PDF compatibility"""
    # Remove emojis and other unicode symbols
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        u"\U0001FA00-\U0001FA6F"  # Chess Symbols
        u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        u"\U00002600-\U000026FF"  # Miscellaneous Symbols
        u"\U00002B50"  # star
        u"\U0001F004"  # mahjong
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub('', text)
    # Remove any remaining non-ASCII characters except common punctuation
    text = text.encode('ascii', 'ignore').decode('ascii')
    # Clean up extra spaces
    text = ' '.join(text.split())
    return text.strip()

# Load models at startup
MODEL_PATH = 'saved_models'

try:
    model_A = joblib.load(os.path.join(MODEL_PATH, 'stroke_model_A_original.pkl'))
    model_B = joblib.load(os.path.join(MODEL_PATH, 'stroke_model_B_synthetic.pkl'))
    feature_info = joblib.load(os.path.join(MODEL_PATH, 'feature_info.pkl'))
    print("✅ Models loaded successfully!")
except Exception as e:
    print(f"❌ Error loading models: {e}")
    model_A = None
    model_B = None
    feature_info = None

# Helper functions for JSON operations
def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def load_results():
    with open(RESULTS_FILE, 'r') as f:
        return json.load(f)

def save_results(results):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=4)

def load_medications():
    with open(MEDICATIONS_FILE, 'r') as f:
        return json.load(f)

def save_medications(medications):
    with open(MEDICATIONS_FILE, 'w') as f:
        json.dump(medications, f, indent=4)

def load_doctor_advice():
    if not os.path.exists(DOCTOR_ADVICE_FILE):
        return {}
    with open(DOCTOR_ADVICE_FILE, 'r') as f:
        return json.load(f)

def save_doctor_advice(data):
    with open(DOCTOR_ADVICE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Email notification functions
def send_email(recipient_email, subject, body):
    """Send email notification"""
    try:
        if not EMAIL_CONFIG['sender'] or not EMAIL_CONFIG['password']:
            print("⚠️ Email not configured. Skipping email notification.")
            print(f"   Sender: {EMAIL_CONFIG['sender']}")
            print(f"   Password: {'***' if EMAIL_CONFIG['password'] else 'Not set'}")
            return False
        
        print(f"\n📧 Attempting to send email:")
        print(f"   From: {EMAIL_CONFIG['sender']}")
        print(f"   To: {recipient_email}")
        print(f"   Subject: {subject}")
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG['sender']
        msg['To'] = recipient_email
        
        # Add HTML and plain text versions
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #0EA5E9; border-bottom: 2px solid #0EA5E9; padding-bottom: 10px;">
                        🏥 Stroke Risk Prediction System
                    </h2>
                    {body}
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="color: #666; font-size: 12px; text-align: center;">
                        This is an automated notification from the Stroke Risk Prediction System.
                    </p>
                </div>
            </body>
        </html>
        """
        
        # Attach both versions
        msg.attach(MIMEText(body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        print(f"   Connecting to {EMAIL_CONFIG['smtp_server']}:{EMAIL_CONFIG['smtp_port']}...")
        
        # Send email
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'], timeout=10) as server:
            server.starttls()
            print(f"   Logging in as {EMAIL_CONFIG['sender']}...")
            server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['password'])
            print(f"   Sending message...")
            server.send_message(msg)
        
        print(f"✅ Email sent successfully to {recipient_email}\n")
        return True
    
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {e}")
        print(f"   Check your email and password in .env file")
        print(f"   Gmail users: Use an App Password, not your regular password")
        print(f"   Get one at: https://myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"❌ Failed to send email to {recipient_email}: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_login_notification(user_email, user_name):
    """Send email when user logs in"""
    subject = "🔐 Login Alert - Stroke Risk Prediction System"
    body = f"""
    <p style="font-size: 16px;">Hello <strong>{user_name}</strong>,</p>
    <p>We detected a login to your account on the <strong>Stroke Risk Prediction System</strong>.</p>
    <div style="background-color: #f0f9ff; padding: 15px; border-left: 4px solid #0EA5E9; margin: 20px 0;">
        <p style="margin: 5px 0;"><strong>Login Time:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        <p style="margin: 5px 0;"><strong>Account:</strong> {user_email}</p>
    </div>
    <p>If this wasn't you, please secure your account immediately.</p>
    <p style="margin-top: 20px;">Stay healthy! 💙</p>
    """
    return send_email(user_email, subject, body)

def send_medication_reminder(user_email, user_name, medication_name, time_slot):
    """Send medication reminder email"""
    subject = "💊 Medication Reminder - Take Your Medicine!"
    body = f"""
    <p style="font-size: 16px;">Hello <strong>{user_name}</strong>,</p>
    <div style="background-color: #fef3c7; padding: 20px; border-left: 4px solid #f59e0b; margin: 20px 0; border-radius: 5px;">
        <h3 style="color: #f59e0b; margin-top: 0;">⏰ Medication Alert</h3>
        <p style="font-size: 18px; margin: 10px 0;">
            <strong>Medication:</strong> {medication_name}
        </p>
        <p style="font-size: 16px; margin: 10px 0;">
            <strong>Scheduled Time:</strong> {time_slot.capitalize()}
        </p>
        <p style="font-size: 16px; margin: 10px 0;">
            <strong>Current Time:</strong> {datetime.now().strftime('%I:%M %p')}
        </p>
    </div>
    <p style="font-size: 16px;">⚠️ You haven't marked this medication as taken yet.</p>
    <p style="font-size: 14px; color: #666;">Please take your medication as prescribed and mark it as completed in the system.</p>
    <p style="margin-top: 20px;">Your health is important! 💙</p>
    """
    return send_email(user_email, subject, body)

def check_medication_reminders():
    """Check for overdue medications and send reminders"""
    try:
        medications = load_medications()
        users = load_users()
        current_time = datetime.now()
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        print(f"\n⏰ [SCHEDULER] Checking medications at {current_time.strftime('%H:%M:%S')}")
        
        for username, user_meds in medications.items():
            # Get user's email
            if username not in users:
                print(f"   ⚠️ User {username} not found in users.json")
                continue
            
            user = users[username]
            user_email = user.get('email')
            user_name = user.get('name', username)
            
            if not user_email:
                print(f"   ⚠️ No email for user {username}")
                continue
            
            print(f"   👤 Checking {len(user_meds)} medications for {user_name} ({user_email})")
            
            # Check each medication
            for med in user_meds:
                medication_name = med.get('tablet_name', 'Medication')
                schedule = med.get('schedule', [])
                
                for slot in schedule:
                    # Skip if already taken
                    if slot.get('taken', False):
                        continue
                    
                    # Get scheduled time
                    slot_time = slot.get('time', '')
                    slot_name = slot.get('slot', 'unknown')
                    
                    if not slot_time:
                        continue
                    
                    try:
                        # Parse scheduled time (format: "HH:MM")
                        scheduled_hour, scheduled_minute = map(int, slot_time.split(':'))
                        
                        # Calculate time difference in minutes
                        time_diff = (current_hour * 60 + current_minute) - (scheduled_hour * 60 + scheduled_minute)
                        
                        print(f"      💊 {medication_name} ({slot_name}) - Scheduled: {slot_time}, Time diff: {time_diff} min")
                        
                        # Get last alert time (if any)
                        last_alert = slot.get('last_alert_sent')
                        alert_count = slot.get('alert_count', 0)
                        needs_save = False
                        
                        # Send immediate alert when overdue (0-15 minutes after scheduled time)
                        if 0 <= time_diff <= 15 and alert_count == 0:
                            print(f"         📧 [IMMEDIATE] Sending to {user_email}")
                            result = send_medication_reminder(user_email, user_name, medication_name, slot_name)
                            if result:
                                slot['last_alert_sent'] = current_time.isoformat()
                                slot['alert_count'] = 1
                                needs_save = True
                        
                        # Send 2-hour overdue alert (120+ minutes late)
                        elif time_diff >= 120 and alert_count < 2:
                            print(f"         📧 [2 HOURS OVERDUE] Sending urgent reminder to {user_email}")
                            subject = "⚠️ URGENT: Medication 2+ Hours Overdue!"
                            body = f"""
                                <p style="font-size: 16px;">Hello <strong>{user_name}</strong>,</p>
                                <div style="background-color: #fee2e2; padding: 20px; border-left: 4px solid #ef4444; margin: 20px 0; border-radius: 5px;">
                                    <h3 style="color: #dc2626; margin-top: 0;">🚨 URGENT MEDICATION ALERT</h3>
                                    <p style="font-size: 18px; margin: 10px 0;">
                                        <strong>Medication:</strong> {medication_name}
                                    </p>
                                    <p style="font-size: 16px; margin: 10px 0;">
                                        <strong>Scheduled Time:</strong> {slot_time} ({slot_name.capitalize()})
                                    </p>
                                    <p style="font-size: 16px; margin: 10px 0;">
                                        <strong>Time Overdue:</strong> {time_diff // 60} hours {time_diff % 60} minutes
                                    </p>
                                </div>
                                <p style="font-size: 16px; color: #dc2626; font-weight: bold;">⚠️ This medication is MORE THAN 2 HOURS OVERDUE!</p>
                                <p style="font-size: 14px; color: #666;">Please take your medication immediately and consult your doctor if you have concerns.</p>
                                <p style="margin-top: 20px;">Your health is critical! 🏥</p>
                                """
                            result = send_email(user_email, subject, body)
                            if result:
                                slot['last_alert_sent'] = current_time.isoformat()
                                slot['alert_count'] = 2
                                needs_save = True
                        
                        # Save if alerts were sent
                        if needs_save:
                            save_medications(medications)
                    
                    except ValueError as e:
                        print(f"      ⚠️ Invalid time format for medication: {slot_time}")
                        continue
    
    except Exception as e:
        print(f"❌ Error checking medication reminders: {e}")
        import traceback
        traceback.print_exc()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Food recommendations based on risk factors
def get_food_recommendations(data, risk_level):
    recommendations = {
        'foods_to_eat': [],
        'foods_to_avoid': [],
        'general_advice': [],
        'urgent_message': None
    }
    
    glucose = float(data.get('avg_glucose_level', 100))
    bmi = float(data.get('bmi', 25))
    hypertension = int(data.get('hypertension', 0))
    heart_disease = int(data.get('heart_disease', 0))
    
    # High Risk - Urgent
    if risk_level == 'HIGH':
        recommendations['urgent_message'] = "⚠️ URGENT: Please consult a doctor immediately! Your stroke risk is high."
    
    # Glucose-based recommendations
    if glucose > 126:  # High glucose (diabetic range)
        recommendations['foods_to_eat'].extend([
            "🥬 Leafy greens (spinach, kale, broccoli)",
            "🫘 Legumes (lentils, chickpeas, beans)",
            "🥜 Nuts (almonds, walnuts)",
            "🐟 Fatty fish (salmon, mackerel)",
            "🫐 Berries (blueberries, strawberries)",
            "🥑 Avocados",
            "🍳 Eggs"
        ])
        recommendations['foods_to_avoid'].extend([
            "🍬 Sugary drinks and sodas",
            "🍰 Processed desserts and sweets",
            "🍞 White bread and refined carbs",
            "🍟 Fried foods",
            "🥤 Fruit juices with added sugar"
        ])
        recommendations['general_advice'].append("Monitor blood sugar levels regularly. Consider a low-glycemic diet.")
    elif glucose > 100:  # Pre-diabetic
        recommendations['foods_to_eat'].extend([
            "🥗 Fresh salads with olive oil",
            "🍠 Sweet potatoes",
            "🌾 Whole grains (quinoa, brown rice)",
            "🍎 Apples and citrus fruits"
        ])
        recommendations['foods_to_avoid'].extend([
            "🍭 High-sugar snacks",
            "🥐 Pastries and baked goods"
        ])
        recommendations['general_advice'].append("Your glucose is slightly elevated. Focus on fiber-rich foods.")
    
    # BMI-based recommendations
    if bmi > 30:  # Obese
        recommendations['foods_to_eat'].extend([
            "🥒 Low-calorie vegetables (cucumber, celery)",
            "🍗 Lean protein (chicken breast, turkey)",
            "🥚 Protein-rich breakfast",
            "🍵 Green tea"
        ])
        recommendations['foods_to_avoid'].extend([
            "🍔 Fast food",
            "🍕 High-calorie processed foods",
            "🍿 Buttery snacks",
            "🥓 Fatty meats"
        ])
        recommendations['general_advice'].append("Weight management is crucial. Consider portion control and regular exercise.")
    elif bmi > 25:  # Overweight
        recommendations['foods_to_eat'].extend([
            "🍲 Vegetable soups",
            "🥙 Lean wraps"
        ])
        recommendations['general_advice'].append("Moderate weight loss can significantly reduce stroke risk.")
    elif bmi < 18.5:  # Underweight
        recommendations['foods_to_eat'].extend([
            "🥜 Nut butters",
            "🥛 Full-fat dairy",
            "🍌 Bananas and dates"
        ])
        recommendations['general_advice'].append("Focus on nutrient-dense foods to gain healthy weight.")
    
    # Hypertension-based recommendations
    if hypertension:
        recommendations['foods_to_eat'].extend([
            "🍌 Potassium-rich foods (bananas, potatoes)",
            "🧄 Garlic and onions",
            "🥛 Low-fat dairy",
            "🫒 Olive oil"
        ])
        recommendations['foods_to_avoid'].extend([
            "🧂 High-sodium foods",
            "🥫 Canned soups and processed foods",
            "🥓 Processed meats (bacon, sausagppythones)",
            "🧀 High-sodium cheeses"
        ])
        recommendations['general_advice'].append("Follow a DASH diet. Limit sodium to less than 2,300mg/day.")
    
    # Heart disease-based recommendations
    if heart_disease:
        recommendations['foods_to_eat'].extend([
            "🐟 Omega-3 rich fish (2-3 times/week)",
            "🫒 Extra virgin olive oil",
            "🍷 Red wine (moderate, if approved by doctor)",
            "🥜 Unsalted nuts"
        ])
        recommendations['foods_to_avoid'].extend([
            "🥩 Red meat (limit consumption)",
            "🧈 Trans fats and saturated fats",
            "🍳 Excessive egg yolks"
        ])
        recommendations['general_advice'].append("Follow a Mediterranean-style diet. Regular cardiac check-ups are essential.")
    
    # Remove duplicates
    recommendations['foods_to_eat'] = list(set(recommendations['foods_to_eat']))
    recommendations['foods_to_avoid'] = list(set(recommendations['foods_to_avoid']))
    recommendations['general_advice'] = list(set(recommendations['general_advice']))
    
    # Add default healthy foods if lists are small
    if len(recommendations['foods_to_eat']) < 5:
        defaults = [
            "🥗 Fresh vegetables",
            "🍎 Fresh fruits",
            "💧 Plenty of water (8 glasses/day)",
            "🌾 Whole grains"
        ]
        recommendations['foods_to_eat'].extend(defaults)
    
    return recommendations


def parse_nlp_health_description(text):
    """
    Parse a free-text health description and extract numeric health values.
    Handles case-insensitive keywords and various spellings/abbreviations.
    
    Example input:
        "age 45, GlUcose 180, bmi: 27.5, blood pressure 145, heart disease yes,
         smoking smokes, gender male, married yes, work private, residence urban"
    
    Returns a dict with extracted health parameters.
    """
    import re
    result = {}
    t = text.lower()

    # ---- Numeric extractions ----
    def find_number(patterns):
        for pat in patterns:
            m = re.search(pat + r'[:\s=]+([\d]+\.?[\d]*)', t)
            if m:
                return float(m.group(1))
        return None

    age_val = find_number([r'age', r'yrs', r'years'])
    if age_val is not None:
        result['age'] = int(age_val)

    glucose_val = find_number([r'glucose', r'gluco', r'blood\s*sugar', r'sugar\s*level', r'avg[_\s]*glucose[_\s]*level'])
    if glucose_val is not None:
        result['avg_glucose_level'] = glucose_val

    bmi_val = find_number([r'bmi', r'body\s*mass\s*index'])
    if bmi_val is not None:
        result['bmi'] = bmi_val

    bp_val = find_number([r'blood[_\s]*pressure', r'bp', r'systolic', r'hypertension[_\s]*value'])
    if bp_val is not None:
        result['blood_pressure'] = bp_val
        result['hypertension'] = 1 if bp_val >= 140 else 0

    # ---- Boolean / categorical extractions ----
    # Heart disease
    if re.search(r'heart[_\s]*disease\s*[:\s=]*\s*(yes|true|1|have|has)', t):
        result['heart_disease'] = 1
    elif re.search(r'heart[_\s]*disease\s*[:\s=]*\s*(no|false|0|none)', t):
        result['heart_disease'] = 0
    elif re.search(r'heart[_\s]*disease', t):
        result['heart_disease'] = 1  # mentioned without qualifier = assume yes

    # Hypertension override (if explicitly stated)
    if re.search(r'hypertension\s*[:\s=]*\s*(yes|true|1|have|has)', t):
        result['hypertension'] = 1
        if 'blood_pressure' not in result:
            result['blood_pressure'] = 160
    elif re.search(r'hypertension\s*[:\s=]*\s*(no|false|0|none)', t) and 'hypertension' not in result:
        result['hypertension'] = 0

    # Smoking status
    if re.search(r'smok(es|ing|er)', t) and not re.search(r'(never|former|quit|ex)', t):
        result['smoking_status'] = 'smokes'
    elif re.search(r'(formerly\s*smok|former\s*smok|ex[\s\-]smok|quit\s*smok|used\s*to\s*smok)', t):
        result['smoking_status'] = 'formerly smoked'
    elif re.search(r'(never\s*smok|non[\s\-]smok|no\s*smok)', t):
        result['smoking_status'] = 'never smoked'
    elif re.search(r'smok', t):
        result['smoking_status'] = 'smokes'

    # Gender
    if re.search(r'\b(male|man|boy|mr\.?)\b', t) and not re.search(r'fe?male|woman|girl', t):
        result['gender'] = 'Male'
    elif re.search(r'\b(fe?male|woman|girl|ms\.?|mrs\.?)\b', t):
        result['gender'] = 'Female'

    # Ever married
    if re.search(r'(married|wedded|spouse|wife|husband)', t) and not re.search(r'(not\s*married|unmarried|single|never\s*married)', t):
        result['ever_married'] = 'Yes'
    elif re.search(r'(unmarried|single|not\s*married|never\s*married)', t):
        result['ever_married'] = 'No'

    # Work type
    if re.search(r'(govt|government|gov\.?\s*job)', t):
        result['work_type'] = 'Govt_job'
    elif re.search(r'self[\s\-]?employ', t):
        result['work_type'] = 'Self-employed'
    elif re.search(r'(private|pvt)', t):
        result['work_type'] = 'Private'
    elif re.search(r'(child|children|student)', t):
        result['work_type'] = 'children'
    elif re.search(r'(never\s*work|unemployed)', t):
        result['work_type'] = 'Never_worked'

    # Residence type
    if re.search(r'\b(urban|city|metro|town)\b', t):
        result['residence_type'] = 'Urban'
    elif re.search(r'\b(rural|village|countryside)\b', t):
        result['residence_type'] = 'Rural'

    return result


def get_doctor_recommendations(data):
    """
    Generate doctor recommendations based on actual blood pressure and glucose levels.
    
    Blood Pressure (mmHg): < 100 = Low, 120-160 = Medium, 180-200 = High
    Glucose (mg/dL):       < 100 = Low, 170-180 = Medium, 250-300 = High
    Combined risk = worst of the two
    """
    glucose = float(data.get('avg_glucose_level', 100))
    # Support both numeric blood_pressure and boolean hypertension flag
    blood_pressure = float(data.get('blood_pressure', 0))
    hypertension_flag = int(data.get('hypertension', 0))
    # If no numeric BP provided, estimate from flag
    # Diagnosed hypertension (flag=1) maps to stage-2 range (>=180) for conservative risk assessment
    if blood_pressure == 0:
        blood_pressure = 180 if hypertension_flag == 1 else 90

    # Determine BP risk
    if blood_pressure < 100:
        bp_risk = 'low'
    elif 120 <= blood_pressure <= 160:
        bp_risk = 'medium'
    elif blood_pressure >= 180:
        bp_risk = 'high'
    else:
        bp_risk = 'medium'  # 100-119 borderline

    # Determine Glucose risk (WHO clinical thresholds)
    # Normal: <100, Pre-diabetic/elevated: 100-139, Diabetic/high: >=140
    if glucose < 100:
        glucose_risk = 'low'
    elif glucose < 140:
        glucose_risk = 'medium'
    else:
        glucose_risk = 'high'

    # Combined = worst of the two
    risk_order = {'low': 0, 'medium': 1, 'high': 2}
    combined_risk = bp_risk if risk_order[bp_risk] >= risk_order[glucose_risk] else glucose_risk

    # Factor in smoking status — active smoking is a major stroke risk factor
    smoking_status = str(data.get('smoking_status', ''))
    risk_keys = ['low', 'medium', 'high']
    if smoking_status == 'smokes':
        # Active smoking upgrades risk by one level (low→medium, medium→high)
        current_idx = risk_order.get(combined_risk, 0)
        combined_risk = risk_keys[min(current_idx + 1, 2)]
    elif smoking_status == 'formerly smoked' and combined_risk == 'low':
        # Former smokers have elevated baseline risk
        combined_risk = 'medium'

    doctor_recommendations = {
        'risk_category': '',
        'risk_level': '',
        'consult_doctor': False,
        'consult_message': '',
        'doctor_types': [],
        'medical_advice': [],
        'indian_foods_to_eat': [],
        'indian_foods_to_avoid': [],
        'lifestyle_changes': []
    }

    if combined_risk == 'low':
        doctor_recommendations['risk_category'] = 'Low Risk'
        doctor_recommendations['risk_level'] = 'LOW'
        doctor_recommendations['consult_doctor'] = False
        doctor_recommendations['consult_message'] = 'Your health parameters look good! No urgent consultation needed, but annual check-ups are recommended.'
        doctor_recommendations['doctor_types'] = [
            {'type': 'General Physician', 'reason': 'Annual wellness check-up and preventive care', 'urgency': 'Routine (once a year)'}
        ]
        doctor_recommendations['medical_advice'] = [
            "Your glucose and blood pressure levels are within normal range",
            "Continue maintaining a healthy lifestyle",
            "Annual health check-ups are recommended"
        ]
        doctor_recommendations['indian_foods_to_eat'] = [
            "🍛 Dal (lentils) - High in protein and fiber",
            "🥬 Palak (spinach) curry",
            "🥒 Cucumber raita with low-fat curd",
            "🌾 Brown rice or multi-grain roti",
            "🥗 Mixed vegetable sabzi",
            "🍵 Herbal chai with mint/tulsi",
            "🥜 Roasted chana (chickpeas)",
            "🫘 Moong dal sprouts salad",
            "🍅 Tomato and onion salad",
            "🥥 Coconut water"
        ]
        doctor_recommendations['indian_foods_to_avoid'] = [
            "🍰 Excessive sweets (gulab jamun, jalebi, barfi)",
            "🍟 Deep-fried snacks (samosa, pakora, bhajiya)",
            "🧂 High-salt pickles and papad",
            "🥤 Sugary drinks and packaged juices"
        ]
        doctor_recommendations['lifestyle_changes'] = [
            "Practice yoga or light exercise for 30 minutes daily",
            "Maintain regular meal timings",
            "Stay hydrated with water and herbal teas",
            "Get 7-8 hours of quality sleep"
        ]
    
    # Medium Risk
    elif combined_risk == 'medium':
        doctor_recommendations['risk_category'] = 'Medium Risk'
        doctor_recommendations['risk_level'] = 'MEDIUM'
        doctor_recommendations['consult_doctor'] = True
        doctor_recommendations['consult_message'] = '⚠️ Medium risk detected. It is recommended to consult a doctor within the next 2 weeks for a thorough evaluation.'
        _medium_doctors = [
            {'type': 'General Physician / Internal Medicine', 'reason': 'Initial assessment, blood tests, BP & glucose management plan', 'urgency': 'Within 2 weeks'},
        ]
        if float(data.get('avg_glucose_level', 100)) >= 140:
            _medium_doctors.append({'type': 'Endocrinologist (Diabetes Specialist)', 'reason': 'Elevated glucose / pre-diabetic or diabetic range management', 'urgency': 'Within 4 weeks'})
        if float(data.get('blood_pressure', 0)) >= 140 or int(data.get('hypertension', 0)) == 1:
            _medium_doctors.append({'type': 'Cardiologist', 'reason': 'Blood pressure monitoring and cardiovascular risk assessment', 'urgency': 'Within 4 weeks'})
        if str(data.get('smoking_status', '')) in ('smokes', 'formerly smoked'):
            _medium_doctors.append({'type': 'Pulmonologist', 'reason': 'Lung health assessment due to smoking history', 'urgency': 'Within 6 weeks'})
        doctor_recommendations['doctor_types'] = _medium_doctors
        doctor_recommendations['medical_advice'] = [
            "⚠️ Your glucose and/or blood pressure levels indicate medium risk",
            "Schedule a consultation with your doctor within 2 weeks",
            "Regular monitoring of glucose and blood pressure is essential",
            "Consider lifestyle modifications to prevent progression",
            "Monthly medical check-ups recommended"
        ]
        doctor_recommendations['indian_foods_to_eat'] = [
            "🥬 Methi (fenugreek) sabzi - Helps control blood sugar",
            "🫘 Masoor dal, moong dal, chana dal",
            "🥒 Karela (bitter gourd) juice or sabzi",
            "🌾 Oats upma or dalia (broken wheat)",
            "🥗 Cabbage and carrot sabzi",
            "🍅 Tomato soup (low salt)",
            "🫚 Ginger and garlic in cooking",
            "🥜 Small portions of almonds and walnuts",
            "🍵 Green tea or tulsi tea",
            "🥥 Buttermilk (chaas) without salt",
            "🥕 Beetroot and carrot salad",
            "🫑 Capsicum (bell pepper) sabzi"
        ]
        doctor_recommendations['indian_foods_to_avoid'] = [
            "🍚 White rice and refined flour (maida) products",
            "🥔 Potato-based dishes (aloo paratha, aloo sabzi)",
            "🍰 All sweets and desserts (mithai, halwa, kheer)",
            "🍟 Fried foods (samosa, kachori, poori, bhatura)",
            "🧂 High-salt foods (pickles, papad, namkeen)",
            "🥓 Processed meats and sausages",
            "🧈 Ghee and butter in excess",
            "🥤 Sugary beverages and packaged juices",
            "🍞 White bread and biscuits",
            "🧀 Full-fat paneer and cheese"
        ]
        doctor_recommendations['lifestyle_changes'] = [
            "Walking for 45 minutes daily (morning or evening)",
            "Practice pranayama and meditation for stress reduction",
            "Monitor blood sugar levels twice a week",
            "Reduce salt intake to less than 5g per day",
            "Avoid skipping meals - eat small frequent meals",
            "Limit screen time and ensure adequate rest",
            "Consider joining a diabetes/hypertension management program"
        ]
    
    # High Risk
    else:
        doctor_recommendations['risk_category'] = 'High Risk'
        doctor_recommendations['risk_level'] = 'HIGH'
        doctor_recommendations['consult_doctor'] = True
        doctor_recommendations['consult_message'] = '🚨 HIGH RISK: Please consult a doctor IMMEDIATELY (within 24-48 hours). Do not delay medical attention!'
        _high_doctors = [
            {'type': 'Neurologist (Stroke Specialist)', 'reason': 'Immediate stroke risk evaluation, brain imaging if needed', 'urgency': 'URGENT — within 24 hours'},
            {'type': 'Cardiologist', 'reason': 'Heart & vascular health, BP management, ECG evaluation', 'urgency': 'URGENT — within 24-48 hours'},
        ]
        if float(data.get('avg_glucose_level', 100)) >= 200:
            _high_doctors.append({'type': 'Endocrinologist (Diabetes Specialist)', 'reason': 'Critical glucose level — diabetes management & insulin therapy', 'urgency': 'Within 48 hours'})
        elif float(data.get('avg_glucose_level', 100)) >= 140:
            _high_doctors.append({'type': 'Endocrinologist (Diabetes Specialist)', 'reason': 'Elevated glucose requiring specialist management', 'urgency': 'Within 1 week'})
        if str(data.get('smoking_status', '')) == 'smokes':
            _high_doctors.append({'type': 'Pulmonologist + Smoking Cessation Clinic', 'reason': 'Active smoking dramatically increases stroke risk — immediate cessation required', 'urgency': 'Within 1 week'})
        if int(data.get('heart_disease', 0)) == 1:
            _high_doctors.append({'type': 'Interventional Cardiologist', 'reason': 'Existing heart disease combined with high stroke risk requires specialist care', 'urgency': 'Within 48 hours'})
        _high_doctors.append({'type': 'General Physician / Emergency Medicine', 'reason': 'Comprehensive health workup, blood tests, referral coordination', 'urgency': 'IMMEDIATE'})
        doctor_recommendations['doctor_types'] = _high_doctors
        doctor_recommendations['medical_advice'] = [
            "🚨 URGENT: Your glucose and/or blood pressure levels are critically high",
            "IMMEDIATE doctor consultation required - within 24-48 hours",
            "You may need medication to manage glucose and blood pressure",
            "Daily monitoring of vital parameters is mandatory",
            "Follow prescribed medication schedule strictly",
            "Consider hospitalization if symptoms worsen",
            "Weekly doctor follow-ups essential"
        ]
        doctor_recommendations['indian_foods_to_eat'] = [
            "🫘 Only dal-based proteins (masoor, moong - minimal oil)",
            "🥬 Steamed or boiled vegetables (palak, lauki, turai)",
            "🥒 Karela juice daily (bitter gourd)",
            "🫚 Ginger-garlic paste in minimal quantities",
            "🍵 Herbal teas (green tea, fenugreek tea)",
            "🥗 Raw salads (cucumber, tomato, radish)",
            "🌾 Small portions of oats or dalia",
            "🥥 Coconut water (natural, unsweetened)",
            "🫘 Sprouts (moong, chana) - steamed",
            "🥛 Skimmed milk only"
        ]
        doctor_recommendations['indian_foods_to_avoid'] = [
            "🚫 COMPLETELY AVOID all sweets and desserts",
            "🚫 NO fried foods whatsoever (pakora, samosa, poori, vada)",
            "🚫 NO white rice, potatoes, or maida products",
            "🚫 NO pickles, papad, or namkeen",
            "🚫 NO full-fat dairy products",
            "🚫 NO ghee, butter, or dalda",
            "🚫 NO sugary drinks, sodas, or packaged juices",
            "🚫 NO processed or canned foods",
            "🚫 NO red meat or organ meats",
            "🚫 NO coconut milk or heavy gravies",
            "🚫 NO bakery items (bread, biscuits, cakes)",
            "🚫 Strictly limit salt to 3g per day"
        ]
        doctor_recommendations['lifestyle_changes'] = [
            "⚠️ CRITICAL: Strict adherence to medication schedule",
            "Monitor glucose levels twice daily (fasting and post-meal)",
            "Check blood pressure twice daily",
            "Walking after every meal (even 10-15 minutes helps)",
            "Complete bed rest if advised by doctor",
            "Avoid all sources of stress - practice deep breathing",
            "Sleep 8 hours minimum, maintain regular sleep schedule",
            "Keep emergency contact numbers handy",
            "Inform family members about your condition",
            "Consider staying with family/caregivers initially"
        ]
    
    return doctor_recommendations


def get_indian_food_recommendations(data):
    """
    Get Indian food recommendations based on input health parameters
    """
    recommendations = []
    
    glucose_level = float(data.get('avg_glucose_level', 0))
    bmi = float(data.get('bmi', 0))
    hypertension = int(data.get('hypertension', 0))
    heart_disease = int(data.get('heart_disease', 0))
    age = int(data.get('age', 0))
    
    # General healthy Indian foods suitable for stroke prevention
    base_foods = [
        "🥗 Moong dal (yellow lentils) - high in protein, low in fat",
        "🍚 Brown rice or hand-pounded rice instead of white rice",
        "🥬 Palak (spinach) sabzi with minimal oil",
        "🥒 Cucumber raita with low-fat yogurt",
        "🫘 Chana dal or masoor dal preparations",
        "🌾 Ragi (finger millet) porridge or roti"
    ]
    
    # Add based on glucose levels
    if glucose_level < 100:
        recommendations.append("✅ Your glucose is good! Include: Whole moong, bajra roti, oats upma")
    elif glucose_level <= 160:
        recommendations.append("⚠️ Moderate glucose - Prefer: Sugar-free dal preparations, methi leaves, bitter gourd sabzi")
        recommendations.append("❌ Reduce: White rice, sweet dishes, refined flour items")
    else:
        recommendations.append("🚨 High glucose - Focus on: Karela juice, methi water, chana dal, avoid all sweets")
        recommendations.append("❌ Strictly avoid: Rice dishes, roti made from maida, jaggery-based foods")
    
    # Add based on BMI
    if bmi > 30:
        recommendations.append("⚖️ Weight management: Choose steamed idli, vegetable upma, avoid fried foods")
        recommendations.append("❌ Skip: All fried items (samosa, pakora, bhajiya), heavy curries with cream")
    elif bmi >= 25:
        recommendations.append("⚖️ Light meals: Khichdi, dal-rice, vegetable soups")
    
    # Add based on hypertension
    if hypertension == 1:
        recommendations.append("🩺 For BP control: Low-salt dal, jeera water, coconut water")
        recommendations.append("❌ Avoid: Pickles, papad, salted buttermilk, commercial masalas")
    
    # Add based on heart disease
    if heart_disease == 1:
        recommendations.append("❤️ Heart-healthy: Garlic chutney, flaxseed chutney, oats dosa")
        recommendations.append("❌ Avoid: Ghee, butter, coconut oil cooking, full-fat dairy")
    
    # Age-specific recommendations
    if age > 60:
        recommendations.append("👴 For seniors: Soft khichdi, dal water, vegetable soups, avoid hard-to-digest foods")
    
    # Add base foods to all
    recommendations.extend(base_foods)
    
    # General tips
    recommendations.append("💡 Cooking tips: Use minimal oil, prefer steaming/boiling, add turmeric & ginger")
    recommendations.append("🥤 Beverages: Buttermilk (low salt), herbal tea, jeera water, avoid sugary drinks")
    
    return recommendations


def prepare_features(data):
    """
    Prepare input features for prediction
    """
    # Encode categorical variables
    gender_map = {'Female': 0, 'Male': 1, 'Other': 2}
    married_map = {'No': 0, 'Yes': 1}
    work_map = {'Govt_job': 0, 'Never_worked': 1, 'Private': 2, 'Self-employed': 3, 'children': 4}
    residence_map = {'Rural': 0, 'Urban': 1}
    smoking_map = {'Unknown': 0, 'formerly smoked': 1, 'never smoked': 2, 'smokes': 3}
    
    # Extract values
    age = float(data['age'])
    gender = gender_map.get(data['gender'], 0)
    hypertension = int(data['hypertension'])
    heart_disease = int(data['heart_disease'])
    ever_married = married_map.get(data['ever_married'], 0)
    work_type = work_map.get(data['work_type'], 2)
    residence_type = residence_map.get(data['residence_type'], 1)
    avg_glucose_level = float(data['avg_glucose_level'])
    bmi = float(data['bmi'])
    smoking_status = smoking_map.get(data['smoking_status'], 0)
    
    # Feature engineering
    age_glucose_interaction = age * avg_glucose_level
    age_bmi_interaction = age * bmi
    glucose_bmi_interaction = avg_glucose_level * bmi
    
    # Age group
    if age <= 18: age_group = 0
    elif age <= 35: age_group = 1
    elif age <= 50: age_group = 2
    elif age <= 65: age_group = 3
    else: age_group = 4
    
    # BMI category
    if bmi < 18.5: bmi_category = 0
    elif bmi < 25: bmi_category = 1
    elif bmi < 30: bmi_category = 2
    else: bmi_category = 3
    
    # Glucose category
    if avg_glucose_level < 100: glucose_category = 0
    elif avg_glucose_level < 126: glucose_category = 1
    elif avg_glucose_level < 200: glucose_category = 2
    else: glucose_category = 3
    
    # Risk score (smoking is a primary stroke risk factor, include it explicitly)
    risk_score = (int(age > 50) + hypertension + heart_disease +
                  int(avg_glucose_level > 126) + int(bmi > 30) +
                  int(smoking_status == 3))  # 3 = currently smokes
    
    # Create feature DataFrame
    features = pd.DataFrame({
        'gender': [gender],
        'hypertension': [hypertension],
        'heart_disease': [heart_disease],
        'ever_married': [ever_married],
        'work_type': [work_type],
        'residence_type': [residence_type],
        'avg_glucose_level': [avg_glucose_level],
        'bmi': [bmi],
        'smoking_status': [smoking_status],
        'bmi_missing': [0],
        'age': [age],
        'age_glucose_interaction': [age_glucose_interaction],
        'age_bmi_interaction': [age_bmi_interaction],
        'glucose_bmi_interaction': [glucose_bmi_interaction],
        'age_group': [age_group],
        'bmi_category': [bmi_category],
        'glucose_category': [glucose_category],
        'risk_score': [risk_score]
    })
    
    # Reorder columns to match training data
    if feature_info:
        features = features[feature_info['feature_names']]
    
    return features


# Routes
@app.route('/')
def index():
    """Redirect to login or dashboard"""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET'])
def login():
    """Serve login page — authentication exclusively via Firebase"""
    return render_template('login.html', firebase_config=FIREBASE_CONFIG)


@app.route('/register', methods=['GET'])
def register():
    """Serve register page — registration exclusively via Firebase"""
    return render_template('register.html', firebase_config=FIREBASE_CONFIG)


@app.route('/forgot-password', methods=['GET'])
def forgot_password():
    """Serve forgot-password page — password reset exclusively via Firebase email"""
    return render_template('forgot_password.html', firebase_config=FIREBASE_CONFIG)


@app.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/firebase-debug')
def firebase_debug():
    """Debug page to check Firebase configuration"""
    return render_template('firebase_debug.html', firebase_config=FIREBASE_CONFIG)


# Firebase Authentication Routes
@app.route('/firebase-login', methods=['POST'])
def firebase_login():
    """Handle Firebase authentication login"""
    try:
        data = request.get_json()
        token = data.get('token')
        email = data.get('email')
        uid = data.get('uid')
        display_name = data.get('displayName', email)
        
        if not token or not email or not uid:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
        
        # Check if this Firebase UID has been permanently deleted/blocked
        users = load_users()
        blocked_uids = users.get('_deleted_uids', [])
        if uid in blocked_uids:
            print(f"⛔ Blocked login attempt from deleted UID: {uid}")
            return jsonify({'success': False, 'error': 'This account has been permanently deleted. Please register a new account.'}), 403
        
        # Create or update user in local database
        # Use email as username for Firebase users
        username = email.replace('@', '_').replace('.', '_')
        
        if username not in users:
            # Create new user
            users[username] = {
                'username': username,
                'email': email,
                'name': display_name,
                'role': 'user',
                'firebase_uid': uid,
                'created_at': datetime.now().isoformat(),
                'auth_provider': data.get('provider', 'email')
            }
        else:
            # Always keep firebase_uid up-to-date so account deletion works correctly
            users[username]['firebase_uid'] = uid
        save_users(users)
        
        # Create session
        session['user'] = username
        session['name'] = users[username].get('name', display_name)
        session['role'] = users[username].get('role', 'user')
        session['firebase_uid'] = uid
        
        # Send login notification email
        send_login_notification(email, display_name)
        
        return jsonify({'success': True, 'message': 'Login successful'})
    
    except Exception as e:
        print(f"Firebase login error: {e}")
        return jsonify({'success': False, 'error': 'Login failed'}), 500


@app.route('/api/check-deleted-email', methods=['POST'])
def check_deleted_email():
    """Check if an email is in the deleted-emails list (enables re-registration)"""
    try:
        data = request.get_json()
        email = data.get('email', '')
        users = load_users()
        deleted_emails = users.get('_deleted_emails', [])
        return jsonify({'deleted': email in deleted_emails})
    except Exception as e:
        return jsonify({'deleted': False}), 500


@app.route('/firebase-register', methods=['POST'])
def firebase_register():
    """Handle Firebase authentication registration"""
    try:
        data = request.get_json()
        token = data.get('token')
        email = data.get('email')
        uid = data.get('uid')
        display_name = data.get('displayName', email)
        is_reregistration = data.get('is_reregistration', False)
        
        if not token or not email or not uid:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
        
        users = load_users()
        blocked_uids = users.get('_deleted_uids', [])
        deleted_emails = users.get('_deleted_emails', [])

        # Allow re-registration when email was previously deleted
        # (Firebase account may still exist if client-side delete failed)
        if is_reregistration and email in deleted_emails:
            print(f"♻️  Re-registration allowed for previously deleted email: {email}")
            # Clean up old blocklist entries for this email
            username_key = email.replace('@', '_').replace('.', '_')
            # Remove old UID from blocklist (new Firebase UID will be different or same)
            # We allow this because the user explicitly re-registered
            if uid in blocked_uids:
                blocked_uids.remove(uid)
                users['_deleted_uids'] = blocked_uids
            # Remove from deleted_emails
            deleted_emails.remove(email)
            users['_deleted_emails'] = deleted_emails
            # Remove stale user record if it somehow still exists
            if username_key in users:
                del users[username_key]
            save_users(users)
        elif uid in blocked_uids:
            print(f"⛔ Blocked register attempt from deleted UID: {uid}")
            return jsonify({'success': False, 'error': 'This account has been permanently deleted. Please register a new account.'}), 403
        
        # Re-load after potential modifications above
        users = load_users()

        # Use email as username for Firebase users
        username = email.replace('@', '_').replace('.', '_')
        
        if username in users:
            # User already exists, just log them in
            session['user'] = username
            session['name'] = users[username].get('name', display_name)
            session['role'] = users[username].get('role', 'user')
            session['firebase_uid'] = uid
            return jsonify({'success': True, 'message': 'Login successful'})
        
        # Create new user
        users[username] = {
            'username': username,
            'email': email,
            'name': display_name,
            'role': 'user',
            'firebase_uid': uid,
            'created_at': datetime.now().isoformat(),
            'auth_provider': data.get('provider', 'email'),
            'photo_url': data.get('photoURL', '')
        }
        save_users(users)
        
        # Create session
        session['user'] = username
        session['name'] = display_name
        session['role'] = 'user'
        session['firebase_uid'] = uid
        
        return jsonify({'success': True, 'message': 'Registration successful'})
    
    except Exception as e:
        print(f"Firebase registration error: {e}")
        return jsonify({'success': False, 'error': 'Registration failed'}), 500


@app.route('/dashboard')
@login_required
def dashboard():
    """Render the main dashboard"""
    return render_template('dashboard.html', user=session.get('name', 'User'), role=session.get('role', 'user'), firebase_config=FIREBASE_CONFIG)


@app.route('/admin')
@admin_required
def admin_panel():
    """Admin panel to see all users and their history"""
    users = load_users()
    results = load_results()
    
    user_stats = []
    for username, user_data in users.items():
        # Skip internal/system keys (like _deleted_uids, _deleted_emails, etc.)
        if username.startswith('_') or not isinstance(user_data, dict):
            continue
            
        user_results = results.get(username, [])
        high_risk_count = sum(1 for r in user_results if r.get('results', {}).get('ensemble', {}).get('risk_level') == 'HIGH')
        medium_risk_count = sum(1 for r in user_results if r.get('results', {}).get('ensemble', {}).get('risk_level') == 'MEDIUM')
        low_risk_count = sum(1 for r in user_results if r.get('results', {}).get('ensemble', {}).get('risk_level') == 'LOW')
        
        latest_prediction = None
        if user_results:
            sorted_results = sorted(user_results, key=lambda x: x.get('timestamp', ''), reverse=True)
            latest_prediction = sorted_results[0]
        
        user_stats.append({
            'username': username,
            'name': user_data.get('name', username),
            'email': user_data.get('email', ''),
            'role': user_data.get('role', 'user'),
            'created_at': user_data.get('created_at', ''),
            'total_predictions': len(user_results),
            'high_risk': high_risk_count,
            'medium_risk': medium_risk_count,
            'low_risk': low_risk_count,
            'latest_prediction': latest_prediction
        })
    
    total_users = len([u for u in user_stats if u['role'] != 'admin'])
    total_predictions = sum(u['total_predictions'] for u in user_stats)
    total_high_risk = sum(u['high_risk'] for u in user_stats)
    
    return render_template('admin.html', 
                         user=session.get('name', 'User'),
                         role=session.get('role', 'user'),
                         user_stats=user_stats,
                         total_users=total_users,
                         total_predictions=total_predictions,
                         total_high_risk=total_high_risk)


@app.route('/api/admin/user-history/<username>')
@admin_required
def get_user_history(username):
    """Get prediction history for a specific user (admin only)"""
    try:
        results = load_results()
        user_results = results.get(username, [])
        user_results = sorted(user_results, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        users = load_users()
        user_data = users.get(username, {})
        
        return jsonify({
            'success': True,
            'user': {
                'username': username,
                'name': user_data.get('name', username),
                'email': user_data.get('email', '')
            },
            'results': user_results
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/admin/toggle-role', methods=['POST'])
@admin_required
def toggle_admin_role():
    """Toggle admin role for a user (admin only)"""
    try:
        data = request.get_json()
        username = data.get('username')
        new_role = data.get('new_role')
        
        if not username or not new_role:
            return jsonify({'success': False, 'error': 'Missing username or role'}), 400
        
        if new_role not in ['admin', 'user']:
            return jsonify({'success': False, 'error': 'Invalid role'}), 400
        
        if username == 'admin':
            return jsonify({'success': False, 'error': 'Cannot change admin role'}), 403
        
        users = load_users()
        
        if username not in users:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Update user role
        users[username]['role'] = new_role
        save_users(users)
        
        # Update session if toggling current user's role
        if session.get('user') == username:
            session['role'] = new_role
        
        return jsonify({
            'success': True,
            'message': f'User role updated to {new_role}',
            'username': username,
            'new_role': new_role
        })
    except Exception as e:
        print(f"Error toggling admin role: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/history')
@login_required
def history():
    """Show prediction history"""
    results = load_results()
    user_results = results.get(session['user'], [])
    # Sort by date, newest first
    user_results = sorted(user_results, key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('history.html', results=user_results, user=session.get('name', 'User'), role=session.get('role', 'user'), firebase_config=FIREBASE_CONFIG)


@app.route('/medications')
@login_required
def medications():
    """Medication reminder page"""
    meds = load_medications()
    user_meds = meds.get(session['user'], [])
    return render_template('medications.html', medications=user_meds, user=session.get('name', 'User'), role=session.get('role', 'user'), firebase_config=FIREBASE_CONFIG)


@app.route('/doctor-recommendations')
@login_required
def doctor_recommendations_page():
    """Doctor recommendations page"""
    all_advice = load_doctor_advice()
    user_advice = all_advice.get(session['user'], [])
    user_advice_sorted = sorted(user_advice, key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('doctor_recommendations.html',
                           user=session.get('name', 'User'),
                           role=session.get('role', 'user'),
                           advice_history=user_advice_sorted)


@app.route('/api/medications', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_medications():
    """API for medication management"""
    meds = load_medications()
    username = session['user']
    
    if username not in meds:
        meds[username] = []
    
    if request.method == 'GET':
        return jsonify({'success': True, 'medications': meds[username]})
    
    if request.method == 'POST':
        data = request.get_json()
        
        tablet_name = data.get('tablet_name', '').strip()
        frequency = int(data.get('frequency', 1))
        times = data.get('times', [])
        custom_times = data.get('custom_times', {})
        
        if not tablet_name:
            return jsonify({'success': False, 'error': 'Tablet name is required'})
        
        # Default times
        default_times = {
            'morning': '09:00',
            'afternoon': '13:00',
            'night': '20:30'
        }
        
        # Use custom times if provided, otherwise use defaults
        schedule = []
        for time_slot in times:
            time_value = custom_times.get(time_slot, default_times.get(time_slot, '09:00'))
            schedule.append({
                'slot': time_slot,
                'time': time_value,
                'taken': False,
                'taken_at': None
            })
        
        new_med = {
            'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
            'tablet_name': tablet_name,
            'frequency': frequency,
            'schedule': schedule,
            'created_at': datetime.now().isoformat()
        }
        
        meds[username].append(new_med)
        save_medications(meds)
        
        return jsonify({'success': True, 'medication': new_med})
    
    if request.method == 'DELETE':
        data = request.get_json()
        med_id = data.get('id')
        
        print(f"🗑️ Deleting medication: {med_id} for user: {username}")
        print(f"   Before: {len(meds[username])} medications")
        
        meds[username] = [m for m in meds[username] if m['id'] != med_id]
        save_medications(meds)
        
        print(f"   After: {len(meds[username])} medications")
        
        return jsonify({'success': True})


@app.route('/api/medications/mark-taken', methods=['POST'])
@login_required
def mark_medication_taken():
    """Mark a medication dose as taken"""
    data = request.get_json()
    med_id = data.get('med_id')
    slot = data.get('slot')
    
    meds = load_medications()
    username = session['user']
    
    if username in meds:
        for med in meds[username]:
            if med['id'] == med_id:
                for s in med['schedule']:
                    if s['slot'] == slot:
                        s['taken'] = True
                        s['taken_at'] = datetime.now().isoformat()
                        break
                break
        save_medications(meds)
    
    return jsonify({'success': True})


@app.route('/api/medications/reset-daily', methods=['POST'])
@login_required
def reset_daily_medications():
    """Reset all medication taken status for a new day"""
    meds = load_medications()
    username = session['user']
    
    if username in meds:
        for med in meds[username]:
            for s in med['schedule']:
                s['taken'] = False
                s['taken_at'] = None
                # Reset alert tracking for new day
                s['last_alert_sent'] = None
                s['alert_count'] = 0
        save_medications(meds)
    
    return jsonify({'success': True})


@app.route('/api/medications/alerts', methods=['GET'])
@login_required
def get_medication_alerts():
    """Get overdue medications for visual alerts"""
    try:
        meds = load_medications()
        username = session['user']
        current_time = datetime.now()
        alerts = []
        
        if username in meds:
            for med in meds[username]:
                medication_name = med.get('tablet_name', 'Medication')
                
                for slot in med['schedule']:
                    # Skip if already taken
                    if slot.get('taken', False):
                        continue
                    
                    slot_time = slot.get('time', '')
                    slot_name = slot.get('slot', 'unknown')
                    
                    if not slot_time:
                        continue
                    
                    try:
                        # Parse scheduled time
                        scheduled_hour, scheduled_minute = map(int, slot_time.split(':'))
                        current_hour = current_time.hour
                        current_minute = current_time.minute
                        
                        # Calculate time difference in minutes
                        time_diff = (current_hour * 60 + current_minute) - (scheduled_hour * 60 + scheduled_minute)
                        
                        # If overdue (even by 1 minute)
                        if time_diff > 0:
                            severity = 'warning'  # Default
                            
                            if time_diff >= 120:  # 2+ hours
                                severity = 'critical'
                            elif time_diff >= 30:  # 30+ minutes
                                severity = 'urgent'
                            
                            alerts.append({
                                'medication': medication_name,
                                'slot': slot_name,
                                'scheduled_time': slot_time,
                                'minutes_overdue': time_diff,
                                'severity': severity,
                                'message': f"{medication_name} ({slot_name}) is {time_diff} minutes overdue!"
                            })
                    
                    except ValueError:
                        continue
        
        return jsonify({'success': True, 'alerts': alerts})
    
    except Exception as e:
        print(f"Error getting medication alerts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/predict', methods=['POST'])
@login_required
def predict():
    """Handle prediction requests"""
    try:
        data = request.get_json()
        
        if not model_A or not model_B:
            return jsonify({
                'success': False,
                'error': 'Models not loaded. Please ensure model files exist in saved_models folder.'
            })
        
        # Prepare features
        features = prepare_features(data)
        
        # Get predictions
        prob_A = float(model_A.predict_proba(features)[0][1])
        prob_B = float(model_B.predict_proba(features)[0][1])
        avg_prob = (prob_A + prob_B) / 2
        
        # Determine risk levels
        def get_risk_level(prob):
            if prob < 0.3:
                return 'LOW'
            elif prob < 0.6:
                return 'MEDIUM'
            else:
                return 'HIGH'
        
        risk_level = get_risk_level(avg_prob)
        
        # ── Clinical rule overrides ──────────────────────────────────────────
        # The ML model may under-predict when a patient has multiple known risk
        # factors.  These evidence-based rules only *upgrade* risk, never lower it.
        def upgrade_risk(current, target):
            order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
            return target if order.get(target, 0) > order.get(current, 0) else current

        smoking_val = str(data.get('smoking_status', ''))
        hypertension_val = int(data.get('hypertension', 0))
        glucose_val = float(data.get('avg_glucose_level', 100))
        heart_val = int(data.get('heart_disease', 0))

        # Rule 1: Active smoker is never LOW risk
        if smoking_val == 'smokes':
            risk_level = upgrade_risk(risk_level, 'MEDIUM')

        # Rule 2: Hypertension + severely elevated glucose (≥200 mg/dL) → HIGH
        if hypertension_val == 1 and glucose_val >= 200:
            risk_level = upgrade_risk(risk_level, 'HIGH')

        # Rule 3: Hypertension + diabetic glucose range (≥140 mg/dL) → at least MEDIUM
        elif hypertension_val == 1 and glucose_val >= 140:
            risk_level = upgrade_risk(risk_level, 'MEDIUM')

        # Rule 4: Active smoking + hypertension → HIGH (two major stroke risk factors)
        if smoking_val == 'smokes' and hypertension_val == 1:
            risk_level = upgrade_risk(risk_level, 'HIGH')

        # Rule 5: Active smoking + heart disease → HIGH
        if smoking_val == 'smokes' and heart_val == 1:
            risk_level = upgrade_risk(risk_level, 'HIGH')

        # Rule 6: Active smoking + diabetic glucose → HIGH
        if smoking_val == 'smokes' and glucose_val >= 140:
            risk_level = upgrade_risk(risk_level, 'HIGH')
        # ────────────────────────────────────────────────────────────────────

        # Apply the same clinical rules to each individual model so that
        # all displayed risk labels are consistent with the ensemble decision.
        def apply_clinical_rules(base_risk):
            r = base_risk
            if smoking_val == 'smokes':
                r = upgrade_risk(r, 'MEDIUM')
            if hypertension_val == 1 and glucose_val >= 200:
                r = upgrade_risk(r, 'HIGH')
            elif hypertension_val == 1 and glucose_val >= 140:
                r = upgrade_risk(r, 'MEDIUM')
            if smoking_val == 'smokes' and hypertension_val == 1:
                r = upgrade_risk(r, 'HIGH')
            if smoking_val == 'smokes' and heart_val == 1:
                r = upgrade_risk(r, 'HIGH')
            if smoking_val == 'smokes' and glucose_val >= 140:
                r = upgrade_risk(r, 'HIGH')
            return r

        risk_A = apply_clinical_rules(get_risk_level(prob_A))
        risk_B = apply_clinical_rules(get_risk_level(prob_B))

        # When clinical rules force a higher risk label, the raw ML probability
        # is unreliable (models were trained on imbalanced data).  Calibrate
        # the *displayed* probability so it is consistent with the risk label.
        # Model A (trained on original data) is the stronger signal → floor 0.76
        # Model B (trained on synthetic data) is the weaker signal  → floor 0.65
        # Ensemble floor is the average of the two individual floors → ~0.70
        def calibrate_prob(raw_prob, final_risk, high_floor=0.70, medium_floor=0.40):
            if final_risk == 'HIGH':
                return max(raw_prob, high_floor)
            elif final_risk == 'MEDIUM':
                return max(raw_prob, medium_floor)
            return raw_prob

        disp_A        = calibrate_prob(prob_A,    risk_A,    high_floor=0.76)
        disp_B        = calibrate_prob(prob_B,    risk_B,    high_floor=0.65)
        disp_ensemble = calibrate_prob(avg_prob,  risk_level, high_floor=0.70)

        # Get food recommendations
        food_recommendations = get_food_recommendations(data, risk_level)
        
        # Get doctor recommendations
        doctor_recommendations = get_doctor_recommendations(data)
        
        # Get Indian food recommendations
        indian_food_recommendations = get_indian_food_recommendations(data)
        
        results = {
            'success': True,
            'model_A': {
                'probability': round(disp_A * 100, 1),
                'risk_level': risk_A
            },
            'model_B': {
                'probability': round(disp_B * 100, 1),
                'risk_level': risk_B
            },
            'ensemble': {
                'probability': round(disp_ensemble * 100, 1),
                'risk_level': risk_level
            },
            'food_recommendations': food_recommendations,
            'doctor_recommendations': doctor_recommendations,
            'indian_food_recommendations': indian_food_recommendations,
            'consult_doctor': doctor_recommendations.get('consult_doctor', False),
            'consult_message': doctor_recommendations.get('consult_message', ''),
            'doctor_types': doctor_recommendations.get('doctor_types', [])
        }
        
        # Save result to history
        result_entry = {
            'timestamp': datetime.now().isoformat(),
            'input_data': data,
            'results': {
                'model_A': results['model_A'],
                'model_B': results['model_B'],
                'ensemble': results['ensemble']
            },
            'food_recommendations': food_recommendations,
            'doctor_recommendations': doctor_recommendations,
            'indian_food_recommendations': indian_food_recommendations
        }
        
        all_results = load_results()
        username = session['user']
        if username not in all_results:
            all_results[username] = []
        all_results[username].append(result_entry)
        save_results(all_results)
        
        return jsonify(results)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/history/<int:result_id>')
@login_required
def get_result_detail(result_id):
    """Get detailed result by index"""
    try:
        results = load_results()
        user_results = results.get(session['user'], [])
        # Sort by date, newest first (same as history page)
        user_results = sorted(user_results, key=lambda x: x.get('timestamp', ''), reverse=True)
        if 0 <= result_id < len(user_results):
            return jsonify({'success': True, 'result': user_results[result_id]})
        return jsonify({'success': False, 'error': 'Result not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/delete-account', methods=['DELETE'])
@login_required
def delete_account():
    """Permanently delete user account and all associated data"""
    try:
        username = session.get('user')
        
        if not username:
            return jsonify({'success': False, 'error': 'User not logged in'}), 401
        
        # Prevent admin account deletion
        if username == 'admin':
            return jsonify({'success': False, 'error': 'Cannot delete admin account'}), 403
        
        print(f"\n🗑️ Deleting account: {username}")
        
        # Delete from users.json and record the deleted firebase_uid as a blocklist
        users = load_users()
        deleted_uid = None
        deleted_email = None
        if username in users:
            deleted_uid = users[username].get('firebase_uid')
            deleted_email = users[username].get('email')
            del users[username]
            # Persist deleted UID so this account can never log back in via old UID
            if deleted_uid:
                blocked = users.get('_deleted_uids', [])
                if deleted_uid not in blocked:
                    blocked.append(deleted_uid)
                users['_deleted_uids'] = blocked
            # Persist deleted email to allow re-registration with same email
            # (Firebase may still hold the account if client-side delete fails)
            if deleted_email:
                deleted_emails = users.get('_deleted_emails', [])
                if deleted_email not in deleted_emails:
                    deleted_emails.append(deleted_email)
                users['_deleted_emails'] = deleted_emails
            save_users(users)
            print(f"   ✓ Deleted from users.json")
            if deleted_uid:
                print(f"   ✓ UID {deleted_uid} added to deleted blocklist")
            if deleted_email:
                print(f"   ✓ Email {deleted_email} marked for re-registration")
        
        # Delete from results.json
        results = load_results()
        if username in results:
            del results[username]
            save_results(results)
            print(f"   ✓ Deleted from results.json")
        
        # Delete from medications.json
        medications = load_medications()
        if username in medications:
            del medications[username]
            save_medications(medications)
            print(f"   ✓ Deleted from medications.json")
        
        # Clear session
        session.clear()
        
        print(f"   ✓ Account '{username}' permanently deleted")
        
        return jsonify({
            'success': True,
            'message': 'Account and all associated data have been permanently deleted'
        })
        
    except Exception as e:
        print(f"   ✗ Error deleting account: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-doctor-recommendations', methods=['POST'])
@login_required
def api_get_doctor_recommendations():
    """API endpoint to get doctor recommendations based on all health parameters"""
    try:
        data = request.get_json()
        
        # Extract all form fields
        health_data = {
            'age': int(data.get('age', 50)),
            'gender': data.get('gender', 'Male'),
            'blood_pressure': float(data.get('blood_pressure', 0)),
            'hypertension': int(data.get('hypertension', 0)),
            'heart_disease': int(data.get('heart_disease', 0)),
            'ever_married': data.get('ever_married', 'Yes'),
            'work_type': data.get('work_type', 'Private'),
            'residence_type': data.get('residence_type', 'Urban'),
            'avg_glucose_level': float(data.get('avg_glucose_level', 100)),
            'bmi': float(data.get('bmi', 25)),
            'smoking_status': data.get('smoking_status', 'never smoked')
        }
        
        # Get doctor recommendations
        recommendations = get_doctor_recommendations(health_data)
        
        # Get Indian food recommendations
        indian_foods = get_indian_food_recommendations(health_data)
        
        # Add Indian foods to recommendations
        recommendations['indian_food_suggestions'] = indian_foods
        
        # Save to doctor advice history
        try:
            all_advice = load_doctor_advice()
            username = session['user']
            if username not in all_advice:
                all_advice[username] = []
            entry = {
                'timestamp': datetime.now().isoformat(),
                'input_data': health_data,
                'recommendations': recommendations
            }
            all_advice[username].append(entry)
            # Keep only last 50 entries per user
            all_advice[username] = all_advice[username][-50:]
            save_doctor_advice(all_advice)
        except Exception as hist_err:
            print(f"Warning: could not save doctor advice history: {hist_err}")
        
        return jsonify({
            'success': True,
            'recommendations': recommendations
        })
        
    except Exception as e:
        print(f"Error getting doctor recommendations: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parse-health-description', methods=['POST'])
@login_required
def api_parse_health_description():
    """API endpoint: parse free-text health description and return extracted values"""
    try:
        data = request.get_json()
        description = data.get('description', '')
        if not description.strip():
            return jsonify({'success': False, 'error': 'No description provided'}), 400
        extracted = parse_nlp_health_description(description)
        return jsonify({'success': True, 'extracted': extracted})
    except Exception as e:
        print(f"Error parsing health description: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


def generate_report_pdf(input_data, results, food_recommendations=None, doctor_recommendations=None, skip_predictions=False):
    """Generate a professional PDF report for stroke risk prediction results.
    Set skip_predictions=True when generating doctor-only reports (no ML model output).
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    # ==================== HEADER ====================
    pdf.set_font('Times', 'B', 24)
    pdf.set_text_color(25, 25, 112)  # Midnight Blue
    title = 'DOCTOR RECOMMENDATIONS REPORT' if skip_predictions else 'STROKE RISK PREDICTION REPORT'
    pdf.cell(0, 15, title, ln=True, align='C')
    
    pdf.set_font('Times', 'I', 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, 'Generated on: ' + datetime.now().strftime('%B %d, %Y at %I:%M %p'), ln=True, align='C')
    pdf.set_font('Times', 'B', 10)
    pdf.cell(0, 6, 'StrokeGuard AI Medical Analysis System', ln=True, align='C')
    pdf.ln(6)

    # Header separator line
    pdf.set_draw_color(25, 25, 112)
    pdf.set_line_width(1.0)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(10)

    # ==================== PATIENT INFORMATION ====================
    pdf.set_font('Times', 'B', 16)
    pdf.set_text_color(25, 25, 112)
    pdf.cell(0, 10, 'PATIENT INFORMATION', ln=True)
    pdf.set_draw_color(70, 130, 180)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 120, pdf.get_y())
    pdf.ln(6)

    # Patient data in a clean table format
    pdf.set_font('Times', '', 11)
    pdf.set_text_color(40, 40, 40)
    
    patient_fields = [
        ('Age', str(input_data.get('age', 'N/A')) + ' years'),
        ('Gender', str(input_data.get('gender', 'N/A'))),
        ('Marital Status', str(input_data.get('ever_married', 'N/A'))),
        ('Residence', str(input_data.get('residence_type', 'N/A'))),
        ('Work Type', str(input_data.get('work_type', 'N/A')).replace('_', ' ').title()),
        ('Smoking Status', str(input_data.get('smoking_status', 'N/A')).title()),
    ]

    for label, value in patient_fields:
        pdf.set_font('Times', 'B', 11)
        pdf.cell(70, 8, '    ' + label + ':', 0, 0)
        pdf.set_font('Times', '', 11)
        pdf.cell(0, 8, value, ln=True)
    
    pdf.ln(4)

    # ==================== CLINICAL PARAMETERS ====================
    pdf.set_font('Times', 'B', 16)
    pdf.set_text_color(25, 25, 112)
    pdf.cell(0, 10, 'CLINICAL PARAMETERS', ln=True)
    pdf.set_draw_color(70, 130, 180)
    pdf.line(20, pdf.get_y(), 120, pdf.get_y())
    pdf.ln(6)

    pdf.set_font('Times', '', 11)
    pdf.set_text_color(40, 40, 40)
    
    clinical_fields = [
        ('Hypertension', 'Yes' if str(input_data.get('hypertension', '0')) == '1' else 'No'),
        ('Heart Disease', 'Yes' if str(input_data.get('heart_disease', '0')) == '1' else 'No'),
        ('Average Glucose Level', str(input_data.get('avg_glucose_level', 'N/A')) + ' mg/dL'),
        ('Body Mass Index (BMI)', str(input_data.get('bmi', 'N/A'))),
    ]

    for label, value in clinical_fields:
        pdf.set_font('Times', 'B', 11)
        pdf.cell(70, 8, '    ' + label + ':', 0, 0)
        pdf.set_font('Times', '', 11)
        pdf.cell(0, 8, value, ln=True)
    
    pdf.ln(8)

    # ========== PREDICTION RESULTS (ML models — omitted for doctor-only reports) ==========
    if not skip_predictions:
        pdf.set_font('Times', 'B', 16)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 10, 'PREDICTION RESULTS', ln=True)
        pdf.set_draw_color(70, 130, 180)
        pdf.line(20, pdf.get_y(), 120, pdf.get_y())
        pdf.ln(6)

        model_a = results.get('model_A', {})
        model_b = results.get('model_B', {})
        ensemble = results.get('ensemble', {})

        # Model A Results
        pdf.set_font('Times', 'B', 13)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 8, 'Model A (Original Dataset)', ln=True)
        pdf.set_font('Times', '', 11)
        pdf.cell(70, 7, '        Stroke Probability:', 0, 0)
        pdf.set_font('Times', 'B', 11)
        pdf.cell(0, 7, str(model_a.get('probability', 'N/A')) + '%', ln=True)
        pdf.set_font('Times', '', 11)
        pdf.cell(70, 7, '        Risk Classification:', 0, 0)
        pdf.set_font('Times', 'B', 11)
        pdf.cell(0, 7, str(model_a.get('risk_level', 'N/A')), ln=True)
        pdf.ln(4)

        # Model B Results
        pdf.set_font('Times', 'B', 13)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 8, 'Model B (Synthetic-Enhanced Dataset)', ln=True)
        pdf.set_font('Times', '', 11)
        pdf.cell(70, 7, '        Stroke Probability:', 0, 0)
        pdf.set_font('Times', 'B', 11)
        pdf.cell(0, 7, str(model_b.get('probability', 'N/A')) + '%', ln=True)
        pdf.set_font('Times', '', 11)
        pdf.cell(70, 7, '        Risk Classification:', 0, 0)
        pdf.set_font('Times', 'B', 11)
        pdf.cell(0, 7, str(model_b.get('risk_level', 'N/A')), ln=True)
        pdf.ln(6)

        # Ensemble (Combined) Results - HIGHLIGHTED
        pdf.set_fill_color(230, 240, 250)
        pdf.set_draw_color(70, 130, 180)
        pdf.set_line_width(0.3)
        pdf.rect(18, pdf.get_y(), 174, 28, 'D')
        
        pdf.set_font('Times', 'B', 14)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 10, 'COMBINED ENSEMBLE PREDICTION', ln=True)
        
        pdf.set_font('Times', '', 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(70, 7, '        Overall Probability:', 0, 0)
        pdf.set_font('Times', 'B', 12)
        pdf.cell(0, 7, str(ensemble.get('probability', 'N/A')) + '%', ln=True)
        
        pdf.set_font('Times', '', 11)
        pdf.cell(70, 7, '        Final Risk Level:', 0, 0)
        
        risk_level = str(ensemble.get('risk_level', 'N/A'))
        pdf.set_font('Times', 'B', 13)
        if risk_level == 'HIGH':
            pdf.set_text_color(178, 34, 34)  # Firebrick red
        elif risk_level == 'MEDIUM':
            pdf.set_text_color(218, 165, 32)  # Goldenrod
        else:
            pdf.set_text_color(34, 139, 34)  # Forest green
        pdf.cell(0, 7, risk_level, ln=True)
        pdf.set_text_color(40, 40, 40)
        pdf.ln(10)

    # ==================== DIETARY RECOMMENDATIONS ====================
    if food_recommendations:
        pdf.set_font('Times', 'B', 16)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 10, 'DIETARY RECOMMENDATIONS', ln=True)
        pdf.set_draw_color(70, 130, 180)
        pdf.line(20, pdf.get_y(), 120, pdf.get_y())
        pdf.ln(6)

        # Urgent message if any
        urgent_msg = food_recommendations.get('urgent_message', '')
        if urgent_msg:
            urgent_clean = remove_emojis(urgent_msg)
            pdf.set_fill_color(255, 245, 245)
            pdf.set_font('Times', 'B', 11)
            pdf.set_text_color(178, 34, 34)
            pdf.multi_cell(0, 7, 'ALERT: ' + urgent_clean, 0, 'L', True)
            pdf.set_text_color(40, 40, 40)
            pdf.ln(4)

        # Recommended Foods
        foods_to_eat = food_recommendations.get('foods_to_eat', [])
        if foods_to_eat:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(34, 139, 34)
            pdf.cell(0, 9, 'Foods to Include in Your Diet:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for food in foods_to_eat[:12]:  # Limit to 12 items
                clean_food = remove_emojis(str(food))
                if clean_food:  # Only add if there's text after removing emojis
                    pdf.cell(0, 6, '      * ' + clean_food, ln=True)
            pdf.ln(4)

        # Foods to Avoid
        foods_to_avoid = food_recommendations.get('foods_to_avoid', [])
        if foods_to_avoid:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(178, 34, 34)
            pdf.cell(0, 9, 'Foods to Limit or Avoid:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for food in foods_to_avoid[:10]:  # Limit to 10 items
                clean_food = remove_emojis(str(food))
                if clean_food:
                    pdf.cell(0, 6, '      * ' + clean_food, ln=True)
            pdf.ln(4)

        # General Health Advice
        advice_list = food_recommendations.get('general_advice', [])
        if advice_list:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(25, 25, 112)
            pdf.cell(0, 9, 'General Health Advice:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for advice in advice_list:
                clean_advice = remove_emojis(str(advice))
                if clean_advice:
                    pdf.multi_cell(0, 6, '      * ' + clean_advice)
            pdf.ln(2)

    # ==================== DOCTOR RECOMMENDATIONS ====================
    if doctor_recommendations:
        pdf.add_page()  # Add new page for doctor recommendations
        
        pdf.set_font('Times', 'B', 16)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 10, 'DOCTOR RECOMMENDATIONS', ln=True)
        pdf.set_draw_color(70, 130, 180)
        pdf.line(20, pdf.get_y(), 130, pdf.get_y())
        pdf.ln(6)

        # Risk Category
        pdf.set_font('Times', 'B', 14)
        risk_category = doctor_recommendations.get('risk_category', 'N/A')
        risk_level_doc = doctor_recommendations.get('risk_level', 'LOW')
        
        if risk_level_doc == 'HIGH':
            pdf.set_text_color(178, 34, 34)
        elif risk_level_doc == 'MEDIUM':
            pdf.set_text_color(218, 165, 32)
        else:
            pdf.set_text_color(34, 139, 34)
        
        pdf.cell(0, 10, 'Risk Assessment: ' + risk_category, ln=True)
        pdf.set_text_color(40, 40, 40)
        pdf.ln(4)

        # Medical Advice
        medical_advice = doctor_recommendations.get('medical_advice', [])
        if medical_advice:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(25, 25, 112)
            pdf.cell(0, 9, 'Medical Advice:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for advice in medical_advice[:10]:
                clean_advice = remove_emojis(str(advice))
                if clean_advice:
                    pdf.multi_cell(0, 6, '      * ' + clean_advice)
            pdf.ln(4)

        # Indian Foods to Include
        indian_foods_eat = doctor_recommendations.get('indian_foods_to_eat', [])
        if indian_foods_eat:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(34, 139, 34)
            pdf.cell(0, 9, 'Indian Foods to Include:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for food in indian_foods_eat[:12]:
                clean_food = remove_emojis(str(food))
                if clean_food:
                    pdf.cell(0, 6, '      * ' + clean_food, ln=True)
            pdf.ln(4)

        # Indian Foods to Avoid
        indian_foods_avoid = doctor_recommendations.get('indian_foods_to_avoid', [])
        if indian_foods_avoid:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(178, 34, 34)
            pdf.cell(0, 9, 'Indian Foods to Avoid:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for food in indian_foods_avoid[:12]:
                clean_food = remove_emojis(str(food))
                if clean_food:
                    pdf.cell(0, 6, '      * ' + clean_food, ln=True)
            pdf.ln(4)

        # Lifestyle Changes
        lifestyle = doctor_recommendations.get('lifestyle_changes', [])
        if lifestyle:
            pdf.set_font('Times', 'B', 13)
            pdf.set_text_color(25, 25, 112)
            pdf.cell(0, 9, 'Recommended Lifestyle Changes:', ln=True)
            pdf.set_font('Times', '', 11)
            pdf.set_text_color(40, 40, 40)
            
            for change in lifestyle[:10]:
                clean_change = remove_emojis(str(change))
                if clean_change:
                    pdf.multi_cell(0, 6, '      * ' + clean_change)
            pdf.ln(2)

    # ==================== FOOTER ====================
    pdf.ln(8)
    pdf.set_draw_color(25, 25, 112)
    pdf.set_line_width(0.8)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)
    
    pdf.set_font('Times', 'BI', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5, 'DISCLAIMER: This report is generated by an AI-based prediction system and is intended for informational purposes only. It should NOT be used as a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of your physician or other qualified health provider with any questions you may have regarding a medical condition.', 0, 'C')
    
    pdf.ln(2)
    pdf.set_font('Times', 'I', 9)
    pdf.cell(0, 5, 'StrokeGuard AI (c) 2024 - Advanced Medical Analytics', ln=True, align='C')

    return pdf


@app.route('/download-report')
@login_required
def download_report():
    """Download prediction result as a PDF report from dashboard"""
    try:
        input_data = json.loads(request.args.get('data', '{}'))
        results = json.loads(request.args.get('results', '{}'))
        food = json.loads(request.args.get('food', '{}'))
        doctor = json.loads(request.args.get('doctor', '{}'))

        pdf = generate_report_pdf(input_data, results, food, doctor)

        # Get PDF as bytes string
        pdf_output = pdf.output(dest='S')
        # Convert to bytes if it's a string
        if isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)

        filename = 'StrokeRisk_Report_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.pdf'
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download-history-report/<int:index>')
@login_required
def download_history_report(index):
    """Download a specific history entry as PDF"""
    try:
        results_data = load_results()
        user_results = results_data.get(session['user'], [])
        user_results = sorted(user_results, key=lambda x: x.get('timestamp', ''), reverse=True)

        if index < 0 or index >= len(user_results):
            return jsonify({'error': 'Invalid index'}), 404

        entry = user_results[index]
        input_data = entry.get('input_data', {})
        pred_results = entry.get('results', {})
        food = entry.get('food_recommendations', None)
        doctor = entry.get('doctor_recommendations', None)

        pdf = generate_report_pdf(input_data, pred_results, food, doctor)

        # Get PDF as bytes string
        pdf_output = pdf.output(dest='S')
        # Convert to bytes if it's a string
        if isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)

        filename = 'StrokeRisk_Report_' + entry.get('timestamp', '')[:10].replace('-', '') + '.pdf'
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download-doctor-report', methods=['POST'])
@login_required
def download_doctor_report():
    """Download doctor recommendations as a standalone PDF (no ML model data)"""
    try:
        req_data = request.get_json()
        input_data = req_data.get('input_data', {})
        doctor_recommendations = req_data.get('recommendations', {})

        pdf = generate_report_pdf(
            input_data=input_data,
            results={},
            food_recommendations=None,
            doctor_recommendations=doctor_recommendations,
            skip_predictions=True
        )

        pdf_output = pdf.output(dest='S')
        if isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output

        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name='Doctor_Recommendations_Report.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"Error generating doctor report PDF: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'models_loaded': model_A is not None and model_B is not None
    })


# Initialize Background Scheduler for Medication Reminders
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_medication_reminders,
    trigger=IntervalTrigger(minutes=1),  # Check every minute
    id='medication_reminder_job',
    name='Check medication reminders',
    replace_existing=True
)

# Start the scheduler
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

print("\n⏰ Medication reminder scheduler started!")
print("   Checking for overdue medications every minute...")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏥 Stroke Prediction Dashboard")
    print("="*60)
    print("Starting server at http://127.0.0.1:5000")
    print("Authentication: Firebase only (email/password + Google)")
    print("Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)

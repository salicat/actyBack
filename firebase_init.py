import firebase_admin
from firebase_admin import credentials

def initialize_firebase():
    # Path to your Firebase service account key
    key_path = 'FireB_JsonKey/otp1-d9db4-firebase-adminsdk-x0mbp-c4d7507b59.json'
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
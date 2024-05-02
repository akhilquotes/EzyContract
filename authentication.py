import datetime
import re
from flask import Blueprint, redirect, render_template, request, session, url_for
import pyrebase

config = {
    "apiKey" : "AIzaSyD8AIy3Ksie53JLDEh7VxMAe1aVFkplxGQ",
    "authDomain" : "supplychain-2b269.firebaseapp.com",
    "projectId" : "supplychain-2b269",
    "storageBucket" : "supplychain-2b269.appspot.com",
    "messagingSenderId" : "507383147420",
    "appId" : "1:507383147420:web:a0a5035c4e6d31387d7659",
    "databaseURL" : "https://supplychain-2b269-default-rtdb.firebaseio.com/"
}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()


# Function to check password strength
def check_password_strength(password):
    # At least one lower case letter, one upper case letter, one digit, one special character, and at least 8 characters long
    return re.match(r'^(?=.*\d)(?=.*[!@#$%^&*])(?=.*[a-z])(?=.*[A-Z]).{8,}$', password) is not None

def create_user(email,password):
    auth.create_user_with_email_and_password(email, password)
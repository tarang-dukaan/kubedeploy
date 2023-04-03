from flask import Flask, redirect, url_for, session, request
from config import secret_key,client_id,client_secret
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError
import requests
app = Flask(__name__)
app.config['SECRET_KEY'] = secret_key


@app.route('/')
def home():
    return 'Home Page'

@app.route('/login')
def login():

    authorized_domains = ['rankz.io']
    redirect_uri = 'http://localhost:5000/callback'
    auth_url = f'https://accounts.google.com/o/oauth2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=openid%20email&hd={authorized_domains}'
    return redirect(auth_url)

@app.route('/callback')
def callback():
    
    authorized_domains = ['rankz.io']
    redirect_uri = url_for('callback', _external=True)
    code = request.args.get('code')
    token_url = 'https://oauth2.googleapis.com/token'
    token_payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    token_response = requests.post(token_url, data=token_payload)
    token_data = token_response.json()
    id_token_jwt = token_data.get('id_token')

    id_info = id_token.verify_oauth2_token(id_token_jwt, Request(), client_id)

    if id_info['email'].split('@')[-1] not in authorized_domains:
        return 'Access Denied'
    session['email'] = id_info['email']
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def protected():
    if 'email' not in session:
        return redirect(url_for('login'))
    


    return 'Protected Area'

if __name__ == '__main__':
    app.run()

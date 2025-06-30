import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests

def get_access_token():
    # Path to your downloaded JSON key
    key_file_path = 'strahn-demo-wallet-6c2bce347ee3.json' 
    
    scopes = ['https://www.googleapis.com/auth/firebase.messaging']

    credentials = service_account.Credentials.from_service_account_file(
        key_file_path,
        scopes=scopes
    )
    
    # The `token` attribute holds the access token string
    # The `refresh` method will automatically handle refreshing when needed
    # Call refresh() once to ensure the token is available
    credentials.refresh(google.auth.transport.requests.Request())
    
    print("Access Token:", credentials.token)
    return credentials.token

if __name__ == "__main__":
    print(get_access_token())
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, Form, Response
from fastapi.responses import RedirectResponse
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import razorpay
from pydantic import BaseModel
# Security and Token Libraries
from passlib.context import CryptContext
from jose import JWTError, jwt

# Supabase Library
from supabase import create_client, Client
# Google Auth Libraries (still needed for your custom Google sign-in)
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# --- NEW: Import Pydantic for update model ---
from pydantic import BaseModel

# =================================================================

# --- Supabase Connection ---
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# --- Password Hashing Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- JWT Configuration ---
# We no longer need our own SECRET_KEY for sessions, Supabase handles it.
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- Router Setup ---
router = APIRouter()

# =================================================================
#  HELPER & DEPENDENCY FUNCTIONS
# =================================================================

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# This function is no longer used for sessions, but could be useful for other things.
# We'll leave it for now, but it's not part of the auth flow.
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    # You still need a SECRET_KEY if you use this function
    CUSTOM_SECRET = os.environ.get("SECRET_KEY") 
    return jwt.encode(to_encode, CUSTOM_SECRET, algorithm=ALGORITHM)

#
# =================================================================
#  FIX #1: THE NEW get_current_user
#  This function now validates the token WITH SUPABASE.
# =================================================================
#
async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    token = token.replace("Bearer ", "")
    
    try:
        # Use the Supabase client to get the user from the token
        # This validates the token and returns the user from auth.users
        auth_user_response = supabase.auth.get_user(token)
        auth_user = auth_user_response.user
        
        if not auth_user:
            return None
        
        # Now, fetch the user's PUBLIC PROFILE (with username, credits)
        # We use the user's ID, which is the link between auth.users and public.users
        profile_response = supabase.table('users').select("*").eq('id', auth_user.id).execute()
        
        if not profile_response.data:
            # This can happen if the trigger failed or is new
            print(f"Auth user {auth_user.id} exists, but profile not found.")
            return None
            
        return profile_response.data[0]
        
    except Exception as e:
        print(f"Error in get_current_user: {e}")
        return None

# --- NEW: Pydantic model for profile updates ---
class ProfileUpdate(BaseModel):
    username: str
    title: Optional[str] = None
    bio: Optional[str] = None
    # We will handle image URLs in a later step

# =================================================================
#  ROUTES
# =================================================================

@router.post("/signup")
async def signup(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    try:
        # 1. Attempt to Sign Up
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": { "username": username }
            }
        })

        # 2. Check if user was created (Supabase sometimes returns None if user exists but doesn't throw error)
        if not auth_response.user:
            # If no user object returned, assume they exist
            return RedirectResponse(url="/login?error=You+already+have+an+account.+Please+Log+In.", status_code=303)

        # 3. Add 10 Free Credits (Database)
        # Note: The SQL Trigger we added handles this now, but this is a safe backup
        try:
            user_id = auth_response.user.id
            supabase.table('users').update({"graph_credits": 10}).eq('id', user_id).execute()
        except Exception:
            pass # Trigger likely handled it

        # 4. Success - Log them in
        if auth_response.session:
            access_token = auth_response.session.access_token
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
            return response
            
    except Exception as e:
        error_msg = str(e)
        print(f"--- SIGNUP ERROR: {error_msg} ---")
        
        # --- THE FIX IS HERE ---
        # Check if the error message says the user exists
        if "User already registered" in error_msg or "already registered" in error_msg:
            return RedirectResponse(url="/login?error=You+already+have+an+account.+Please+Log+In.", status_code=303)
            
        # Default error for other crashes
        return RedirectResponse(url="/signup?error=An+unexpected+error+occurred.+Try+again.", status_code=303)

    # Fallback
    return RedirectResponse(url="/login?msg=Account+created!+Please+log+in.", status_code=303)

@router.post("/login")
async def login(response: Response, email: str = Form(...), password: str = Form(...)):
    try:
        # This route is correct.
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if auth_response.session:
            access_token = auth_response.session.access_token
            
            redirect_response = RedirectResponse(url="/dashboard", status_code=303)
            redirect_response.set_cookie(
                key="access_token", 
                value=f"Bearer {access_token}", 
                httponly=True, 
                samesite="lax"
            )
            return redirect_response
        else:
            return RedirectResponse(url="/login?error=Incorrect+email+or+password", status_code=303)
            
    except Exception as e:
        print(f"--- LOGIN ERROR: {e} ---")
        return RedirectResponse(url="/login?error=Incorrect+email+or+password", status_code=303)

@router.get("/logout")
async def logout():
    # This route is correct.
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response


@router.get("/users/me")
async def read_users_me(current_user: Optional[dict] = Depends(get_current_user)):
    # This route should now work perfectly.
    # `current_user` is the profile data from your 'users' table.
    if current_user:
        return {
            "loggedIn": True, 
            "username": current_user.get("username"), 
            "email": current_user.get("email"),
            "credits": current_user.get("graph_credits") # Make sure this column name is correct
        }
    return {"loggedIn": False}


#
# =================================================================
#  NEW: Profile Page API Endpoints
# =================================================================
#

@router.get("/api/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Gets the profile data for the currently logged-in user.
    """
    if not current_user:
        # If no user, raise 401 Unauthorized, which JS will catch
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # current_user is the profile from the 'users' table, return it
    return current_user

@router.post("/api/profile")
async def update_profile(
    update_data: ProfileUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Updates the profile data for the currently logged-in user.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = current_user.get("id")
    
    try:
        # Update the 'users' table in Supabase
        updated_profile_response = supabase.table('users').update({
            "username": update_data.username,
            "title": update_data.title,
            "bio": update_data.bio
        }).eq('id', user_id).select("*").execute() # Added select("*") to get data back
        
        if not updated_profile_response.data:
            raise HTTPException(status_code=404, detail="Profile not found or update failed")
            
        # Return the newly updated profile data
        return updated_profile_response.data[0]
        
    except Exception as e:
        print(f"--- PROFILE UPDATE ERROR: {e} ---")
        raise HTTPException(status_code=500, detail="Error updating profile")


#
# =================================================================
#
@router.post("/auth/google/callback")
async def google_auth_callback(request: Request):
    form_data = await request.form()
    credential = form_data.get('credential') # This is the ID token from Google
    
    if not credential:
        raise HTTPException(status_code=400, detail="No credential provided")

    try:
        # Use Supabase's built-in function to sign in (or sign up)
        # This exchanges the Google ID token for a Supabase session
        auth_response = supabase.auth.sign_in_with_id_token({
            "provider": "google",
            "token": credential
        })
        
        if not auth_response.session:
            raise Exception("Google Sign-In failed with Supabase.")
        
        # We have a valid Supabase session and token
        access_token = auth_response.session.access_token
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
        return response

    except Exception as e:
        print(f"Google Sign-In Error: {e}")
        return RedirectResponse(url="/login?error=Google+sign-in+failed", status_code=303)
    

    # =================================================================
#  NEW PAYMENT & CREDIT ROUTES (Add these to auth.py)
# =================================================================


# --- Add these to your config section near the top ---
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
# ---

class OrderRequest(BaseModel):
    amount: int
    currency: str

class VerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/api/create-order")
async def create_order(order_request: OrderRequest, current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        amount_in_paise = order_request.amount * 100
        order_data = {
            'amount': amount_in_paise,
            'currency': 'INR',
            'receipt': str(uuid.uuid4())  # This is the 36-character unique ID
        }
        order = razorpay_client.order.create(data=order_data)
        return {
            "key_id": RAZORPAY_KEY_ID,
            "order_id": order['id'],
            "amount": order['amount']  # This will be 19900
        }
    except Exception as e:
        print(f"--- CREATE ORDER ERROR: {e} ---")
        raise HTTPException(status_code=500, detail="Could not create payment order")

@router.post("/api/verify-payment")
async def verify_payment(verify_request: VerifyRequest, current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Verify the signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': verify_request.razorpay_order_id,
            'razorpay_payment_id': verify_request.razorpay_payment_id,
            'razorpay_signature': verify_request.razorpay_signature
        })
        
        # --- Signature is valid, update credits ---
        user_id = current_user['id']
        
        # 1. Get current credits
        profile_response = supabase.table('users').select("graph_credits").eq('id', user_id).execute()
        if not profile_response.data:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        current_credits = profile_response.data[0].get('graph_credits', 0)
        
        # 2. Add new credits (e.g., 50 for this purchase)
        new_total_credits = current_credits + 50
        
        # 3. Update the database
        update_response = supabase.table('users').update({
            "graph_credits": new_total_credits
        }).eq('id', user_id).execute()

        return {"status": "success", "new_credits": new_total_credits}

    except razorpay.errors.SignatureVerificationError:
        print("--- PAYMENT VERIFICATION FAILED: Invalid signature ---")
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        print(f"--- VERIFY PAYMENT ERROR: {e} ---")
        raise HTTPException(status_code=500, detail="Error verifying payment")

@router.post("/api/use-credit")
async def use_credit(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user['id']
    current_credits = current_user.get('graph_credits', 0)

    if current_credits <= 0:
        return {"status": "failed", "error": "No credits remaining"}

    new_total_credits = current_credits - 1

    try:
        supabase.table('users').update({
            "graph_credits": new_total_credits
        }).eq('id', user_id).execute()
        
        return {"status": "success", "new_credits": new_total_credits}
    except Exception as e:
        print(f"--- USE CREDIT ERROR: {e} ---")
        # Don't block the user, just log the error
        return {"status": "error", "message": "Failed to log credit use"}

#
# (Your existing /auth/google/callback route comes after this)
#
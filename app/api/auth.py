import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, Form, Response
from fastapi.responses import RedirectResponse
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import razorpay
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from supabase import create_client, Client
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# --- Password Hashing Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

router = APIRouter()
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    CUSTOM_SECRET = os.environ.get("SECRET_KEY") 
    return jwt.encode(to_encode, CUSTOM_SECRET, algorithm=ALGORITHM)


async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    token = token.replace("Bearer ", "")    
    try:
        auth_user_response = supabase.auth.get_user(token)
        auth_user = auth_user_response.user       
        if not auth_user:
            return None
        profile_response = supabase.table('users').select("*").eq('id', auth_user.id).execute()       
        if not profile_response.data:
            print(f"Auth user {auth_user.id} exists, but profile not found.")
            return None           
        return profile_response.data[0]       
    except Exception as e:
        print(f"Error in get_current_user: {e}")
        return None

class ProfileUpdate(BaseModel):
    username: str
    title: Optional[str] = None  

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

        try:
            user_id = auth_response.user.id
            supabase.table('users').update({"graph_credits": 10}).eq('id', user_id).execute()
        except Exception as e:
            print(f"Error assigning free credits: {e}")
            pass
        # 4. Success - Log them in
        if auth_response.session:
            access_token = auth_response.session.access_token
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
            return response
            
    except Exception as e:
        error_msg = str(e)
        print(f"--- SIGNUP ERROR: {error_msg} ---")
        
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
    if current_user:
        return {
            "loggedIn": True, 
            "username": current_user.get("username"), 
            "email": current_user.get("email"),
            "credits": current_user.get("graph_credits") # Make sure this column name is correct
        }
    return {"loggedIn": False}

@router.get("/api/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Gets the profile data for the currently logged-in user.
    """
    if not current_user:
        # If no user, raise 401 Unauthorized, which JS will catch
        raise HTTPException(status_code=401, detail="Not authenticated")
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
        updated_profile_response = supabase.table('users').update({
            "username": update_data.username,
            "title": update_data.title,
            "bio": update_data.bio
        }).eq('id', user_id).execute()
        
        if not updated_profile_response.data:
            raise HTTPException(status_code=404, detail="Profile not found or update failed")
            
        # Return the newly updated profile data
        return updated_profile_response.data[0]
        
    except Exception as e:
        print(f"--- PROFILE UPDATE ERROR: {e} ---")
        raise HTTPException(status_code=500, detail="Error updating profile")


# now i am writing code for enterprise model when you will launch enterprise model just on the upper code and off the lower google auth check

# --- ADD THIS AT THE TOP OF auth.py ---
EDU_DOMAINS = ["du.ac.in", "iitm.ac.in", "smail.iitm.ac.in", "morph-ai.com"]

# --- REPLACE THE CALLBACK FUNCTION ---
@router.post("/auth/google/callback")
async def google_auth_callback(request: Request):
    form_data = await request.form()
    credential = form_data.get('credential')
    
    if not credential:
        raise HTTPException(status_code=400, detail="No credential provided")
    
    try:
        # 1. Sign in with Google
        auth_response = supabase.auth.sign_in_with_id_token({
            "provider": "google",
            "token": credential
        })        
        
        if not auth_response.session:
            raise Exception("Google Sign-In failed with Supabase.")
        
        user = auth_response.user
        
        # --- FIX STARTS HERE: Set Default Redirect ---
        redirect_url = "/dashboard" 
        # ---------------------------------------------

        # 2. CHECK PROFILE & DETERMINE FLOW
        try:
            profile_response = supabase.table('users').select("*").eq('id', user.id).execute()
            
            # IF NEW USER (Profile missing)
            if not profile_response.data:
                print(f"New Google User detected: {user.email}")
                
                # A. Check if Enterprise Domain
                domain = user.email.split('@')[-1].lower()
                is_enterprise = any(domain.endswith(edu) for edu in EDU_DOMAINS)
                
                initial_credits = 10     # Default for normal users
                
                # B. Enterprise Rule: 0 Credits until they pay ₹1
                if is_enterprise:
                    print(f"Enterprise User Detected ({user.email}). Redirecting to payment.")
                    initial_credits = 0
                    redirect_url = "/dashboard?action=verify_enterprise" # <--- Overwrites default if needed

                # C. Create Profile
                raw_username = user.user_metadata.get('full_name') or user.email.split('@')[0]
                new_profile = {
                    "id": user.id,
                    "email": user.email,
                    "username": raw_username,
                    "graph_credits": initial_credits
                }
                
                supabase.table('users').insert(new_profile).execute()
                
        except Exception as db_error:
            print(f"Warning: Profile Sync Failed: {db_error}")

        # 3. Success - Log them in and Redirect
        access_token = auth_response.session.access_token
        
        # Now 'redirect_url' is guaranteed to exist (either "/dashboard" or the verify link)
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
        return response

    except Exception as e:
        print(f"Google Sign-In Critical Error: {e}")
        return RedirectResponse(url="/login?error=Google+sign-in+failed", status_code=303)



# @router.post("/auth/google/callback")
# async def google_auth_callback(request: Request):
#     form_data = await request.form()
#     credential = form_data.get('credential')
    
#     if not credential:
#         raise HTTPException(status_code=400, detail="No credential provided")
    
#     try:
#         # 1. Sign in with Google (Auth Layer)
#         auth_response = supabase.auth.sign_in_with_id_token({
#             "provider": "google",
#             "token": credential
#         })        
        
#         if not auth_response.session:
#             raise Exception("Google Sign-In failed with Supabase.")
        
#         user = auth_response.user
        
#         # 2. CHECK: Does the profile exist in the public 'users' table?
#         try:
#             profile_response = supabase.table('users').select("*").eq('id', user.id).execute()
            
#             # 3. HANDLE MISSING PROFILE (This is a New User)
#             if not profile_response.data:
#                 print(f"New Google User detected (No Profile): {user.email}")
                
#                 # Get username from metadata or fallback to email
#                 raw_username = user.user_metadata.get('full_name') or user.user_metadata.get('name')
#                 if not raw_username:
#                     raw_username = user.email.split('@')[0]
                
#                 # Create the profile MANUALLY with 10 Credits
#                 new_profile = {
#                     "id": user.id,
#                     "email": user.email,
#                     "username": raw_username,
#                     "graph_credits": 10  # <--- GIVING THE FREE CREDITS HERE
#                 }
                
#                 supabase.table('users').insert(new_profile).execute()
#                 print("Profile created successfully with 10 credits.")
                
#         except Exception as db_error:
#             # If this fails, we log it but still allow login (Safety Net)
#             print(f"Warning: Profile Sync Failed: {db_error}")

#         # 4. Success - Log them in
#         access_token = auth_response.session.access_token
#         response = RedirectResponse(url="/dashboard", status_code=303)
#         response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
#         return response

#     except Exception as e:
#         print(f"Google Sign-In Critical Error: {e}")
#         return RedirectResponse(url="/login?error=Google+sign-in+failed", status_code=303)




RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

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
        user_id = current_user['id']
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
    
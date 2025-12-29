from fastapi import APIRouter, Depends, HTTPException, Response, Request, Header
from supabase import Client
import os
import razorpay
import json
from supabase import create_client, Client
import supabase
from .auth import get_current_user # Import your user dependency

router = APIRouter()
@router.post("/use-credit")
async def use_credit(current_user: dict = Depends(get_current_user)):
    """
    Checks if a user has credits, deducts one if they do,
    and returns the new credit count.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_email = current_user.get("email")

    try:
        user_profile_response = supabase.table('users').select('graph_credits').eq('email', user_email).single().execute()
        
        if not user_profile_response.data:
            raise HTTPException(status_code=404, detail="User profile not found")

        current_credits = user_profile_response.data.get('graph_credits', 0)

        if current_credits > 0:
            new_credits = current_credits - 1
            updated_user = supabase.table('users').update({'graph_credits': new_credits}).eq('email', user_email).execute()
            return {"status": "success", "credits_remaining": new_credits}
        else:
            return {"status": "insufficient_credits", "credits_remaining": 0}

    except Exception as e:
        print(f"--- CREDIT ERROR: {e} ---")
        raise HTTPException(status_code=500, detail="An error occurred while processing credits.")
 
# import os
# import uuid
# import time
# import razorpay
# from datetime import datetime, timedelta, timezone
# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel
# from supabase import create_client, Client
# from app.api.auth import get_current_user

# router = APIRouter()

# # --- Configuration ---
# supabase_url = os.environ.get("SUPABASE_URL")
# supabase_key = os.environ.get("SUPABASE_KEY")
# supabase: Client = create_client(supabase_url, supabase_key)

# RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
# RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
# razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# # --- Models ---
# class OrderRequest(BaseModel):
#     amount: int

# class PaymentVerification(BaseModel):
#     razorpay_order_id: str
#     razorpay_payment_id: str
#     razorpay_signature: str

# # --- Routes ---

# @router.post("/create-order")
# async def create_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
#     if not current_user:
#         raise HTTPException(status_code=401, detail="Not authenticated")
#     try:
#         # ALLOW 1 Rupee for Enterprise verification
#         allowed_prices = [1, 49, 199, 999] 
#         if request.amount not in allowed_prices:
#             raise HTTPException(status_code=400, detail="Invalid price package")

#         amount_in_paise = request.amount * 100
#         order_data = {
#             'amount': amount_in_paise,
#             'currency': 'INR',
#             'receipt': f"rcpt_{current_user['id'][:6]}_{int(time.time())}",
#             'notes': { "user_id": current_user['id'] }
#         }
#         order = razorpay_client.order.create(data=order_data)
#         return order
#     except Exception as e:
#         print(f"--- CREATE ORDER ERROR: {e} ---")
#         raise HTTPException(status_code=500, detail="Could not create payment order")


# @router.post("/verify-payment")
# async def verify_payment(data: PaymentVerification, current_user: dict = Depends(get_current_user)):
#     if not current_user:
#         raise HTTPException(status_code=401, detail="Not authenticated")
#     try:
#         # 1. Verify Signature
#         params_dict = {
#             'razorpay_order_id': data.razorpay_order_id,
#             'razorpay_payment_id': data.razorpay_payment_id,
#             'razorpay_signature': data.razorpay_signature
#         }
#         razorpay_client.utility.verify_payment_signature(params_dict)

#         # 2. Check Amount & Assign Credits
#         order_info = razorpay_client.order.fetch(data.razorpay_order_id)
#         amount_paid = order_info['amount'] / 100 
#         user_id = current_user['id']
#         credits_to_add = 0

#         # --- NEW: ENTERPRISE LOGIC (₹1 Payment) ---
#         if amount_paid == 1:
#             credits_to_add = 50000
            
#             # Calculate Expiry (Now + 90 Days)
#             end_date = datetime.now(timezone.utc) + timedelta(days=90)
            
#             # Insert/Update the Separate Subscription Table
#             supabase.table('enterprise_subscriptions').upsert({
#                 "user_id": user_id,
#                 "end_date": end_date.isoformat(),
#                 "plan_type": "student_quarterly"
#             }).execute()
            
#             print(f"Enterprise Subscription Activated for {user_id} until {end_date}")

#         # --- STANDARD PACKAGES ---
#         elif amount_paid == 49: credits_to_add = 20
#         elif amount_paid == 199: credits_to_add = 200
#         elif amount_paid == 999: credits_to_add = 1500
        
#         # 3. Update User's Credit Balance
#         profile = supabase.table('users').select("graph_credits").eq('id', user_id).execute()
#         current_credits = profile.data[0].get('graph_credits', 0) if profile.data else 0
#         new_total = current_credits + credits_to_add
        
#         supabase.table('users').update({"graph_credits": new_total}).eq('id', user_id).execute()

#         return {"status": "success", "new_balance": new_total}

#     except Exception as e:
#         print(f"--- VERIFY PAYMENT ERROR: {e} ---")
#         raise HTTPException(status_code=500, detail="Error verifying payment")


# @router.post("/use-credit")
# async def use_credit(current_user: dict = Depends(get_current_user)):
#     if not current_user:
#         raise HTTPException(status_code=401, detail="Not authenticated")

#     user_id = current_user['id']
    
#     # --- NEW: CHECK EXPIRATION FIRST ---
#     try:
#         # Check if they have an enterprise subscription
#         sub_response = supabase.table('enterprise_subscriptions').select("*").eq('user_id', user_id).execute()
        
#         if sub_response.data:
#             subscription = sub_response.data[0]
#             expiry_str = subscription['end_date'].replace('Z', '+00:00')
#             expiry_date = datetime.fromisoformat(expiry_str)
            
#             # If Today > Expiry Date -> EXPIRED!
#             if datetime.now(timezone.utc) > expiry_date:
#                 print(f"Subscription expired for {user_id}. Resetting credits.")
                
#                 # Reset credits to 0 (or 0)
#                 supabase.table('users').update({"graph_credits": 0}).eq('id', user_id).execute()
                
#                 return {"status": "failed", "error": "Your 3-month student plan has expired. Please renew."}
#     except Exception as e:
#         print(f"Subscription check warning: {e}")

#     # --- NORMAL CREDIT DEDUCTION ---
#     current_credits = current_user.get('graph_credits', 0)

#     if current_credits <= 0:
#         return {"status": "failed", "error": "No credits remaining"}

#     new_total = current_credits - 1

#     try:
#         supabase.table('users').update({
#             "graph_credits": new_total
#         }).eq('id', user_id).execute()
        
#         return {"status": "success", "new_credits": new_total}
#     except Exception as e:
#         return {"status": "error", "message": "Failed to log credit use"}

# ====================
# IMPORTS
# ====================
from fastapi import APIRouter, Depends, HTTPException, Response, Request, Header
from supabase import Client
import os
import razorpay
import json
from supabase import create_client, Client
import supabase
from .auth import get_current_user # Import your user dependency

router = APIRouter()
# ====================
# ENDPOINTS
# ====================

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
 
from dotenv import load_dotenv
load_dotenv()
from app.api import upload, chart, auth, credits # <-- ADD 'credits' HERE
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import pandas as pd
from fastapi import Depends
from fastapi.responses import RedirectResponse
from app.api.auth import get_current_user # This imports your security guard
import time
# from supabase import create_client
from supabase import create_client, Client
from app.api import upload, chart, auth  # <-- This line now works because auth.py exists
from app.services.file_handler import get_dataframe
import razorpay
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from razorpay.errors import SignatureVerificationError
import os
# 1. Define the data model for verification
class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
# from fastapi.responses import JSONResponse
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# =================================================================
#  2. APP INITIALIZATION & CONFIGURATION
# =================================================================
# Initialize the FastAPI application
app = FastAPI(title="Morph-AI Backend")

# Configure Jinja2 to find HTML templates in the "templates" directory
templates = Jinja2Templates(directory="templates")

# Add CORS Middleware to allow the frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

#  3. API ROUTERS

# Include routers from other files (upload.py, chart.py)
# API-specific routes (data upload, chart generation, etc.)
app.include_router(upload.router, prefix="/api")
app.include_router(chart.router, prefix="/api")
# Top-level routes for authentication (login, signup, logout)
app.include_router(auth.router) # <-- CORRECTED: The "/api" prefix is removed


app.include_router(credits.router, prefix="/api") # <-- ADD THIS LINE
#  4. CORE API ENDPOINTS
@app.get("/api/summary")
def get_summary():
    """
    Calculates summary statistics and identifies column types from the uploaded data.
    """
    df = get_dataframe()
    if df is None or df.empty:
        return JSONResponse(content={"error": "No data available to summarize."}, status_code=404)

    try:
        numeric_columns = df.select_dtypes(include='number').columns.tolist()
        
        categorical_columns = []
        for col in df.select_dtypes(include=['object', 'category']).columns:
            if df[col].nunique() < 50:
                categorical_columns.append(col)
        total_sales = float(pd.to_numeric(df["Sales"], errors='coerce').sum()) if "Sales" in df.columns else 0
        avg_profit = float(pd.to_numeric(df["Profit"], errors='coerce').mean()) if "Profit" in df.columns else 0
        max_profit = float(pd.to_numeric(df["Profit"], errors='coerce').max()) if "Profit" in df.columns else 0
        min_profit = float(pd.to_numeric(df["Profit"], errors='coerce').min()) if "Profit" in df.columns else 0
        summary_data = {
            "total_sales": total_sales,
            "avg_profit": avg_profit,
            "max_profit": max_profit,
            "min_profit": min_profit,
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns
        }
        return JSONResponse(content=summary_data)
    except Exception as e:
        return JSONResponse(content={"error": f"An error occurred during summary calculation: {str(e)}"}, status_code=500)

# This route serves the main page when you visit the root URL
@app.get("/", response_class=HTMLResponse)
async def get_homepage(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# Routes for all other pages in the application
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/analytics", response_class=HTMLResponse)
async def get_analytics(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})
    
@app.get("/history", response_class=HTMLResponse)
async def get_history(request: Request, current_user: dict = Depends(get_current_user)):
    # This is the security check
    if not current_user:
        # If the guard finds no logged-in user, send them to the login page
        return RedirectResponse(url="/login")

    # If the user is logged in, show the history page
    return templates.TemplateResponse("history.html", {"request": request, "user": current_user})

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
    
@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})
@app.get("/users/me")
async def read_current_user():
    return JSONResponse(content={"loggedIn": False})

@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})
    
@app.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})
# In backend/main.py

# ... (all your other code and routes)

@app.get("/terms", response_class=HTMLResponse)
async def get_terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def get_privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/refunds", response_class=HTMLResponse)
async def get_refunds_page(request: Request):
    return templates.TemplateResponse("refunds.html", {"request": request})

@app.get("/shipping", response_class=HTMLResponse)
async def get_shipping_page(request: Request):
    return templates.TemplateResponse("shipping.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
async def get_contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})
# =================================================================
#  PAYMENT & CREDITS LOGIC (Dynamic Pricing)
# =================================================================

class OrderRequest(BaseModel):
    amount: int  # Accepts 49, 199, or 999

# In main.py - REPLACE your old create-order function with this:

class OrderRequest(BaseModel):
    amount: int  # <--- This allows the frontend to send 49, 199, or 999

@app.post("/api/create_order")
async def create_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
    try:
        # 1. Security Check
        allowed_prices = [49, 199, 999] 
        if request.amount not in allowed_prices:
            raise HTTPException(status_code=400, detail="Invalid price package")

        # 2. Create Razorpay Order
        # FIX: We use current_user['id'][:6] to take only the first 6 letters
        data = {
            "amount": request.amount * 100,
            "currency": "INR",
            "receipt": f"rcpt_{current_user['id'][:6]}_{int(time.time())}", 
            "notes": {
                "user_id": current_user['id'],
                "plan_price": request.amount 
            }
        }
        order = client.order.create(data=data)
        return order

    except Exception as e:
        print(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/verify_payment") # Note: Changed from verify-payment to verify_payment
async def verify_payment(data: PaymentVerification):
    try:
        # 1. Verify Signature
        params_dict = {
            'razorpay_order_id': data.razorpay_order_id,
            'razorpay_payment_id': data.razorpay_payment_id,
            'razorpay_signature': data.razorpay_signature
        }
        client.utility.verify_payment_signature(params_dict)

        # 2. Fetch Order Details to confirm amount
        order_info = client.order.fetch(data.razorpay_order_id)
        amount_paid = order_info['amount'] / 100  # Convert paise back to Rupees
        user_id = order_info['notes']['user_id']

        # 3. Determine Credits based on Price
        credits_to_add = 0
        if amount_paid == 49:
            credits_to_add = 20
        elif amount_paid == 199:
            credits_to_add = 200
        elif amount_paid == 999:
            credits_to_add = 1500
        
        # 4. Update Database (Supabase)
        # Fetch current credits first
        response = supabase.table("users").select("credits").eq("id", user_id).execute()
        
        # Handle case where user might not have a credit entry yet
        if response.data:
            current_credits = response.data[0]['credits'] or 0
            new_balance = current_credits + credits_to_add
            
            # Push new balance to DB
            supabase.table("users").update({"credits": new_balance}).eq("id", user_id).execute()
        else:
            # Fallback (should typically not happen for logged in users)
            print(f"User {user_id} not found in DB during credit update.")

        return {"status": "success", "new_balance": new_balance, "added": credits_to_add}

    except SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        print(f"Payment Verification Failed: {e}")
        raise HTTPException(status_code=500, detail="Verification Process Failed")    
from fastapi.responses import FileResponse

@app.get("/robots.txt")
async def get_robots():
    return FileResponse("robots.txt")

# Add this import at the top
from fastapi.responses import FileResponse

# Add this route
@app.get("/sitemap.xml")
async def get_sitemap():
    return FileResponse("sitemap.xml")

# Import the new logic
from app.api.analytics import calculate_data_health, generate_forecast, segment_customers
# (Or just 'import analytics' if in same folder)

# --- 1. Health Check Endpoint ---
@app.post("/api/analyze/health")
async def analyze_health(request: Request):
    data = await request.json()
    # Convert JSON back to DataFrame
    df = pd.DataFrame(data['rows']) 
    result = calculate_data_health(df)
    return result

# --- 2. Forecast Endpoint ---
@app.post("/api/analyze/forecast")
async def get_forecast(request: Request):
    data = await request.json()
    df = pd.DataFrame(data['rows'])
    date_col = data.get('date_col')
    value_col = data.get('value_col')
    
    return generate_forecast(df, date_col, value_col)
from dotenv import load_dotenv
load_dotenv()
from app.api import upload, chart, auth, credits # <-- ADD 'credits' HERE
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import pandas as pd
import numpy as np
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
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from app.services.file_handler import process_uploaded_file # <-- Import the new function
from io import BytesIO

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
@app.head("/")  
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
        allowed_prices = [1, 49, 199, 999] 
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
        if amount_paid == 1:          # <--- ENTERPRISE LOGIC ADDED
            credits_to_add = 50000
        elif amount_paid == 49:
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

# For reset or fogot password
# Pass the keys to the template
@app.get("/forgot-password", response_class=HTMLResponse)
async def get_forgot_password(request: Request):
    return templates.TemplateResponse("forgot_password.html", {
        "request": request, 
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_key": os.environ.get("SUPABASE_KEY") # Ensure this is the ANON key in your .env
    })

@app.get("/reset-password", response_class=HTMLResponse)
async def get_reset_password(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request})

@app.post("/api/process-file")
async def process_file(
    file: UploadFile = File(...), 
    sheet: str = Form(None)  # New optional parameter
):
    try:
        contents = await file.read()
        file_bytes = BytesIO(contents)
        df = None
        
        # 1. Handle Excel Files
        if file.filename.endswith(('.xlsx', '.xls')):
            # Load the Excel file wrapper to check sheet names first
            xls = pd.ExcelFile(file_bytes)
            sheet_names = xls.sheet_names
            
            # CASE A: Multiple Sheets found & User hasn't chosen one yet
            if len(sheet_names) > 1 and not sheet:
                return {
                    "status": "multi_sheet", 
                    "sheets": sheet_names,
                    "message": "Multiple sheets found."
                }
            
            # CASE B: User selected a sheet OR there is only one sheet
            target_sheet = sheet if sheet else 0
            df = pd.read_excel(file_bytes, sheet_name=target_sheet)

        # 2. Handle CSV Files
        elif file.filename.endswith('.csv'):
            # Try different encodings to avoid errors
            try:
                # Read without header to look at raw data
                df_temp = pd.read_csv(file_bytes, header=None, encoding='utf-8')
            except UnicodeDecodeError:
                file_bytes.seek(0)
                df_temp = pd.read_csv(file_bytes, header=None, encoding='ISO-8859-1')
            max_non_nulls = 0
            header_row_index = 0
            
            for i in range(min(50, len(df_temp))):
                non_null_count = df_temp.iloc[i].count()
                if non_null_count > max_non_nulls:
                    max_non_nulls = non_null_count
                    header_row_index = i
            
            # 2. Reload the CSV using the detected header
            file_bytes.seek(0) # Reset pointer
            try:
                df = pd.read_csv(file_bytes, header=header_row_index, encoding='utf-8')
            except UnicodeDecodeError:
                file_bytes.seek(0)
                df = pd.read_csv(file_bytes, header=header_row_index, encoding='ISO-8859-1')

        else:
            return JSONResponse(status_code=400, content={"detail": "Invalid file type. Please upload CSV or Excel."})

       

        if df is None:
            return JSONResponse(status_code=400, content={"detail": "Invalid file."})

        # --- 3. JSON SAFETY BLOCK (THE FIX) ---
        # This prevents the "500 Internal Server Error"
        
        # A. Remove columns that are 100% empty (Safe cleanup)
        df = df.dropna(axis=1, how='all')

        # B. Replace Infinity with 0
        df = df.replace([np.inf, -np.inf], 0)

        # C. Replace NaN with None (This is what JSON needs)
        # We assume Object type to allow None values in numeric columns
        df = df.astype(object)
        df = df.where(pd.notnull(df), None)

        return {
            "status": "success",
            "headers": df.columns.tolist(),
            "data": df.to_dict(orient='records')
        }
    except Exception as e:
        print(f"Upload Error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})
    # --- ADD THIS TO main.py ---



def perform_cleaning(df):
    """
    Smart Cleaning with Correct "Rows Removed" Count.
    1. Finds & Promotes Header (Does not count this as 'removed').
    2. Deletes ONLY true junk rows.
    """
    initial_rows = len(df)
    header_fixed = False # Flag to track if we moved a header

    # --- 1. SMART HEADER DETECTION ---
    first_col = str(df.columns[0])
    if first_col.startswith('Unnamed') or "Sample" in first_col or "Data" in first_col:
        
        best_row_index = -1
        max_score = 0
        keywords = ['id', 'name', 'date', 'price', 'cost', 'stock', 'sku', 'total', 'sales', 'profit', 'category']
        
        for i in range(min(20, len(df))):
            row = df.iloc[i]
            row_str = str(row.tolist()).lower()
            text_count = sum(1 for val in row if isinstance(val, str) and len(str(val).strip()) > 0)
            keyword_bonus = sum(5 for k in keywords if k in row_str)
            
            if (text_count + keyword_bonus) > max_score:
                max_score = text_count + keyword_bonus
                best_row_index = i
        
        # Promote the winner row to Header
        if best_row_index != -1 and max_score > 2:
            new_header = df.iloc[best_row_index]
            df = df.iloc[best_row_index + 1:] 
            
            cleaned_columns = []
            for i, val in enumerate(new_header):
                if pd.isna(val) or str(val).strip() == "":
                    cleaned_columns.append(f"Column_{i+1}")
                else:
                    cleaned_columns.append(str(val).strip())
            df.columns = cleaned_columns
            df = df.reset_index(drop=True)
            header_fixed = True # We moved a row to header!

    # --- 2. SAFE CLEANING ---
    # Remove "Unnamed" columns only if safe
    valid_cols = [c for c in df.columns if not str(c).startswith('Unnamed') and not str(c).startswith('Column_')]
    if len(valid_cols) > 0:
        df = df[valid_cols]

    # Drop Duplicates & Empty Rows
    df = df.drop_duplicates()
    df = df.dropna(how='all') 
    
    # JSON Safety
    df = df.fillna("") 
    df = df.replace([np.inf, -np.inf], 0)

    # --- 3. CALCULATE "TRUE" REMOVED ROWS ---
    final_rows = len(df)
    rows_removed = initial_rows - final_rows
    
    # FIX: If we promoted a header, don't count it as "Removed data"
    if header_fixed:
        rows_removed -= 1
        
    # Ensure we never show negative numbers
    rows_removed = max(0, rows_removed)
    
    return df, rows_removed
@app.post("/api/clean-data")
async def clean_data_endpoint(request: Request):
    try:
        data = await request.json()
        df = pd.DataFrame(data['rows'])
        
        cleaned_df, rows_removed = perform_cleaning(df)
        
        return {
            "status": "success",
            "rows_removed": rows_removed,
            "headers": cleaned_df.columns.tolist(), # <--- ADD THIS LINE !!!
            "data": cleaned_df.to_dict(orient='records')
        }
    except Exception as e:
        print(f"Clean Error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})
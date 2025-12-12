import pandas as pd
from fastapi import UploadFile
from io import BytesIO
DATAFRAME: pd.DataFrame | None = None

def calculate_all_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates all metrics if the required columns exist in the DataFrame.
    This function is adapted from your metrics_calculator.py.
    """
    print("Calculating extended metrics...")
    
    if "Date" in df.columns:
        try:
            df["Date"] = pd.to_datetime(df["Date"])
        except Exception as e:
            print(f"Could not parse Date column: {e}")

    # Ratios & Percentages
    if "Profit" in df.columns and "Sales" in df.columns:
        df["Profit_Margin_%"] = (df["Profit"] / df["Sales"]) * 100
    if "Sales" in df.columns and "Cost" in df.columns:
        df["Gross_Margin_%"] = ((df["Sales"] - df["Cost"]) / df["Sales"]) * 100
    if "Conversions" in df.columns and "Customers" in df.columns:
        df["Conversion_Rate_%"] = (df["Conversions"] / df["Customers"]) * 100
    if "Retained_Customers" in df.columns and "Customers" in df.columns:
        df["Retention_Rate_%"] = (df["Retained_Customers"] / df["Customers"]) * 100
        df["Churn_Rate_%"] = 100 - df["Retention_Rate_%"]
    
    # Operational Metrics
    if "Resolution_Time_Hours" in df.columns and "Resolved_Tickets" in df.columns:
        df["Avg_Resolution_Time"] = df["Resolution_Time_Hours"] / df["Resolved_Tickets"]
    if "Employee_Worked_Hours" in df.columns and "Employee_Available_Hours" in df.columns:
        df["Utilization_%"] = (df["Employee_Worked_Hours"] / df["Employee_Available_Hours"]) * 100
        
    # Customer & Marketing Metrics
    if "Customer_Lifetime_Revenue" in df.columns:
        df["CLV"] = df["Customer_Lifetime_Revenue"]
    if "Customer_Acquisition_Cost" in df.columns:
        df["CAC"] = df["Customer_Acquisition_Cost"]
    if "Revenue" in df.columns and "Marketing_Spend" in df.columns:
        df["ROI_%"] = ((df["Revenue"] - df["Marketing_Spend"]) / df["Marketing_Spend"]) * 100
    
    # Financial Metrics
    if "Net_Profit" in df.columns and "Revenue" in df.columns:
        df["Net_Profit_%"] = (df["Net_Profit"] / df["Revenue"]) * 100
    if "Operating_Income" in df.columns and "Revenue" in df.columns:
        df["Operating_Margin_%"] = (df["Operating_Income"] / df["Revenue"]) * 100

    # Clean up any potential infinite values from division by zero
    df.replace([float('inf'), float('-inf')], 0, inplace=True)
    df.fillna(0, inplace=True)

    print("Metrics calculation complete.")
    return df

async def save_file(file: UploadFile):
    """
    Reads an uploaded CSV/Excel file into a global pandas DataFrame
    and then calculates all derived metrics.
    """
    global DATAFRAME
    
    filename = file.filename
    content = await file.read()
    
    try:
        if filename.endswith(".csv"):
            DATAFRAME = pd.read_csv(BytesIO(content))
        elif filename.endswith((".xls", ".xlsx")):
            DATAFRAME = pd.read_excel(BytesIO(content))
        else:
            return {"success": False, "message": "Unsupported file format"}

        # <<< --- YAHAN PAR HUMNE METRICS CALCULATION KO CALL KIYA HAI --- >>>
        DATAFRAME = calculate_all_metrics(DATAFRAME)

        return {
            "success": True,
            "filename": filename,
            "size": len(content),
        }
    except Exception as e:
        DATAFRAME = None
        return {"success": False, "message": f"Error parsing file: {str(e)}"}

def get_dataframe() -> pd.DataFrame | None:
    """
    Returns the currently loaded DataFrame.
    """
    return DATAFRAME

import io

# ... (keep your existing get_dataframe function if it's there) ...

def process_uploaded_file(file_content: bytes, filename: str):
    """
    Smartly detects file type and returns a Pandas DataFrame.
    Supports: .csv, .xlsx, .xls, .json, .parquet
    """
    filename = filename.lower()
    
    try:
        df = None
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
            
        elif filename.endswith(('.xls', '.xlsx')):
            # Requires 'openpyxl' library installed
            df = pd.read_excel(io.BytesIO(file_content))
            
        elif filename.endswith('.json'):
            df = pd.read_json(io.BytesIO(file_content))
            
        elif filename.endswith('.parquet'):
            df = pd.read_parquet(io.BytesIO(file_content))
            
        return df

    except Exception as e:
        print(f"Error parsing file {filename}: {e}")
        return None
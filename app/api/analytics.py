import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.cluster import KMeans
from datetime import timedelta

# --- 1. HEALTH MONITOR ---
def calculate_data_health(df):
    """
    Analyzes the quality of the uploaded CSV.
    Returns a score (0-100) and a list of issues.
    """
    issues = []
    score = 100
    
    # Check 1: Empty Cells
    total_cells = df.size
    missing_cells = df.isnull().sum().sum()
    if missing_cells > 0:
        missing_pct = (missing_cells / total_cells) * 100
        score -= min(30, int(missing_pct * 2)) # Penalty
        issues.append(f"{int(missing_pct)}% of data is empty/missing.")

    # Check 2: Duplicate Rows
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        score -= 10
        issues.append(f"Found {duplicates} duplicate rows.")

    # Check 3: Column Quality
    if len(df.columns) < 2:
        score -= 40
        issues.append("Dataset has too few columns for analysis.")

    # Cap score
    score = max(0, score)
    
    status = "Healthy"
    if score < 50: status = "Critical"
    elif score < 80: status = "Needs Cleaning"

    return {
        "score": score,
        "status": status,
        "issues": issues
    }

# --- 2. AI FORECASTER (Linear Regression) ---
def generate_forecast(df, date_col, value_col, periods=3):
    """
    Predicts the next 3 months/periods using Linear Regression.
    """
    try:
        # Prepare Data
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=[date_col, value_col])
        
        # Group by Month (or smallest unit)
        df = df.sort_values(date_col)
        df['TimeIndex'] = np.arange(len(df))
        
        # Train AI Model
        X = df[['TimeIndex']].values
        y = df[value_col].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Predict Future
        last_index = df['TimeIndex'].max()
        future_indices = np.array([[last_index + i] for i in range(1, periods + 1)])
        predictions = model.predict(future_indices)
        
        # Return simplified data for frontend
        future_data = []
        last_date = df[date_col].max()
        
        for i, pred in enumerate(predictions):
            next_date = last_date + timedelta(days=30 * (i+1)) # Approx 1 month
            future_data.append({
                "date": next_date.strftime('%Y-%m-%d'),
                "value": round(float(pred), 2),
                "type": "forecast"
            })
            
        return {"success": True, "forecast": future_data}

    except Exception as e:
        return {"success": False, "error": str(e)}

# --- 3. CUSTOMER SEGMENTATION (K-Means) ---
def segment_customers(df, sales_col):
    """
    Groups data into 3 clusters: Low, Medium, High Value.
    """
    try:
        if len(df) < 5: return {"error": "Not enough data"}

        # Reshape for K-Means
        X = df[[sales_col]].fillna(0).values
        
        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        kmeans.fit(X)
        
        # Assign Labels (0, 1, 2)
        df['Cluster'] = kmeans.labels_
        
        # Map clusters to "Low/Med/High" based on average value
        cluster_map = {}
        for i in range(3):
            avg_val = df[df['Cluster'] == i][sales_col].mean()
            cluster_map[i] = avg_val
            
        # Sort clusters: Smallest avg = "Low", Largest avg = "High"
        sorted_clusters = sorted(cluster_map, key=cluster_map.get)
        
        labels = {
            sorted_clusters[0]: "Low Value",
            sorted_clusters[1]: "Medium Value",
            sorted_clusters[2]: "High Value"
        }
        
        # Return distribution for Pie Chart
        counts = df['Cluster'].map(labels).value_counts().to_dict()
        return {"success": True, "segments": counts}

    except Exception as e:
        return {"success": False, "error": str(e)}
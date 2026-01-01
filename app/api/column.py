from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.file_handler import get_dataframe

router = APIRouter()

@router.get("/columns")
async def get_columns():
    """
    Returns a list of column names from the uploaded DataFrame.
    """
    df = get_dataframe()
    if df is None:
        return JSONResponse(
            {"error": "No data file has been uploaded."},
            status_code=400,
        )
    
    # Return only numeric columns, as they are best for charting
    numeric_columns = df.select_dtypes(include='number').columns.tolist()
    
    return {"columns": numeric_columns}
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import tempfile
import shutil
from datetime import datetime
from typing import Optional, List
import json
import logging

from generator import generate_dataset

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BookDash Dataset Generator")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global variable to track temp files for cleanup (optional)
_temp_files_to_cleanup = []

def cleanup_temp_file(file_path: str):
    """Clean up temporary file after sending response"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.warning(f"Could not clean up {file_path}: {e}")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/api/generate")
async def generate_dataset_endpoint(
    background_tasks: BackgroundTasks,
    request: Request,
    client_name: str = Form(...),
    industry: str = Form(...),
    start_date: str = Form(...),
    months: int = Form(...),
    region: str = Form('mixed'),
    business_scale: str = Form('medium'),
    messiness: str = Form('none'),
    num_customers: int = Form(...),
    num_vendors: int = Form(...),
    num_products: int = Form(...),
    num_invoices: int = Form(0),
    num_sales_receipts: int = Form(0),
    pct_deposits_from_invoices: int = Form(70),
    invoice_pct_paid: int = Form(80),
    invoice_due_days: int = Form(15),
    bank_txn_per_month: int = Form(100),
    cc_txn_per_month: int = Form(100),
    cc_payment_frequency: str = Form("monthly"),
    include_savings_account: bool = Form(False),
    savings_transfer_per_month: int = Form(0),
    use_account_numbers: bool = Form(True),
    curveball_duplicate_deposits: int = Form(0),
    curveball_vendor_customer_conflict: bool = Form(True),
    curveball_questionable_expense_pct: int = Form(5),
    curveball_processor_fees: bool = Form(True),
    curveball_open_invoice_pct: int = Form(20),
    payment_processor: str = Form("none"),
    processor_fee_pct: float = Form(2.9),
    processor_fixed_fee: float = Form(0.3),
    us_only_enforced: bool = Form(True),
    currency: str = Form("USD"),
    state_bias: str = Form(""),
    outputs_csv: bool = Form(True),
    outputs_pdf_statements: bool = Form(True),
    outputs_pdf_briefing: bool = Form(True),
    bundle_zip: bool = Form(True),
    random_seed: int = Form(-1),
    briefing_file: Optional[UploadFile] = File(None),
    num_checking_accounts: int = Form(1),
    num_credit_cards: int = Form(1),
    num_savings_accounts: int = Form(0),
    error_chart_of_accounts: int = Form(0),
    error_products: int = Form(0),
    error_customers: int = Form(0),
    error_vendors: int = Form(0),
    error_invoices: int = Form(0),
    invoice_new_customers: int = Form(0),
    error_bank: int = Form(0),
    error_creditcard: int = Form(0),
    output_files: List[str] = Form(["customers", "vendors", "products", "invoices", "bank", "creditcard"])
):
    try:
        logger.info(f"Generating dataset for client: {client_name}")
        
        # Validate inputs
        if months < 3 or months > 12:
            raise HTTPException(status_code=400, detail="Months must be between 3 and 12")
        
        if not us_only_enforced:
            raise HTTPException(status_code=400, detail="US-only enforcement must be enabled")

        # Create a persistent temporary directory (not using TemporaryDirectory context manager)
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp directory: {temp_dir}")
        
        try:
            # Handle briefing file upload
            briefing_path = None
            if briefing_file and briefing_file.filename:
                briefing_path = os.path.join(temp_dir, "custom_briefing.txt")
                with open(briefing_path, "wb") as f:
                    content = await briefing_file.read()
                    f.write(content)
            
            # Auto-enable savings account if number > 0
            effective_include_savings = include_savings_account or (num_savings_accounts > 0)
            
            # Prepare configuration dictionary
            config = {
                "client_name": client_name,
                "industry": industry,
                "start_date": start_date,
                "months": months,
                "region": region,
                "business_scale": business_scale,
                "messiness": messiness,
                "num_customers": num_customers,
                "num_vendors": num_vendors,
                "num_products": num_products,
                "num_invoices": num_invoices,
                "num_sales_receipts": num_sales_receipts,
                "pct_deposits_from_invoices": pct_deposits_from_invoices,
                "invoice_pct_paid": invoice_pct_paid,
                "invoice_due_days": invoice_due_days,
                "bank_txn_per_month": bank_txn_per_month,
                "cc_txn_per_month": cc_txn_per_month,
                "cc_payment_frequency": cc_payment_frequency,
                "include_savings_account": effective_include_savings,
                "savings_transfer_per_month": savings_transfer_per_month,
                "use_account_numbers": use_account_numbers,
                "curveball_duplicate_deposits": curveball_duplicate_deposits,
                "curveball_vendor_customer_conflict": curveball_vendor_customer_conflict,
                "curveball_questionable_expense_pct": curveball_questionable_expense_pct,
                "curveball_processor_fees": curveball_processor_fees,
                "curveball_open_invoice_pct": curveball_open_invoice_pct,
                "payment_processor": payment_processor,
                "processor_fee_pct": processor_fee_pct,
                "processor_fixed_fee": processor_fixed_fee,
                "us_only_enforced": us_only_enforced,
                "currency": currency,
                "state_bias": state_bias,
                "outputs_csv": outputs_csv,
                "outputs_pdf_statements": outputs_pdf_statements,
                "outputs_pdf_briefing": outputs_pdf_briefing,
                "bundle_zip": bundle_zip,
                "random_seed": random_seed,
                "num_checking_accounts": num_checking_accounts,
                "num_credit_cards": num_credit_cards,
                "num_savings_accounts": num_savings_accounts,
                "output_files": output_files,
                "briefing_file": briefing_path,
                "error_counts": {
                    "chart_of_accounts": max(0, error_chart_of_accounts),
                    "products": max(0, error_products),
                    "customers": max(0, error_customers),
                    "vendors": max(0, error_vendors),
                    "invoices": max(0, error_invoices),
                    "bank_accounts": max(0, error_bank),
                    "credit_cards": max(0, error_creditcard)
                },
                "invoice_new_customers": max(0, invoice_new_customers)
            }

            # Map business_scale presets to default counts if user left values at 0 or blank
            scale_map = {
                'light': {'num_customers': 10, 'num_vendors': 10, 'num_invoices': 20, 'bank_txn_per_month': 100, 'cc_txn_per_month': 100},
                'medium': {'num_customers': 25, 'num_vendors': 25, 'num_invoices': 50, 'bank_txn_per_month': 250, 'cc_txn_per_month': 250},
                'heavy': {'num_customers': 50, 'num_vendors': 50, 'num_invoices': 100, 'bank_txn_per_month': 500, 'cc_txn_per_month': 500}
            }
            preset = scale_map.get(business_scale.lower())
            if preset:
                # Only set if the incoming numeric values look like placeholders (0 or None)
                if not num_customers or num_customers <= 0:
                    config['num_customers'] = preset['num_customers']
                if not num_vendors or num_vendors <= 0:
                    config['num_vendors'] = preset['num_vendors']
                if not num_invoices or num_invoices <= 0:
                    config['num_invoices'] = preset['num_invoices']
                if not bank_txn_per_month or bank_txn_per_month <= 0:
                    config['bank_txn_per_month'] = preset['bank_txn_per_month']
                if not cc_txn_per_month or cc_txn_per_month <= 0:
                    config['cc_txn_per_month'] = preset['cc_txn_per_month']
            
            # Generate dataset
            zip_path = generate_dataset(config, temp_dir)
            
            if not zip_path or not os.path.exists(zip_path):
                raise HTTPException(status_code=500, detail="Dataset generation failed")
            
            logger.info(f"Dataset generated successfully: {zip_path}")
            
            # Schedule cleanup of the entire temp directory after response is sent
            background_tasks.add_task(cleanup_temp_directory, temp_dir)
            
            # Return the generated zip file
            filename = f"{slugify(client_name)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            return FileResponse(
                zip_path,
                media_type='application/zip',
                filename=filename
            )
            
        except Exception as e:
            # Clean up temp directory on error
            cleanup_temp_directory(temp_dir)
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating dataset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def cleanup_temp_directory(temp_dir: str):
    """Clean up temporary directory"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Could not clean up {temp_dir}: {e}")

def slugify(s: str) -> str:
    """Convert string to filesystem-safe name"""
    valid_chars = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    s = s.lower().replace(' ', '_')
    return ''.join(ch for ch in s if ch in valid_chars)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
import time
import uuid
import requests
import datetime
import base64
from decimal import Decimal
from ..extensions import db
from ..models import Tenant

# In-memory store for simulated transactions: checkout_id -> {"status": "pending"|"success"|"failed"|"cancelled", "amount": X, "phone": Y, "receipt": Z, "created_at": time}
simulated_txs = {}

def get_mpesa_access_token(consumer_key: str, consumer_secret: str) -> str:
    """Fetches access token from Safaricom Daraja API."""
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        r = requests.get(url, auth=(consumer_key, consumer_secret), timeout=10)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        print(f"Failed to fetch M-Pesa token: {e}")
    return None

def initiate_stk_push(tenant_id: int, phone: str, amount: float) -> dict:
    """Initiates an STK Push payment request.
    If simulation mode is enabled, registers the request in simulated_txs.
    Otherwise, communicates with Safaricom Developer API.
    """
    tenant = db.session.get(Tenant, tenant_id)
    simulate_mode = tenant.mpesa_simulate if tenant else True

    # Normalize phone: convert 07xx/01xx to 254xx
    phone_clean = phone.strip()
    if phone_clean.startswith("0"):
        phone_clean = "254" + phone_clean[1:]
    elif phone_clean.startswith("+"):
        phone_clean = phone_clean[1:]
    elif not phone_clean.startswith("254"):
        phone_clean = "254" + phone_clean

    # If simulation is disabled and credentials are present, attempt real Safaricom STK Push
    if not simulate_mode and tenant and tenant.mpesa_shortcode and tenant.mpesa_consumer_key and tenant.mpesa_consumer_secret:
        shortcode = tenant.mpesa_shortcode
        consumer_key = tenant.mpesa_consumer_key
        consumer_secret = tenant.mpesa_consumer_secret
        passkey = tenant.mpesa_passkey or "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919" # Default sandbox passkey

        token = get_mpesa_access_token(consumer_key, consumer_secret)
        if not token:
            return {
                "success": False,
                "message": "Failed to authenticate with Safaricom Daraja API. Please check your Consumer Key and Secret."
            }

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        password_str = f"{shortcode}{passkey}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode()

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Sandbox STK Push parameters
        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount) if amount >= 1 else 1, # STK Push only allows integer KES amounts >= 1
            "PartyA": phone_clean,
            "PartyB": shortcode,
            "PhoneNumber": phone_clean,
            "CallBackURL": "https://sandbox.safaricom.co.ke/callback", # Dummy, we query status directly
            "AccountReference": f"INV-{uuid.uuid4().hex[:6].upper()}",
            "TransactionDesc": "POS Checkout"
        }

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            res_data = r.json()
            if r.status_code == 200 and res_data.get("ResponseCode") == "0":
                checkout_id = res_data.get("CheckoutRequestID")
                # Store the checkout locally to remember it's a real query
                simulated_txs[checkout_id] = {
                    "tenant_id": tenant_id,
                    "phone": phone_clean,
                    "amount": amount,
                    "status": "pending_real",
                    "receipt": None,
                    "created_at": time.time()
                }
                return {
                    "success": True,
                    "simulate": False,
                    "checkout_id": checkout_id,
                    "message": "STK Push prompt sent to phone. Awaiting your PIN."
                }
            else:
                error_msg = res_data.get("errorMessage") or res_data.get("ResponseDescription") or "STK request rejected."
                return {
                    "success": False,
                    "message": f"Safaricom API Error: {error_msg}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Network error during Safaricom STK Push: {str(e)}"
            }

    # Fallback/Simulation Mode
    checkout_id = f"ws_CO_{uuid.uuid4().hex[:16]}"
    simulated_txs[checkout_id] = {
        "tenant_id": tenant_id,
        "phone": phone_clean,
        "amount": amount,
        "status": "pending",
        "receipt": None,
        "created_at": time.time()
    }
    return {
        "success": True,
        "simulate": True,
        "checkout_id": checkout_id,
        "message": "STK Push request initiated successfully (Simulation Mode)."
    }

def check_stk_status(tenant_id: int, checkout_id: str) -> dict:
    """Checks the status of an active checkout request."""
    if checkout_id in simulated_txs:
        tx = simulated_txs[checkout_id]
        if tx["tenant_id"] != tenant_id:
            return {"success": False, "status": "not_found", "message": "Transaction request not found."}

        # If it is a real request, query the Safaricom Daraja API
        if tx["status"] == "pending_real":
            tenant = db.session.get(Tenant, tenant_id)
            if tenant and tenant.mpesa_shortcode and tenant.mpesa_consumer_key and tenant.mpesa_consumer_secret:
                shortcode = tenant.mpesa_shortcode
                consumer_key = tenant.mpesa_consumer_key
                consumer_secret = tenant.mpesa_consumer_secret
                passkey = tenant.mpesa_passkey or "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"

                token = get_mpesa_access_token(consumer_key, consumer_secret)
                if not token:
                    return {"success": True, "status": "pending", "message": "Awaiting Safaricom status check..."}

                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                password_str = f"{shortcode}{passkey}{timestamp}"
                password = base64.b64encode(password_str.encode()).decode()

                url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                payload = {
                    "BusinessShortCode": shortcode,
                    "Password": password,
                    "Timestamp": timestamp,
                    "CheckoutRequestID": checkout_id
                }

                try:
                    r = requests.post(url, json=payload, headers=headers, timeout=10)
                    res_data = r.json()
                    result_code = res_data.get("ResultCode")
                    
                    if r.status_code == 200:
                        if result_code == "0":
                            # Successful transaction!
                            receipt = res_data.get("MpesaReceiptNumber") or f"MP{uuid.uuid4().hex[:8].upper()}"
                            tx["status"] = "success"
                            tx["receipt"] = receipt
                            return {
                                "success": True,
                                "status": "success",
                                "amount": tx["amount"],
                                "phone": tx["phone"],
                                "receipt": receipt,
                                "message": "Payment verified successfully!"
                            }
                        elif result_code is not None:
                            # User cancelled or transaction failed
                            # 1032 = Cancelled by user
                            status = "cancelled" if str(result_code) == "1032" else "failed"
                            tx["status"] = status
                            return {
                                "success": True,
                                "status": status,
                                "message": res_data.get("ResultDesc") or "Payment failed."
                            }
                except Exception as e:
                    print(f"Error querying status: {e}")

            # Fallback to pending if query didn't give a definitive success/failure response
            return {
                "success": True,
                "status": "pending",
                "message": "Awaiting customer payment PIN entry."
            }

        # Otherwise it is a simulated transaction
        return {
            "success": True,
            "status": tx["status"],
            "amount": tx["amount"],
            "phone": tx["phone"],
            "receipt": tx["receipt"],
            "message": f"Transaction status: {tx['status']}"
        }
            
    return {
        "success": False,
        "status": "not_found",
        "message": "Transaction request not found."
    }

def process_callback_simulation(checkout_id: str, outcome: str) -> bool:
    """Forces status update for simulated transactions."""
    if checkout_id in simulated_txs:
        tx = simulated_txs[checkout_id]
        if outcome == "success":
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            receipt = "S" + "".join(uuid.uuid4().hex[:9].upper())
            tx["status"] = "success"
            tx["receipt"] = receipt
        elif outcome == "insufficient_funds":
            tx["status"] = "failed"
            tx["receipt"] = None
        else:
            tx["status"] = "cancelled"
            tx["receipt"] = None
        return True
    return False

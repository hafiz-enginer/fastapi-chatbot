from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Shopping Chatbot API - Unified Endpoint")

# Environment variables
CATEGORY_API_URL = os.getenv("CATEGORY_API_URL")
ITEMS_API_BASE = os.getenv("ITEMS_API_BASE")
BILL_API_URL = os.getenv("BILL_API_URL")  # Adjust if needed


# ----- Models -----
class CartItem(BaseModel):
    name: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)


class UserDetails(BaseModel):
    name: str
    phone: str
    address: str
    payment_method: Optional[str] = None

    @validator('phone')
    def phone_valid(cls, v):
        if not (v.isdigit() and len(v) in [10, 11]):
            raise ValueError('Phone must be 10 or 11 digits')
        return v


class ChatRequest(BaseModel):
    action: str
    payload: Optional[Dict[str, Any]] = {}


# ----- In-memory session store (demo) -----
user_session: Optional[UserDetails] = None
cart: List[CartItem] = []


# ----- Helper functions -----
def fetch_categories():
    try:
        resp = requests.get(CATEGORY_API_URL)
        resp.raise_for_status()
        data = resp.json()
        return [cat["categoryName"].strip() for cat in data if cat.get("isEnable")]
    except Exception as e:
        return []


def fetch_items_by_category(cat_name: str):
    try:
        url = f"{ITEMS_API_BASE}/{cat_name.strip()}"
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return []


# ----- Unified chat endpoint -----
@app.post("/chat")
def chat(request: ChatRequest):
    global user_session, cart
    action = request.action.lower()
    payload = request.payload or {}

    if action == "greet":
        return {
            "message": "Assalamoalikum! 🙏\n🤖: Welcome! Please login to continue shopping.\n🤖: What's your name?"
        }

    if action == "login":
        try:
            user = UserDetails(**payload)
            user_session = user
            cart.clear()
            return {"message": f"Welcome {user.name}!", "user": user.dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ... rest of your existing code ...

    if action == "list_categories":
        categories = fetch_categories()
        if not categories:
            raise HTTPException(status_code=503, detail="Categories service unavailable")
        return {"categories": categories}

    if action == "list_items":
        category_name = payload.get("category_name")
        if not category_name:
            raise HTTPException(status_code=400, detail="Missing 'category_name' in payload")
        items = fetch_items_by_category(category_name)
        mapped_items = []
        for item in items:
            price = item.get("price") or item.get("sales") or 0
            mapped_items.append(
                {"name": item.get("itemName", "Unknown"), "price": price}
            )
        return {"items": mapped_items}

    if action == "add_to_cart":
        if not user_session:
            raise HTTPException(status_code=401, detail="User not logged in")
        try:
            item = CartItem(**payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        for existing_item in cart:
            if existing_item.name == item.name:
                existing_item.quantity += item.quantity
                return {"message": f"Updated {item.name} quantity to {existing_item.quantity}"}
        cart.append(item)
        return {"message": f"Added {item.quantity} x {item.name} to cart"}

    if action == "show_cart":
        if not cart:
            return {"message": "🛒 Your cart is empty."}
        total = sum(item.quantity * item.price for item in cart)
        items_summary = [
            {"name": i.name, "quantity": i.quantity, "price": i.price, "subtotal": i.quantity * i.price}
            for i in cart
        ]
        return {"items": items_summary, "total": total}

    if action == "checkout":
        if not user_session:
            raise HTTPException(status_code=401, detail="User not logged in")
        if not cart:
            raise HTTPException(status_code=400, detail="Cart is empty")
        pm = payload.get("payment_method")
        if pm not in ["Cash on Delivery", "Online Transfer"]:
            raise HTTPException(status_code=400, detail="Invalid payment method")

        user_session.payment_method = pm
        payload_bill = {
            "user": user_session.dict(),
            "items": [item.dict() for item in cart]
        }
        try:
            resp = requests.post(BILL_API_URL, json=payload_bill)
            resp.raise_for_status()
            bill_response = resp.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Billing API error: {e}")

        cart.clear()
        return {
            "message": "Checkout successful",
            "payment_method": pm,
            "bill": bill_response.get("bill", {})
        }

    if action == "logout":
        user_session = None
        cart.clear()
        return {"message": "Logged out and cart cleared."}

    raise HTTPException(status_code=400, detail="Invalid action")


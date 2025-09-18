import os
import threading
import requests
from fastapi import FastAPI
from openai import OpenAI
from dotenv import load_dotenv
import streamlit as st
import uvicorn
import difflib

# =========================================================
# STEP 1: Load Environment Variables & Initialize OpenAI Client
# =========================================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================================================
# STEP 2: Backend API Endpoints
# =========================================================

CAT_URL = os.getenv("CATEGORY_API_URL")
ITEM_URL = os.getenv("ITEMS_API_BASE")
BILL_API_URL = os.getenv("BILL_API_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# =========================================================
# STEP 3: Category Functions
# =========================================================
def get_categories():
    try:
        res = requests.get(CAT_URL)
        data = res.json()
        if isinstance(data, list):
            seen = set()
            unique = []
            for c in data:
                name = c["categoryName"].strip().lower()
                if name not in seen:
                    seen.add(name)
                    unique.append(c)
            return unique
        return []
    except Exception as e:
        print("ERROR get_categories:", e)
        return []

def smart_match_category(user_input, categories):
    user_input = user_input.strip().lower()
    category_names = [c["categoryName"] for c in categories]

    for c in categories:
        if c["categoryName"].lower() == user_input:
            return c

    closest = difflib.get_close_matches(user_input, [c.lower() for c in category_names], n=1, cutoff=0.6)
    if closest:
        for c in categories:
            if c["categoryName"].lower() == closest[0]:
                return c
    return None

# =========================================================
# STEP 4: Mart Knowledge Base & AI Helper
# =========================================================
mart_info = {
    "categories": ["Electronics", "Vegetables & Fruits", "Clothes"],
    "payment_delivery": "We provide payment via Cash on Delivery and deliver nationwide.",
    "about": "AITOPIA Shopping Mart is your friendly online store for Electronics, Fruits & Vegetables, and Clothes."
}

def get_ai_response(user_question, knowledge_base):
    context_text = f"""
    You are an assistant for a shopping mart. Answer only using the following info:

    Categories: {', '.join(knowledge_base['categories'])}
    Payment & Delivery: {knowledge_base['payment_delivery']}
    About: {knowledge_base['about']}

    If the question is unrelated, politely say you only answer about the mart.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": context_text},
            {"role": "user", "content": user_question}
        ]
    )
    return response.choices[0].message.content

# =========================================================
# =========================================================
# STEP 5: Handle Cart & Chat Commands (Implemented)
# =========================================================
def handle_cart_commands(msg):
    """
    msg: user input message
    Handles adding/removing items to/from cart, showing bill, and quantity updates.
    """
    cart = st.session_state["cart"]
    items = st.session_state.get("items", [])

    msg_lower = msg.lower()

    # --------- Show bill ---------
    if msg_lower in ["show bill", "bill"]:
        if not cart:
            st.chat_message("assistant").markdown("🛒 Your cart is empty.")
            return
        bill_msg = "🛒 **Your Cart:**\n"
        total = 0
        for name, info in cart.items():
            price = info["price"]
            qty = info["quantity"]
            subtotal = price * qty
            total += subtotal
            bill_msg += f"- {name}: {qty} x {price} Rs = {subtotal} Rs\n"
        bill_msg += f"**Total:** {total} Rs"
        st.chat_message("assistant").markdown(bill_msg)
        return

    # --------- Add item ---------
    if msg_lower.startswith("add "):
        parts = msg.split()
        if len(parts) >= 2:
            try:
                # Quantity detection
                if parts[1].isdigit():
                    qty = int(parts[1])
                    item_name = " ".join(parts[2:])
                else:
                    qty = 1
                    item_name = " ".join(parts[1:])

                # Find item in current category
                matched_item = None
                for it in items:
                    if it["itemName"].lower() == item_name.lower():
                        matched_item = it
                        break
                if not matched_item:
                    st.chat_message("assistant").markdown(f"❌ Item '{item_name}' not found in current category.")
                    return

                # Add to cart
                if matched_item["itemName"] in cart:
                    cart[matched_item["itemName"]]["quantity"] += qty
                else:
                    cart[matched_item["itemName"]] = {
                        "price": matched_item.get("price", 0),
                        "quantity": qty
                    }
                st.chat_message("assistant").markdown(f"✅ Added {qty} x {matched_item['itemName']} to your cart.")
            except Exception as e:
                st.chat_message("assistant").markdown(f"❌ Error adding item: {e}")

        # --------- Show running bill after addition ---------
        if cart:
            total = sum(cart[it]["price"] * cart[it]["quantity"] for it in cart)
            bill_lines = [f"- {it}: {cart[it]['quantity']} x {cart[it]['price']} = {cart[it]['quantity']*cart[it]['price']} Rs" for it in cart]
            bill_text = "\n".join(bill_lines) + f"\n\n💰 **Total:** {total} Rs"
            st.info(bill_text)
        return

    # --------- Suggest item to add if exact name matches ---------
    for it in items:
        if it["itemName"].lower() in msg_lower:
            st.chat_message("assistant").markdown(
                f"💡 Did you want to add **{it['itemName']}** to your cart? Type `add {it['itemName']}` to add 1 or `add 2 {it['itemName']}` to add 2 etc."
            )
            break


# =========================================================
# STEP 6: Streamlit Chatbot Interface
# =========================================================
def run_streamlit():
    st.title("🤖 AITOPIA Shopping Mart Assistant")

    # -------------------------
    # STEP 6a: Initialize session state
    # -------------------------
    if "user_info" not in st.session_state: st.session_state["user_info"] = {}
    if "messages" not in st.session_state: st.session_state["messages"] = []
    if "selected_cat" not in st.session_state: st.session_state["selected_cat"] = None
    if "items" not in st.session_state: st.session_state["items"] = []
    if "cart" not in st.session_state: st.session_state["cart"] = {}
    if "login_step" not in st.session_state: st.session_state["login_step"] = 0  # 0=name, 1=phone, 2=address, 3=logged in

    # -------------------------
    # STEP 6b: Show welcome message
    # -------------------------
    if not st.session_state["messages"]:
        st.session_state["messages"].append({
            "role": "assistant",
            "content": (
                "👋 Welcome to **AITOPIA Shopping Mart!**\n\n"
                "Let's start with some quick login details."
            )
        })

    # Display chat history
    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).markdown(msg["content"])

    # -------------------------
    # STEP 6c: Fetch categories from API
    # -------------------------
    categories = get_categories()
    available_cats = ", ".join([c["categoryName"] for c in categories if c["isEnable"]])

    # -------------------------
    # STEP 6d: Handle chat input
    # -------------------------
    if prompt := st.chat_input("Type your message here..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)
        msg = prompt.strip()

        # --------- Interactive Login Flow with Validation ---------
        if st.session_state["login_step"] < 3:
            if st.session_state["login_step"] == 0:
                if msg.replace(" ", "").isalpha():
                    st.session_state["user_info"]["name"] = msg
                    st.chat_message("assistant").markdown("📞 Please enter your phone number (starting with 03, 10-11 digits):")
                    st.session_state["login_step"] = 1
                else:
                    st.chat_message("assistant").markdown("❌ Name should only contain letters and spaces. Try again:")

            elif st.session_state["login_step"] == 1:
                digits = ''.join(filter(str.isdigit, msg))
                if (len(digits) in [10, 11]) and digits.startswith("03"):
                    st.session_state["user_info"]["phone"] = digits
                    st.chat_message("assistant").markdown("🏠 Please enter your address:")
                    st.session_state["login_step"] = 2
                else:
                    st.chat_message("assistant").markdown("❌ Mobile number must start with 03 and be 10 or 11 digits long. Try again:")

            elif st.session_state["login_step"] == 2:
                if msg:
                    st.session_state["user_info"]["address"] = msg
                    st.chat_message("assistant").markdown(
                        f"✅ Thanks {st.session_state['user_info']['name']}! You are now logged in and can start shopping.\n\n"
                        f"Available categories: {available_cats}\nType the category name to view items."
                    )
                    st.session_state["login_step"] = 3
                else:
                    st.chat_message("assistant").markdown("❌ Address cannot be empty. Try again:")

        else:
            # --------- Normal shopping/chat flow ---------
            selected_category = smart_match_category(msg.lower(), categories)
            if selected_category:
                st.session_state["selected_cat"] = selected_category
                st.session_state["items"] = []

                # --------- Fetch items dynamically for selected category ---------
                try:
                    items_res = requests.get(f"{ITEM_URL}/{selected_category['categoryName']}").json()
                    if isinstance(items_res, list) and items_res:
                        st.session_state["items"] = items_res
                        items_list = "\n".join(
                            [f"- {it['itemName']} ({it.get('price', 'N/A')} Rs)" for it in items_res])
                        ai_message = (
                            f"✅ Selected category: {selected_category['categoryName']}\n"
                            f"📦 Items available:\n{items_list}\n"
                            "Type `add <qty> <item>` to add to your cart.\n\n"
                            f"To view another category, type its name: {available_cats}"
                        )
                    else:
                        ai_message = f"✅ Selected category: {selected_category['categoryName']}\n⚠️ No items found.\n\nType another category name to switch."
                except Exception as e:
                    ai_message = f"⚠️ Error fetching items: {e}"

                st.chat_message("assistant").markdown(ai_message)

            else:
                # --------- Handle cart commands and suggestions ---------
                handle_cart_commands(msg)

                # --------- Handle cart commands & suggestions ---------
                handle_cart_commands(msg)

                # --------- If msg is neither category nor add command, give AI response ---------
                if not msg.startswith("add "):
                    response = get_ai_response(prompt, mart_info)
                    st.session_state["messages"].append({"role": "assistant", "content": response})
                    st.chat_message("assistant").markdown(response)

    # -------------------------
    # STEP 6e: Display logged-in user info
    # -------------------------
    if st.session_state.get("user_info") and st.session_state["login_step"] == 3:
        st.info(
            f"👤 Logged in as: {st.session_state['user_info']['name']} | "
            f"📞 {st.session_state['user_info']['phone']} | "
            f"🏠 {st.session_state['user_info']['address']}"
        )

    # -------------------------
    # STEP 6f: Display items for selected category (if any)
    # -------------------------
    if st.session_state["selected_cat"] and st.session_state["items"]:
        items_list = "\n".join([f"- {it['itemName']} ({it.get('price', 0)} Rs)" for it in st.session_state["items"]])
        st.chat_message("assistant").markdown(
            f"📦 Items in {st.session_state['selected_cat']['categoryName']}:\n{items_list}\n"
            "Type `add <qty> <item>` to add to your cart."
        )

# =========================================================
# STEP 7: Run FastAPI Backend
# =========================================================
app = FastAPI()

def start_backend():
    uvicorn.run(app, host="127.0.0.1", port=8000)

# =========================================================
# STEP 8: Start App (Backend + Streamlit)
# =========================================================
if __name__ == "__main__":
    threading.Thread(target=start_backend, daemon=True).start()
    run_streamlit()

# =========================================================
# STEP 9: Placeholder for future cart command handling
# =========================================================
# handle_cart_commands(msg) can be integrated here in future

# =========================================================
# STEP 10: End of Script / Notes
# =========================================================
# Script structured into 10 steps for clarity; no internal logic has been changed.

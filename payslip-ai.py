import os
import json
import base64
import requests
import pandas as pd
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types
from st_aggrid import AgGrid, GridOptionsBuilder

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LwMtUaX0C3VQf78Q_7qc4otCmDkrQ1qKDRjUBHTzBLug")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "AVO9NY26lf0s4mq1obuGoEVZIlZGDiIy5aM1twBl-ZJrECNI-4roBFEtdXQWHV2gPeMyI55nuD2ogtL0")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "EBXwruVaW1c2EGUBx_g6dOzs_ouIR0ROp8tygAvzqBIOhO0vxvTwwIp3YzuEpsbtMO51FnAMJpzDD3RU")
PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"

st.set_page_config(page_title="PaySplit AI - PayPal Agent", layout="wide")

# --- 1. PAYPAL SANDBOX API FUNCTIONS ---
def get_paypal_access_token():
    """Authenticates with PayPal Sandbox and returns an OAuth2 token."""
    url = f"{PAYPAL_BASE_URL}/v1/oauth2/token"
    auth = (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]

def create_paypal_order(person_name, amount_usd, description):
    """Creates a real PayPal Sandbox Order and returns the payer approval link."""
    token = get_paypal_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": f"split_{person_name.lower().replace(' ', '_')}",
                "description": f"Bill Split for {person_name}: {description[:100]}",
                "amount": {
                    "currency_code": "USD",
                    "value": f"{float(amount_usd):.2f}"
                }
            }
        ],
        "application_context": {
            "brand_name": "PaySplit AI Agent",
            "user_action": "PAY_NOW",
            "return_url": "https://example.com/payment-success",
            "cancel_url": "https://example.com/payment-cancel"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    order_data = response.json()
    
    approve_link = next(
        (link["href"] for link in order_data.get("links", []) if link["rel"] == "approve"),
        None
    )
    return order_data["id"], approve_link

def check_paypal_order_status(order_id):
    """Checks the real-time status of a PayPal Sandbox Order."""
    token = get_paypal_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("status", "UNKNOWN")

# --- 2. GEMINI VISION & SPLIT AGENT ---
def analyze_and_split_receipt(image: Image.Image, split_instructions: str):
    """Uses Gemini 3.8 Flash to extract receipt items and compute individual splits."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    You are an AI Financial Split-Pay Agent.
    1. Read the uploaded receipt or bill image carefully. Convert amounts to USD if needed or treat numbers as USD for payment processing.
    2. Read the user's split instructions: "{split_instructions}"
    3. Calculate exact shares (including proportional tax/tip if applicable) for each person mentioned.
    4. Return ONLY valid JSON matching this exact structure:
    {{
      "merchant": "Name of restaurant/store",
      "total_bill": 0.00,
      "items_detected": [
        {{"item": "Item name", "price": 0.00, "assigned_to": "Names"}}
      ],
      "splits": [
        {{"person": "Person Name", "amount_owed": 0.00, "items_summary": "Short summary of items"}}
      ]
    }}
    """
    
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

# --- 3. STREAMLIT UI ---
st.title("💸 PaySplit AI: Conversational Receipt & Split-Pay Agent")
st.caption("Powered by Gemini 3.8 Vision AI + PayPal Orders v2 API + AG Grid")

if "split_data" not in st.session_state:
    st.session_state.split_data = None
if "paypal_orders" not in st.session_state:
    st.session_state.paypal_orders = {}

col1, col2 = st.columns([1, 1.4])

with col1:
    st.subheader("1. Upload Receipt & Chat Instructions")
    uploaded_file = st.file_uploader("Upload a receipt or utility bill (JPG/PNG)", type=["jpg", "jpeg", "png"])
    
    default_prompt = "Split the bill between Bhuvan, Divyapradosh, and Alex. Bhuvan had the chicken dish, Divyapradosh had the paneer/veg items, and everyone shared the sides and tax equally."
    user_instructions = st.text_area("Tell the AI who had what:", value=default_prompt, height=100)
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded Receipt", use_container_width=True)
        
        if st.button("🤖 Analyze Receipt & Generate PayPal Links", type="primary"):
            with st.spinner("Gemini AI is parsing line items and generating PayPal Sandbox orders..."):
                try:
                    result = analyze_and_split_receipt(image, user_instructions)
                    st.session_state.split_data = result
                    st.session_state.paypal_orders = {}
                    
                    # Automatically create PayPal Sandbox Order for each person
                    for split in result.get("splits", []):
                        person = split["person"]
                        amt = split["amount_owed"]
                        summary = split["items_summary"]
                        if amt > 0:
                            order_id, link = create_paypal_order(person, amt, summary)
                            st.session_state.paypal_orders[person] = {
                                "order_id": order_id,
                                "approve_link": link,
                                "status": "CREATED"
                            }
                    st.success("Receipt analyzed and live PayPal Sandbox payment links generated!")
                except Exception as e:
                    st.error(f"Error: {e}")

with col2:
    st.subheader("2. Interactive Split Ledger & Live PayPal Checkout")
    if st.session_state.split_data:
        data = st.session_state.split_data
        st.markdown(f"**Merchant:** {data.get('merchant', 'Unknown')} | **Total Detected:** ${data.get('total_bill', 0.0):.2f}")
        
        # Display extracted items using AG Grid (qualifies for AG Grid Sponsor Prize!)
        st.markdown("#### Extracted Line Items (AG Grid View)")
        items_df = pd.DataFrame(data.get("items_detected", []))
        if not items_df.empty:
            gb = GridOptionsBuilder.from_dataframe(items_df)
            gb.configure_default_column(editable=True, sortable=True, filter=True)
            AgGrid(items_df, gridOptions=gb.build(), height=180, fit_columns_on_grid_load=True)
        
        st.markdown("#### Individual PayPal Payment Requests")
        if st.button("🔄 Refresh Payment Statuses from PayPal API"):
            for person, order_info in st.session_state.paypal_orders.items():
                new_status = check_paypal_order_status(order_info["order_id"])
                st.session_state.paypal_orders[person]["status"] = new_status
                
        for split in data.get("splits", []):
            person = split["person"]
            amt = split["amount_owed"]
            summary = split["items_summary"]
            order_info = st.session_state.paypal_orders.get(person, {})
            
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1.5])
                c1.markdown(f"**{person}**\n\n_{summary}_")
                c2.metric("Amount Owed", f"${amt:.2f}")
                if order_info:
                    status = order_info["status"]
                    c3.markdown(f"**Order ID:** `{order_info['order_id']}`  \n**Status:** `{status}`")
                    c3.link_button(f"💳 Pay ${amt:.2f} with PayPal", order_info["approve_link"])
    else:
        st.info("Upload a receipt on the left and click Analyze to generate itemized splits and live PayPal payment links.")
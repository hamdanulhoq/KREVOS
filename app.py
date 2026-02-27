import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import os

# ======================================================
# UNIT CONVERSION
# ======================================================
def to_base_unit(value, unit):
    conversion = {
        "kg": 1000,
        "gm": 1,
        "litre": 1000,
        "ml": 1,
        "pieces": 1
    }
    return value * conversion.get(unit, 1)

def base_unit_type(unit):
    if unit in ["kg","gm"]:
        return "gm"
    elif unit in ["litre","ml"]:
        return "ml"
    return "pieces"

# ======================================================
# CONFIG
# ======================================================
ADMIN_PASSWORD = "87654321"
PACKAGING_COST = 10
LOGO_PATH = "logo.png"

FIXED_STAFF_FOOD = 100
FIXED_MANAGER_SALARY = 450

# ======================================================
# DATABASE
# ======================================================
conn = sqlite3.connect("krevos.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS inventory(
item TEXT PRIMARY KEY,
quantity REAL,
unit TEXT,
total_cost REAL,
cost_per_unit REAL
)""")

c.execute("""CREATE TABLE IF NOT EXISTS menu(
dish TEXT PRIMARY KEY,
price REAL
)""")

c.execute("""CREATE TABLE IF NOT EXISTS recipes(
dish TEXT,
ingredient TEXT,
amount REAL,
unit TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS sales(
date TEXT,
dish TEXT,
qty INTEGER,
total REAL
)""")

c.execute("""CREATE TABLE IF NOT EXISTS expenses(
date TEXT,
category TEXT,
amount REAL,
note TEXT
)""")

conn.commit()

# ======================================================
# BILL / INVOICE
# ======================================================
def generate_bill(dish, qty, price, total):
    file = f"invoice_{datetime.now().timestamp()}.pdf"
    doc = SimpleDocTemplate(file, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    if os.path.exists(LOGO_PATH):
        elements.append(Image(LOGO_PATH, width=120, height=60))

    elements.append(Paragraph("<b>KREVOS – MEET YOUR CRAVINGS</b>", styles["Title"]))
    elements.append(Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M"), styles["Normal"]))
    elements.append(Spacer(1, 20))

    data = [
        ["Item", "Qty", "Unit Price", "Total"],
        [dish, qty, price, total]
    ]

    elements.append(Table(data))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Packaging: {PACKAGING_COST} Tk", styles["Normal"]))
    elements.append(Paragraph(f"<b>Grand Total: {total} Tk</b>", styles["Heading2"]))

    doc.build(elements)
    return file

# ======================================================
# FIXED DAILY COST (SAFE)
# ======================================================
def add_fixed_costs(staff_food, manager_salary):
    today = datetime.now().strftime("%Y-%m-%d")

    if staff_food:
        exists = pd.read_sql_query(
            "SELECT * FROM expenses WHERE date=? AND category='Staff Food'",
            conn, params=(today,)
        )
        if exists.empty:
            c.execute("INSERT INTO expenses VALUES (?,?,?,?)",
                      (today,"Staff Food",FIXED_STAFF_FOOD,"Daily fixed"))

    if manager_salary:
        exists = pd.read_sql_query(
            "SELECT * FROM expenses WHERE date=? AND category='Manager Salary'",
            conn, params=(today,)
        )
        if exists.empty:
            c.execute("INSERT INTO expenses VALUES (?,?,?,?)",
                      (today,"Manager Salary",FIXED_MANAGER_SALARY,"Daily fixed"))

    conn.commit()

# ======================================================
# INVENTORY
# ======================================================
def update_inventory(item, qty, unit, cost):
    df = pd.read_sql_query("SELECT * FROM inventory WHERE item=?", conn, params=(item,))
    if df.empty:
        cpu = cost / qty
        c.execute("INSERT INTO inventory VALUES (?,?,?,?,?)",
                  (item,qty,unit,cost,cpu))
    else:
        new_qty = df.iloc[0]["quantity"] + qty
        new_cost = df.iloc[0]["total_cost"] + cost
        cpu = new_cost / new_qty
        c.execute("""UPDATE inventory
        SET quantity=?, total_cost=?, cost_per_unit=?
        WHERE item=?""",(new_qty,new_cost,cpu,item))
    conn.commit()

# ======================================================
# AUTO INGREDIENT DEDUCTION
# ======================================================
def deduct_ingredients(dish, qty):
    r = pd.read_sql_query("SELECT * FROM recipes WHERE dish=?", conn, params=(dish,))
    for _, row in r.iterrows():
        used = row["amount"] * qty
        c.execute("""
        UPDATE inventory
        SET quantity = quantity - ?
        WHERE item=?
        """, (used, row["ingredient"]))
    conn.commit()

# ======================================================
# COST CALCULATION
# ======================================================
def calculate_dish_cost(dish):
    r = pd.read_sql_query("SELECT * FROM recipes WHERE dish=?", conn, params=(dish,))
    total = 0
    details = []

    for _,row in r.iterrows():
        inv = pd.read_sql_query(
            "SELECT cost_per_unit FROM inventory WHERE item=?",
            conn, params=(row["ingredient"],)
        )
        if not inv.empty:
            cost = inv.iloc[0]["cost_per_unit"] * row["amount"]
            total += cost
            details.append({
                "Ingredient": row["ingredient"],
                "Used Amount": row["amount"],
                "Cost": round(cost,2)
            })

    total += PACKAGING_COST
    return total, details

# ======================================================
# UI HEADER
# ======================================================
st.set_page_config(layout="wide")
st.markdown("## KREVOS – MEET YOUR CRAVINGS")
st.title("KREVOS Restaurant System V3")
st.caption("⚠ Demo system")

# ======================================================
# SIDEBAR (PROFESSIONAL NAV)
# ======================================================
with st.sidebar.expander("🧾 POS & Sales", True):
    show_pos = st.checkbox("POS Billing", True)
    show_daily = st.checkbox("Daily Reports", True)
    show_monthly = st.checkbox("Monthly Reports", True)

with st.sidebar.expander("📦 Inventory & Menu", True):
    show_inventory = st.checkbox("Bazar / Inventory", True)
    show_recipe = st.checkbox("Recipe Builder", True)
    show_menu_cost = st.checkbox("Menu Cost Analysis", True)

with st.sidebar.expander("💸 Expenses", True):
    show_expense = st.checkbox("Monthly Expense Manager", True)

with st.sidebar.expander("🔐 Admin", True):
    show_admin = st.checkbox("Admin Panel", True)

# ======================================================
# POS BILLING
# ======================================================
if show_pos:
    st.header("POS Billing")
    menu_items = pd.read_sql_query("SELECT * FROM menu", conn)

    if not menu_items.empty:
        dish = st.selectbox("Dish", menu_items["dish"])
        qty = st.number_input("Quantity",1)

        if st.button("Generate Bill"):
            price = menu_items[menu_items["dish"]==dish]["price"].values[0]
            total = price * qty

            deduct_ingredients(dish, qty)

            c.execute("INSERT INTO sales VALUES (?,?,?,?)",
                      (datetime.now().strftime("%Y-%m-%d"),dish,qty,total))
            conn.commit()

            file = generate_bill(dish,qty,price,total)
            with open(file,"rb") as f:
                st.download_button("Download Invoice",f,file_name=file)

            st.success("Sale completed")

# ======================================================
# DAILY REPORT + FIXED COST UI
# ======================================================
if show_daily:
    st.header("Daily Report & Fixed Costs")

    staff = st.checkbox("Add Staff Food (100 Tk)")
    manager = st.checkbox("Add Manager Salary (450 Tk)")

    if st.button("Apply Fixed Costs for Today"):
        add_fixed_costs(staff, manager)
        st.success("Fixed costs applied")

    today = datetime.now().strftime("%Y-%m-%d")
    sales = pd.read_sql_query("SELECT * FROM sales WHERE date=?",conn,params=(today,))
    exp = pd.read_sql_query("SELECT * FROM expenses WHERE date=?",conn,params=(today,))

    st.subheader("Income")
    st.dataframe(sales)

    st.subheader("Expenses")
    st.dataframe(exp)

    st.metric(
        "Net Profit Today",
        (sales["total"].sum() if not sales.empty else 0) -
        (exp["amount"].sum() if not exp.empty else 0)
    )

# ======================================================
# INVENTORY
# ======================================================
if show_inventory:
    st.header("Bazar Entry")
    suggestions = ["Chicken","Oil","Potato","Rice","Milk","Tomato"]
    item = st.selectbox("Quick Suggestion", suggestions)
    qty = st.number_input("Quantity",0.0)
    unit = st.selectbox("Unit",["kg","gm","litre","ml","pieces"])
    cost = st.number_input("Total Cost",0.0)

    if st.button("Add Inventory"):
        update_inventory(item,qty,unit,cost)
        c.execute("INSERT INTO expenses VALUES (?,?,?,?)",
                  (datetime.now().strftime("%Y-%m-%d"),"Bazar",cost,item))
        conn.commit()
        st.success("Inventory added")

    st.dataframe(pd.read_sql_query("SELECT * FROM inventory", conn))

# ======================================================
# RECIPE BUILDER
# ======================================================
if show_recipe:
    st.header("Recipe Builder")

    dishes = pd.read_sql_query("SELECT dish FROM menu", conn)
    ingredients = pd.read_sql_query("SELECT item FROM inventory", conn)

    if not dishes.empty and not ingredients.empty:
        dish = st.selectbox("Dish", dishes["dish"])
        ing = st.selectbox("Ingredient", ingredients["item"])
        amt = st.number_input("Amount Needed",0.0)
        unit = st.selectbox("Unit",["kg","gm","litre","ml","pieces"])

        if st.button("Add Ingredient"):
            c.execute("INSERT INTO recipes VALUES (?,?,?,?)",
                      (dish, ing, to_base_unit(amt,unit), base_unit_type(unit)))
            conn.commit()
            st.success("Recipe added")

    st.dataframe(pd.read_sql_query("SELECT rowid,* FROM recipes", conn))

    rid = st.number_input("Recipe rowid to delete",0)
    if st.button("Delete Recipe"):
        c.execute("DELETE FROM recipes WHERE rowid=?", (rid,))
        conn.commit()

# ======================================================
# MENU COST ANALYSIS
# ======================================================
if show_menu_cost:
    st.header("Menu Cost Analysis")
    menu_df = pd.read_sql_query("SELECT * FROM menu", conn)

    for _,row in menu_df.iterrows():
        cost, details = calculate_dish_cost(row["dish"])
        profit = row["price"] - cost

        st.subheader(row["dish"])
        st.table(pd.DataFrame(details))
        st.write("Making Cost:", round(cost,2))
        st.write("Selling Price:", row["price"])
        st.write("Estimated Profit:", round(profit,2))
        st.divider()

# ======================================================
# MONTHLY REPORT
# ======================================================
if show_monthly:
    st.header("Monthly Report")
    month = datetime.now().strftime("%Y-%m")

    sales = pd.read_sql_query("SELECT * FROM sales WHERE date LIKE ?", conn, params=(f"{month}%",))
    exp = pd.read_sql_query("SELECT * FROM expenses WHERE date LIKE ?", conn, params=(f"{month}%",))

    st.subheader("Income")
    st.dataframe(sales)
    st.subheader("Expenses")
    st.dataframe(exp)

# ======================================================
# MONTHLY EXPENSE MANAGER
# ======================================================
if show_expense:
    st.header("Add Monthly Expense")

    category = st.selectbox("Type",["Rent","Gas","Water","Utility","Salary","Others"])
    amount = st.number_input("Amount")
    note = st.text_input("Note")

    if st.button("Add Expense"):
        c.execute("INSERT INTO expenses VALUES (?,?,?,?)",
                  (datetime.now().strftime("%Y-%m-%d"),category,amount,note))
        conn.commit()
        st.success("Expense added")

# ======================================================
# ADMIN PANEL
# ======================================================
if show_admin:
    st.header("Admin Panel")
    pwd = st.text_input("Password", type="password")

    if pwd == ADMIN_PASSWORD:
        st.success("Admin Access Granted")

        st.subheader("Add / Update Menu")
        d = st.text_input("Dish Name")
        p = st.number_input("Price",0.0)

        if st.button("Save Menu"):
            c.execute("""
            INSERT INTO menu VALUES (?,?)
            ON CONFLICT(dish) DO UPDATE SET price=excluded.price
            """,(d,p))
            conn.commit()
            st.success("Menu saved")

        st.subheader("Edit Inventory")
        st.dataframe(pd.read_sql_query("SELECT * FROM inventory", conn))
        del_item = st.text_input("Item name to delete")
        if st.button("Delete Inventory Item"):
            c.execute("DELETE FROM inventory WHERE item=?", (del_item,))
            conn.commit()

        st.subheader("Edit Menu")
        st.dataframe(pd.read_sql_query("SELECT * FROM menu", conn))
        del_menu = st.text_input("Menu to delete")
        if st.button("Delete Menu Item"):
            c.execute("DELETE FROM menu WHERE dish=?", (del_menu,))
            conn.commit()
    else:
        st.warning("Admin login required")
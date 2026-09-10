import os
import enum
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Date, Enum, Numeric, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 1. Database Connection
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

# 2. Database Models
class ExpenseSource(str, enum.Enum):
    inside = "الداخل"
    cash_treasury = "عهدة Cash"
    insta_treasury = "عهدة Insta"

class PaymentMethod(str, enum.Enum):
    cash = "Cash"
    insta = "Insta"
    none = "None"

class TreasuryType(str, enum.Enum):
    cash = "عهدة Cash"
    insta = "عهدة Insta"

class MovementType(str, enum.Enum):
    addition = "إضافة"
    withdrawal = "سحب"

class Region(Base):
    __tablename__ = 'regions'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

class BusinessDay(Base):
    __tablename__ = 'business_days'
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    business_date = Column(Date, nullable=False)
    status = Column(String, default="OPEN")
    opening_inside = Column(Numeric(10, 2), default=0.00)
    opening_cash_treasury = Column(Numeric(10, 2), default=0.00)
    opening_insta_treasury = Column(Numeric(10, 2), default=0.00)
    closing_inside = Column(Numeric(10, 2), nullable=True)
    closing_cash_treasury = Column(Numeric(10, 2), nullable=True)
    closing_insta_treasury = Column(Numeric(10, 2), nullable=True)
    closed_at = Column(DateTime, nullable=True)

class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=True)
    is_active = Column(Boolean, default=True)

class ExpenseCategory(Base):
    __tablename__ = 'expense_categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    order_time = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False)
    price = Column(Numeric(10, 2), default=0.00)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    notes = Column(String, nullable=True)

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    person_entity = Column(String, nullable=False)
    expense_type = Column(String, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    source = Column(Enum(ExpenseSource), nullable=False)
    notes = Column(String, nullable=True)

class TreasuryMovement(Base):
    __tablename__ = 'treasury_movements'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    treasury_type = Column(Enum(TreasuryType), nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)

class Leave(Base):
    __tablename__ = 'leaves'
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    employee_name = Column(String, nullable=False)
    leave_date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)

if engine:
    Base.metadata.create_all(bind=engine)

# 3. FastAPI App Setup
app = FastAPI(title="Catchy Finance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    if not SessionLocal:
        raise HTTPException(status_code=500, detail="Database connection not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Schemas
class OrderIn(BaseModel):
    business_day_id: int
    order_time: str
    customer_name: Optional[str] = "بدون اسم"
    is_subscription: bool = False
    price: float = 0.0
    payment_method: str = "None"
    notes: Optional[str] = ""

class ExpenseIn(BaseModel):
    business_day_id: int
    person_entity: str
    expense_type: str
    amount: float
    source: str
    description: Optional[str] = ""

class TreasuryIn(BaseModel):
    business_day_id: int
    treasury_type: str
    amount: float
    description: Optional[str] = "تغذية عهدة"

class LeaveIn(BaseModel):
    region_id: int
    employee_name: str
    leave_date: str
    notes: Optional[str] = "إجازة"

# 4. API Endpoints
@app.get("/api/regions")
def get_regions(db: Session = Depends(get_db)):
    if db.query(Region).count() == 0:
        db.add_all([Region(name="الشروق"), Region(name="مدينتي")])
        db.commit()
    return db.query(Region).filter(Region.is_active == True).all()

@app.get("/api/shift")
def get_shift(region_id: int, date_str: str, db: Session = Depends(get_db)):
    t_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    current_day = db.query(BusinessDay).filter(
        BusinessDay.region_id == region_id, BusinessDay.business_date == t_date
    ).first()
    
    prev_closed = db.query(BusinessDay).filter(
        BusinessDay.region_id == region_id,
        BusinessDay.business_date < t_date,
        BusinessDay.status == "CLOSED"
    ).order_by(BusinessDay.business_date.desc()).first()

    if not current_day:
        current_day = BusinessDay(
            region_id=region_id, business_date=t_date, status="OPEN",
            opening_inside=prev_closed.closing_inside if prev_closed else 0,
            opening_cash_treasury=prev_closed.closing_cash_treasury if prev_closed else 0,
            opening_insta_treasury=prev_closed.closing_insta_treasury if prev_closed else 0
        )
        db.add(current_day)
        db.commit()
        db.refresh(current_day)
    elif current_day.status == "OPEN" and prev_closed:
        p_in = prev_closed.closing_inside or 0
        p_cash = prev_closed.closing_cash_treasury or 0
        p_insta = prev_closed.closing_insta_treasury or 0
        if (current_day.opening_inside != p_in or current_day.opening_cash_treasury != p_cash or current_day.opening_insta_treasury != p_insta):
            current_day.opening_inside = p_in
            current_day.opening_cash_treasury = p_cash
            current_day.opening_insta_treasury = p_insta
            db.commit()

    # Calculations
    day_id = current_day.id
    orders = db.query(Order).filter(Order.business_day_id == day_id).all()
    expenses = db.query(Expense).filter(Expense.business_day_id == day_id).all()
    movements = db.query(TreasuryMovement).filter(TreasuryMovement.business_day_id == day_id).all()

    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    insta_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.insta])
    total_rev = cash_rev + insta_rev

    exp_inside = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.inside])
    exp_cash_tr = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.cash_treasury])
    exp_insta_tr = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.insta_treasury])
    total_exp = exp_inside + exp_cash_tr + exp_insta_tr

    add_cash_tr = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.cash and m.movement_type == MovementType.addition])
    add_insta_tr = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.insta and m.movement_type == MovementType.addition])

    curr_inside = float(current_day.opening_inside or 0) + cash_rev - exp_inside
    curr_cash_tr = float(current_day.opening_cash_treasury or 0) + add_cash_tr - exp_cash_tr
    curr_insta_tr = float(current_day.opening_insta_treasury or 0) + add_insta_tr - exp_insta_tr
    total_resp = curr_inside + curr_cash_tr + curr_insta_tr

    return {
        "day": {
            "id": current_day.id,
            "date": current_day.business_date.strftime("%Y-%m-%d"),
            "status": current_day.status,
            "opening_inside": int(current_day.opening_inside or 0),
            "opening_cash_treasury": int(current_day.opening_cash_treasury or 0),
            "opening_insta_treasury": int(current_day.opening_insta_treasury or 0),
        },
        "revenue": {"cash": int(cash_rev), "insta": int(insta_rev), "total": int(total_rev)},
        "expenses_summary": {"inside": int(exp_inside), "cash_tr": int(exp_cash_tr), "insta_tr": int(exp_insta_tr), "total": int(total_exp)},
        "balances": {"inside": int(curr_inside), "cash_tr": int(curr_cash_tr), "insta_tr": int(curr_insta_tr), "total_responsibility": int(total_resp)},
        "orders": [{"id": o.id, "time": o.order_time, "customer": o.customer_name, "is_subscription": o.is_subscription, "price": int(o.price), "payment": o.payment_method.value, "notes": o.notes or ""} for o in orders],
        "expenses": [{"id": e.id, "person": e.person_entity, "type": e.expense_type, "amount": int(e.amount), "source": e.source.value, "notes": e.description or ""} for e in expenses]
    }

# Orders CRUD
@app.post("/api/orders")
def add_order(payload: OrderIn, db: Session = Depends(get_db)):
    pm = PaymentMethod.cash if payload.payment_method == "Cash" else (PaymentMethod.insta if payload.payment_method == "Insta" else PaymentMethod.none)
    price = payload.price if pm != PaymentMethod.none else 0.0
    o = Order(business_day_id=payload.business_day_id, order_time=payload.order_time, customer_name=payload.customer_name, is_subscription=payload.is_subscription, price=price, payment_method=pm, notes=payload.notes)
    db.add(o)
    db.commit()
    return {"status": "ok"}

@app.put("/api/orders/{order_id}")
def update_order(order_id: int, payload: OrderIn, db: Session = Depends(get_db)):
    o = db.query(Order).get(order_id)
    if not o: raise HTTPException(status_code=404, detail="Order not found")
    pm = PaymentMethod.cash if payload.payment_method == "Cash" else (PaymentMethod.insta if payload.payment_method == "Insta" else PaymentMethod.none)
    o.order_time = payload.order_time
    o.customer_name = payload.customer_name
    o.is_subscription = payload.is_subscription
    o.price = payload.price if pm != PaymentMethod.none else 0.0
    o.payment_method = pm
    o.notes = payload.notes
    db.commit()
    return {"status": "ok"}

@app.delete("/api/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db.query(Order).filter(Order.id == order_id).delete()
    db.commit()
    return {"status": "ok"}

# Expenses CRUD
@app.post("/api/expenses")
def add_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    src = ExpenseSource.inside if payload.source == "الداخل" else (ExpenseSource.cash_treasury if payload.source == "عهدة Cash" else ExpenseSource.insta_treasury)
    e = Expense(business_day_id=payload.business_day_id, person_entity=payload.person_entity, expense_type=payload.expense_type, amount=payload.amount, source=src, description=payload.description)
    db.add(e)
    db.commit()
    return {"status": "ok"}

@app.put("/api/expenses/{expense_id}")
def update_expense(expense_id: int, payload: ExpenseIn, db: Session = Depends(get_db)):
    e = db.query(Expense).get(expense_id)
    if not e: raise HTTPException(status_code=404, detail="Expense not found")
    src = ExpenseSource.inside if payload.source == "الداخل" else (ExpenseSource.cash_treasury if payload.source == "عهدة Cash" else ExpenseSource.insta_treasury)
    e.person_entity = payload.person_entity
    e.expense_type = payload.expense_type
    e.amount = payload.amount
    e.source = src
    e.description = payload.description
    db.commit()
    return {"status": "ok"}

@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    db.query(Expense).filter(Expense.id == expense_id).delete()
    db.commit()
    return {"status": "ok"}

# Shift Control
@app.post("/api/shift/{day_id}/close")
def close_shift(day_id: int, db: Session = Depends(get_db)):
    d = db.query(BusinessDay).get(day_id)
    if not d: raise HTTPException(status_code=404)
    # Calculate current balances
    orders = db.query(Order).filter(Order.business_day_id == day_id).all()
    expenses = db.query(Expense).filter(Expense.business_day_id == day_id).all()
    movements = db.query(TreasuryMovement).filter(TreasuryMovement.business_day_id == day_id).all()
    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    exp_in = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.inside])
    exp_c = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.cash_treasury])
    exp_i = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.insta_treasury])
    add_c = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.cash and m.movement_type == MovementType.addition])
    add_i = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.insta and m.movement_type == MovementType.addition])

    d.status = "CLOSED"
    d.closing_inside = float(d.opening_inside or 0) + cash_rev - exp_in
    d.closing_cash_treasury = float(d.opening_cash_treasury or 0) + add_c - exp_c
    d.closing_insta_treasury = float(d.opening_insta_treasury or 0) + add_i - exp_i
    d.closed_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}

@app.post("/api/shift/{day_id}/reopen")
def reopen_shift(day_id: int, db: Session = Depends(get_db)):
    d = db.query(BusinessDay).get(day_id)
    if not d: raise HTTPException(status_code=404)
    d.status = "OPEN"
    db.commit()
    return {"status": "ok"}

@app.post("/api/treasury-feed")
def add_treasury(payload: TreasuryIn, db: Session = Depends(get_db)):
    tt = TreasuryType.cash if payload.treasury_type == "عهدة Cash" else TreasuryType.insta
    m = TreasuryMovement(business_day_id=payload.business_day_id, treasury_type=tt, movement_type=MovementType.addition, amount=payload.amount, description=payload.description)
    db.add(m)
    db.commit()
    return {"status": "ok"}

# 5. Reports Engine (Executive BI)
@app.get("/api/reports")
def get_reports(start_date: str, end_date: str, region_id: Optional[int] = None, db: Session = Depends(get_db)):
    s_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    q = db.query(BusinessDay).filter(BusinessDay.business_date >= s_d, BusinessDay.business_date <= e_d)
    if region_id:
        q = q.filter(BusinessDay.region_id == region_id)
    days = q.all()
    day_ids = [d.id for d in days]
    if not day_ids:
        return {"empty": True}

    regions = db.query(Region).all()
    reg_map = {r.id: r.name for r in regions}
    day_map = {d.id: {"date": d.business_date.strftime("%Y-%m-%d"), "region": reg_map.get(d.region_id, "عام")} for d in days}

    # Revenue
    orders = db.query(Order).filter(Order.business_day_id.in_(day_ids)).all()
    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    insta_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.insta])
    total_rev = cash_rev + insta_rev

    # Branch comparisons
    branch_rev = []
    for r in regions:
        b_days = [d.id for d in days if d.region_id == r.id]
        if b_days:
            b_orders = [o for o in orders if o.business_day_id in b_days]
            c_r = sum([float(o.price) for o in b_orders if o.payment_method == PaymentMethod.cash])
            i_r = sum([float(o.price) for o in b_orders if o.payment_method == PaymentMethod.insta])
            branch_rev.append({"name": r.name, "cash": int(c_r), "insta": int(i_r), "total": int(c_r + i_r)})

    # Expenses & Separation Logic
    expenses = db.query(Expense).filter(Expense.business_day_id.in_(day_ids)).all()
    
    def is_deductible(t):
        s = str(t).strip()
        return ("سلف" in s) or ("مصروف" in s and "بنزين" not in s and "سكن" not in s)

    # Salary Deductions Pivot (Employee -> Branches -> Total)
    emp_deductions = {}
    opex_categories = {}
    all_employees = sorted(list(set([e.person_entity for e in expenses])))

    for e in expenses:
        info = day_map.get(e.business_day_id, {"date": "", "region": ""})
        amt = int(e.amount)
        if is_deductible(e.expense_type):
            if e.person_entity not in emp_deductions:
                emp_deductions[e.person_entity] = {"total": 0, "branches": {}}
            emp_deductions[e.person_entity]["total"] += amt
            b_name = info["region"]
            emp_deductions[e.person_entity]["branches"][b_name] = emp_deductions[e.person_entity]["branches"].get(b_name, 0) + amt
        else:
            opex_categories[e.expense_type] = opex_categories.get(e.expense_type, 0) + amt

    # Convert to list for UI
    salary_table = []
    for emp, data in emp_deductions.items():
        row = {"employee": emp, "total": data["total"]}
        for r_name in reg_map.values():
            row[r_name] = data["branches"].get(r_name, 0)
        salary_table.append(row)

    opex_table = [{"category": k, "amount": v} for k, v in sorted(opex_categories.items(), key=lambda x: x[1], reverse=True)]

    # Treasury totals
    in_exp = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.inside])
    cash_tr_exp = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.cash_treasury])
    insta_tr_exp = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.insta_treasury])

    return {
        "empty": False,
        "revenue": {"cash": int(cash_rev), "insta": int(insta_rev), "total": int(total_rev)},
        "branch_revenue": branch_rev,
        "salary_deductions": salary_table,
        "opex": opex_table,
        "opex_total": sum(opex_categories.values()),
        "treasury_sources": {"inside": int(in_exp), "cash_tr": int(cash_tr_exp), "insta_tr": int(insta_tr_exp)},
        "raw_expenses": [{"date": day_map.get(e.business_day_id, {}).get("date"), "branch": day_map.get(e.business_day_id, {}).get("region"), "person": e.person_entity, "type": e.expense_type, "amount": int(e.amount), "source": e.source.value, "notes": e.description or "", "is_deductible": is_deductible(e.expense_type)} for e in expenses]
    }

# 6. Leaves
@app.get("/api/leaves")
def get_leaves(db: Session = Depends(get_db)):
    regions = {r.id: r.name for r in db.query(Region).all()}
    leaves = db.query(Leave).order_by(Leave.leave_date.desc()).all()
    return [{"id": l.id, "employee": l.employee_name, "date": l.leave_date.strftime("%Y-%m-%d"), "branch": regions.get(l.region_id, "عام"), "notes": l.notes or "إجازة"} for l in leaves]

@app.post("/api/leaves")
def add_leave(payload: LeaveIn, db: Session = Depends(get_db)):
    l_date = datetime.strptime(payload.leave_date, "%Y-%m-%d").date()
    l = Leave(region_id=payload.region_id, employee_name=payload.employee_name, leave_date=l_date, notes=payload.notes)
    db.add(l)
    db.commit()
    return {"status": "ok"}

@app.delete("/api/leaves/{leave_id}")
def delete_leave(leave_id: int, db: Session = Depends(get_db)):
    db.query(Leave).filter(Leave.id == leave_id).delete()
    db.commit()
    return {"status": "ok"}

# 7. Metadata / Settings
@app.get("/api/meta")
def get_meta(db: Session = Depends(get_db)):
    emps = [e.name for e in db.query(Employee).filter(Employee.is_active == True).all()]
    cats = [c.name for c in db.query(ExpenseCategory).filter(ExpenseCategory.is_active == True).all()]
    if not cats:
        cats = ["سلفة", "مصروف شخصي", "بنزين", "مشتريات خامات", "سكن", "بوفيه", "تيبس"]
    return {"employees": sorted(list(set(emps))), "categories": sorted(list(set(cats)))}

@app.post("/api/employees")
def create_emp(name: str, region_id: int, db: Session = Depends(get_db)):
    if name.strip():
        db.add(Employee(name=name.strip(), region_id=region_id))
        db.commit()
    return {"status": "ok"}

@app.delete("/api/employees")
def remove_emp(name: str, db: Session = Depends(get_db)):
    db.query(Employee).filter(Employee.name == name).delete()
    db.commit()
    return {"status": "ok"}

@app.post("/api/categories")
def create_cat(name: str, db: Session = Depends(get_db)):
    if name.strip():
        db.add(ExpenseCategory(name=name.strip()))
        db.commit()
    return {"status": "ok"}

@app.delete("/api/categories")
def remove_cat(name: str, db: Session = Depends(get_db)):
    db.query(ExpenseCategory).filter(ExpenseCategory.name == name).delete()
    db.commit()
    return {"status": "ok"}

@app.post("/api/initial-balances")
def set_balances(region_id: int, date_str: str, inside: float, cash_tr: float, insta_tr: float, db: Session = Depends(get_db)):
    t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.region_id == region_id, BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(region_id=region_id, business_date=t_d, status="OPEN")
        db.add(day)
    day.opening_inside = inside
    day.opening_cash_treasury = cash_tr
    day.opening_insta_treasury = insta_tr
    db.commit()
    return {"status": "ok"}
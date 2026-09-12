import os
import enum
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Date, Enum, Numeric, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 1. الاتصال بقاعدة البيانات السحابية
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

# 2. القوائم الثابتة (Enums)
class ExpenseSource(str, enum.Enum):
    inside = "الداخل"
    cash_treasury = "عهدة Cash"
    insta_treasury = "عهدة Insta"

class PaymentMethod(str, enum.Enum):
    cash = "Cash"
    insta = "Insta"
    none = "None"

class TreasuryType(str, enum.Enum):
    inside = "الداخل"
    cash = "عهدة Cash"
    insta = "عهدة Insta"

class MovementType(str, enum.Enum):
    addition = "إضافة"
    withdrawal = "سحب"

# 3. جداول قاعدة البيانات المحكمة
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

class PurchaseCategory(Base):
    __tablename__ = 'purchase_categories'
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

class Penalty(Base):
    __tablename__ = 'penalties'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    employee_name = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(String, nullable=True)

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    purchase_date = Column(Date, nullable=False)
    category = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    source = Column(Enum(ExpenseSource), nullable=False)
    description = Column(String, nullable=True)

class TreasuryMovement(Base):
    __tablename__ = 'treasury_movements'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    treasury_type = Column(Enum(TreasuryType), nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)

class Settlement(Base):
    __tablename__ = 'settlements'
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False) # 'employee' or 'treasury'
    name = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    settlement_date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)

class Leave(Base):
    __tablename__ = 'leaves'
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    employee_name = Column(String, nullable=False)
    leave_date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)

if engine:
    Base.metadata.create_all(bind=engine)

# 4. إعداد السيرفر
app = FastAPI(title="Catchy Finance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    if not SessionLocal: raise HTTPException(status_code=500, detail="Database error")
    db = SessionLocal()
    try: yield db
    finally: db.close()

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

class PenaltyIn(BaseModel):
    business_day_id: int
    employee_name: str
    amount: float
    notes: Optional[str] = ""

class PurchaseIn(BaseModel):
    region_id: int
    business_day_id: int
    purchase_date: str
    category: str
    amount: float
    source: str
    description: Optional[str] = ""

class TreasuryIn(BaseModel):
    business_day_id: int
    treasury_type: str
    amount: float
    description: Optional[str] = "تغذية"

class SettlementIn(BaseModel):
    entity_type: str
    name: str
    amount: float
    settlement_date: str
    notes: Optional[str] = ""

class LeaveIn(BaseModel):
    region_id: int
    employee_name: str
    leave_date: str
    notes: Optional[str] = "إجازة"

# 5. نقاط الـ API
@app.get("/api/regions")
def get_regions(db: Session = Depends(get_db)):
    if db.query(Region).count() == 0:
        db.add_all([Region(name="الشروق"), Region(name="مدينتي")])
        db.commit()
    return db.query(Region).filter(Region.is_active == True).all()

@app.get("/api/shift")
def get_shift(region_id: int, date_str: str, db: Session = Depends(get_db)):
    t_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    current_day = db.query(BusinessDay).filter(BusinessDay.region_id == region_id, BusinessDay.business_date == t_date).first()
    prev_closed = db.query(BusinessDay).filter(BusinessDay.region_id == region_id, BusinessDay.business_date < t_date, BusinessDay.status == "CLOSED").order_by(BusinessDay.business_date.desc()).first()

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
        p_in, p_cash, p_insta = prev_closed.closing_inside or 0, prev_closed.closing_cash_treasury or 0, prev_closed.closing_insta_treasury or 0
        if current_day.opening_inside != p_in or current_day.opening_cash_treasury != p_cash or current_day.opening_insta_treasury != p_insta:
            current_day.opening_inside, current_day.opening_cash_treasury, current_day.opening_insta_treasury = p_in, p_cash, p_insta
            db.commit()

    day_id = current_day.id
    orders = db.query(Order).filter(Order.business_day_id == day_id).all()
    expenses = db.query(Expense).filter(Expense.business_day_id == day_id).all()
    purchases = db.query(Purchase).filter(Purchase.business_day_id == day_id).all()
    penalties = db.query(Penalty).filter(Penalty.business_day_id == day_id).all()
    movements = db.query(TreasuryMovement).filter(TreasuryMovement.business_day_id == day_id).all()

    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    insta_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.insta])
    total_rev = cash_rev + insta_rev

    exp_inside = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.inside]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.inside])
    exp_cash_tr = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.cash_treasury]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.cash_treasury])
    exp_insta_tr = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.insta_treasury]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.insta_treasury])
    total_exp = exp_inside + exp_cash_tr + exp_insta_tr

    add_inside = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.inside and m.movement_type == MovementType.addition])
    add_cash_tr = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.cash and m.movement_type == MovementType.addition])
    add_insta_tr = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.insta and m.movement_type == MovementType.addition])

    curr_inside = float(current_day.opening_inside or 0) + cash_rev + add_inside - exp_inside
    curr_cash_tr = float(current_day.opening_cash_treasury or 0) + add_cash_tr - exp_cash_tr
    curr_insta_tr = float(current_day.opening_insta_treasury or 0) + add_insta_tr - exp_insta_tr
    total_resp = curr_inside + curr_cash_tr + curr_insta_tr

    return {
        "day": {"id": current_day.id, "date": current_day.business_date.strftime("%Y-%m-%d"), "status": current_day.status, "opening_inside": int(current_day.opening_inside or 0), "opening_cash_treasury": int(current_day.opening_cash_treasury or 0), "opening_insta_treasury": int(current_day.opening_insta_treasury or 0)},
        "revenue": {"cash": int(cash_rev), "insta": int(insta_rev), "total": int(total_rev)},
        "expenses_summary": {"inside": int(exp_inside), "cash_tr": int(exp_cash_tr), "insta_tr": int(exp_insta_tr), "total": int(total_exp)},
        "balances": {"inside": int(curr_inside), "cash_tr": int(curr_cash_tr), "insta_tr": int(curr_insta_tr), "total_responsibility": int(total_resp)},
        "orders": [{"id": o.id, "time": o.order_time, "customer": o.customer_name, "is_subscription": o.is_subscription, "price": int(o.price), "payment": o.payment_method.value, "notes": o.notes or ""} for o in orders],
        "expenses": [{"id": e.id, "person": e.person_entity, "type": e.expense_type, "amount": int(e.amount), "source": e.source.value, "notes": e.description or ""} for e in expenses],
        "penalties": [{"id": p.id, "employee": p.employee_name, "amount": int(p.amount), "notes": p.notes or ""} for p in penalties],
        "treasury_movements": [{"id": m.id, "type": m.treasury_type.value, "amount": int(m.amount), "desc": m.description or "تغذية"} for m in movements]
    }

# Orders Endpoints
@app.post("/api/orders")
def add_order(payload: OrderIn, db: Session = Depends(get_db)):
    pm = PaymentMethod.cash if payload.payment_method == "Cash" else (PaymentMethod.insta if payload.payment_method == "Insta" else PaymentMethod.none)
    price = payload.price if pm != PaymentMethod.none else 0.0
    db.add(Order(business_day_id=payload.business_day_id, order_time=payload.order_time, customer_name=payload.customer_name, is_subscription=payload.is_subscription, price=price, payment_method=pm, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.put("/api/orders/{order_id}")
def update_order(order_id: int, payload: OrderIn, db: Session = Depends(get_db)):
    o = db.query(Order).get(order_id)
    if not o: raise HTTPException(status_code=404)
    pm = PaymentMethod.cash if payload.payment_method == "Cash" else (PaymentMethod.insta if payload.payment_method == "Insta" else PaymentMethod.none)
    o.order_time, o.customer_name, o.is_subscription, o.price, o.payment_method, o.notes = payload.order_time, payload.customer_name, payload.is_subscription, payload.price if pm != PaymentMethod.none else 0.0, pm, payload.notes
    db.commit()
    return {"status": "ok"}

@app.delete("/api/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db.query(Order).filter(Order.id == order_id).delete()
    db.commit()
    return {"status": "ok"}

# Expenses Endpoints
@app.post("/api/expenses")
def add_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    src = ExpenseSource.inside if payload.source == "الداخل" else (ExpenseSource.cash_treasury if payload.source == "عهدة Cash" else ExpenseSource.insta_treasury)
    db.add(Expense(business_day_id=payload.business_day_id, person_entity=payload.person_entity, expense_type=payload.expense_type, amount=payload.amount, source=src, description=payload.description))
    db.commit()
    return {"status": "ok"}

@app.put("/api/expenses/{expense_id}")
def update_expense(expense_id: int, payload: ExpenseIn, db: Session = Depends(get_db)):
    e = db.query(Expense).get(expense_id)
    if not e: raise HTTPException(status_code=404)
    src = ExpenseSource.inside if payload.source == "الداخل" else (ExpenseSource.cash_treasury if payload.source == "عهدة Cash" else ExpenseSource.insta_treasury)
    e.person_entity, e.expense_type, e.amount, e.source, e.description = payload.person_entity, payload.expense_type, payload.amount, src, payload.description
    db.commit()
    return {"status": "ok"}

@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    db.query(Expense).filter(Expense.id == expense_id).delete()
    db.commit()
    return {"status": "ok"}

# Penalties (الخصومات)
@app.post("/api/penalties")
def add_penalty(payload: PenaltyIn, db: Session = Depends(get_db)):
    db.add(Penalty(business_day_id=payload.business_day_id, employee_name=payload.employee_name, amount=payload.amount, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/penalties/{penalty_id}")
def delete_penalty(penalty_id: int, db: Session = Depends(get_db)):
    db.query(Penalty).filter(Penalty.id == penalty_id).delete()
    db.commit()
    return {"status": "ok"}

# Purchases (المشتريات والصيانة)
@app.get("/api/purchases")
def get_purchases(region_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Purchase).order_by(Purchase.purchase_date.desc())
    if region_id: q = q.filter(Purchase.region_id == region_id)
    regs = {r.id: r.name for r in db.query(Region).all()}
    return [{"id": p.id, "date": p.purchase_date.strftime("%Y-%m-%d"), "branch": regs.get(p.region_id, "عام"), "category": p.category, "amount": int(p.amount), "source": p.source.value, "description": p.description or ""} for p in q.all()]

@app.post("/api/purchases")
def add_purchase(payload: PurchaseIn, db: Session = Depends(get_db)):
    p_d = datetime.strptime(payload.purchase_date, "%Y-%m-%d").date()
    src = ExpenseSource.inside if payload.source == "الداخل" else (ExpenseSource.cash_treasury if payload.source == "عهدة Cash" else ExpenseSource.insta_treasury)
    db.add(Purchase(region_id=payload.region_id, business_day_id=payload.business_day_id, purchase_date=p_d, category=payload.category, amount=payload.amount, source=src, description=payload.description))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/purchases/{purchase_id}")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    db.query(Purchase).filter(Purchase.id == purchase_id).delete()
    db.commit()
    return {"status": "ok"}

# Treasury & Inside Injections (التغذية للداخل والعهد)
@app.post("/api/treasury-feed")
def add_treasury(payload: TreasuryIn, db: Session = Depends(get_db)):
    tt = TreasuryType.inside if payload.treasury_type == "الداخل" else (TreasuryType.cash if payload.treasury_type == "عهدة Cash" else TreasuryType.insta)
    db.add(TreasuryMovement(business_day_id=payload.business_day_id, treasury_type=tt, movement_type=MovementType.addition, amount=payload.amount, description=payload.description))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/treasury-movements/{movement_id}")
def delete_treasury(movement_id: int, db: Session = Depends(get_db)):
    db.query(TreasuryMovement).filter(TreasuryMovement.id == movement_id).delete()
    db.commit()
    return {"status": "ok"}

# Settlements (التصفية وتسوية الديون)
@app.get("/api/settlements/summary")
def get_settlements_summary(db: Session = Depends(get_db)):
    expenses = db.query(Expense).all()
    penalties = db.query(Penalty).all()
    settlements = db.query(Settlement).filter(Settlement.entity_type == "employee").all()
    
    def is_deductible(t):
        s = str(t).strip()
        return ("سلف" in s) or ("مصروف" in s and "بنزين" not in s and "سكن" not in s)

    emp_balances = {}
    for e in expenses:
        if is_deductible(e.expense_type):
            emp_balances[e.person_entity] = emp_balances.get(e.person_entity, 0) + int(e.amount)
    for p in penalties:
        emp_balances[p.employee_name] = emp_balances.get(p.employee_name, 0) + int(p.amount)
    for s in settlements:
        emp_balances[s.name] = emp_balances.get(s.name, 0) - int(s.amount)

    emp_list = [{"name": k, "balance": max(0, v), "raw_balance": v} for k, v in emp_balances.items() if v != 0]
    history = db.query(Settlement).order_by(Settlement.settlement_date.desc()).all()
    return {
        "employees": sorted(emp_list, key=lambda x: x["balance"], reverse=True),
        "history": [{"id": h.id, "type": h.entity_type, "name": h.name, "amount": int(h.amount), "date": h.settlement_date.strftime("%Y-%m-%d"), "notes": h.notes or ""} for h in history]
    }

@app.post("/api/settlements")
def make_settlement(payload: SettlementIn, db: Session = Depends(get_db)):
    s_d = datetime.strptime(payload.settlement_date, "%Y-%m-%d").date()
    db.add(Settlement(entity_type=payload.entity_type, name=payload.name, amount=payload.amount, settlement_date=s_d, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/settlements/{settlement_id}")
def delete_settlement(settlement_id: int, db: Session = Depends(get_db)):
    db.query(Settlement).filter(Settlement.id == settlement_id).delete()
    db.commit()
    return {"status": "ok"}

# Shift Control (إغلاق وإعادة فتح)
@app.post("/api/shift/{day_id}/close")
def close_shift(day_id: int, db: Session = Depends(get_db)):
    d = db.query(BusinessDay).get(day_id)
    if not d: raise HTTPException(status_code=404)
    orders = db.query(Order).filter(Order.business_day_id == day_id).all()
    expenses = db.query(Expense).filter(Expense.business_day_id == day_id).all()
    purchases = db.query(Purchase).filter(Purchase.business_day_id == day_id).all()
    movements = db.query(TreasuryMovement).filter(TreasuryMovement.business_day_id == day_id).all()
    
    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    exp_in = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.inside]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.inside])
    exp_c = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.cash_treasury]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.cash_treasury])
    exp_i = sum([float(e.amount) for e in expenses if e.source == ExpenseSource.insta_treasury]) + sum([float(p.amount) for p in purchases if p.source == ExpenseSource.insta_treasury])
    
    add_in = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.inside and m.movement_type == MovementType.addition])
    add_c = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.cash and m.movement_type == MovementType.addition])
    add_i = sum([float(m.amount) for m in movements if m.treasury_type == TreasuryType.insta and m.movement_type == MovementType.addition])

    d.status = "CLOSED"
    d.closing_inside = float(d.opening_inside or 0) + cash_rev + add_in - exp_in
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

# Reports Engine (التقارير المجمعة)
@app.get("/api/reports")
def get_reports(start_date: str, end_date: str, region_id: Optional[int] = None, db: Session = Depends(get_db)):
    s_d, e_d = datetime.strptime(start_date, "%Y-%m-%d").date(), datetime.strptime(end_date, "%Y-%m-%d").date()
    q = db.query(BusinessDay).filter(BusinessDay.business_date >= s_d, BusinessDay.business_date <= e_d)
    if region_id: q = q.filter(BusinessDay.region_id == region_id)
    days = q.all()
    day_ids = [d.id for d in days]
    if not day_ids: return {"empty": True}

    regions = {r.id: r.name for r in db.query(Region).all()}
    day_map = {d.id: {"date": d.business_date.strftime("%Y-%m-%d"), "region": regions.get(d.region_id, "عام")} for d in days}

    orders = db.query(Order).filter(Order.business_day_id.in_(day_ids)).all()
    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    insta_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.insta])

    expenses = db.query(Expense).filter(Expense.business_day_id.in_(day_ids)).all()
    penalties = db.query(Penalty).filter(Penalty.business_day_id.in_(day_ids)).all()
    purchases = db.query(Purchase).filter(Purchase.business_day_id.in_(day_ids)).all()

    def is_deductible(t):
        s = str(t).strip()
        return ("سلف" in s) or ("مصروف" in s and "بنزين" not in s and "سكن" not in s)

    emp_deductions = {}
    opex_categories = {}

    for e in expenses:
        info = day_map.get(e.business_day_id, {"date": "", "region": ""})
        amt = int(e.amount)
        if is_deductible(e.expense_type):
            if e.person_entity not in emp_deductions: emp_deductions[e.person_entity] = {"total": 0, "branches": {}}
            emp_deductions[e.person_entity]["total"] += amt
            b_name = info["region"]
            emp_deductions[e.person_entity]["branches"][b_name] = emp_deductions[e.person_entity]["branches"].get(b_name, 0) + amt
        else:
            opex_categories[e.expense_type] = opex_categories.get(e.expense_type, 0) + amt

    for p in penalties:
        info = day_map.get(p.business_day_id, {"date": "", "region": ""})
        amt = int(p.amount)
        if p.employee_name not in emp_deductions: emp_deductions[p.employee_name] = {"total": 0, "branches": {}}
        emp_deductions[p.employee_name]["total"] += amt
        b_name = info["region"]
        emp_deductions[p.employee_name]["branches"][b_name] = emp_deductions[p.employee_name]["branches"].get(b_name, 0) + amt

    salary_table = []
    for emp, data in emp_deductions.items():
        row = {"employee": emp, "total": data["total"]}
        for r_name in regions.values(): row[r_name] = data["branches"].get(r_name, 0)
        salary_table.append(row)

    opex_table = [{"category": k, "amount": v} for k, v in sorted(opex_categories.items(), key=lambda x: x[1], reverse=True)]

    raw_exps = [{"date": day_map.get(e.business_day_id, {}).get("date"), "branch": day_map.get(e.business_day_id, {}).get("region"), "person": e.person_entity, "type": e.expense_type, "amount": int(e.amount), "source": e.source.value, "notes": e.description or "", "is_deductible": is_deductible(e.expense_type)} for e in expenses]
    raw_exps += [{"date": day_map.get(p.business_day_id, {}).get("date"), "branch": day_map.get(p.business_day_id, {}).get("region"), "person": p.employee_name, "type": "خصم / جزاء", "amount": int(p.amount), "source": "إداري", "notes": p.notes or "", "is_deductible": True} for p in penalties]

    return {
        "empty": False,
        "revenue": {"cash": int(cash_rev), "insta": int(insta_rev), "total": int(cash_rev + insta_rev)},
        "salary_deductions": salary_table,
        "opex": opex_table,
        "opex_total": sum(opex_categories.values()),
        "purchases_total": sum([int(p.amount) for p in purchases]),
        "raw_expenses": raw_exps
    }

# Leaves & Settings Endpoints
@app.get("/api/leaves")
def get_leaves(db: Session = Depends(get_db)):
    regions = {r.id: r.name for r in db.query(Region).all()}
    return [{"id": l.id, "employee": l.employee_name, "date": l.leave_date.strftime("%Y-%m-%d"), "branch": regions.get(l.region_id, "عام"), "notes": l.notes or "إجازة"} for l in db.query(Leave).order_by(Leave.leave_date.desc()).all()]

@app.post("/api/leaves")
def add_leave(payload: LeaveIn, db: Session = Depends(get_db)):
    db.add(Leave(region_id=payload.region_id, employee_name=payload.employee_name, leave_date=datetime.strptime(payload.leave_date, "%Y-%m-%d").date(), notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/leaves/{leave_id}")
def delete_leave(leave_id: int, db: Session = Depends(get_db)):
    db.query(Leave).filter(Leave.id == leave_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/meta")
def get_meta(db: Session = Depends(get_db)):
    emps = [e.name for e in db.query(Employee).filter(Employee.is_active == True).all()]
    cats = [c.name for c in db.query(ExpenseCategory).filter(ExpenseCategory.is_active == True).all()]
    p_cats = [c.name for c in db.query(PurchaseCategory).filter(PurchaseCategory.is_active == True).all()]
    if not cats: cats = ["سلفة", "مصروف شخصي", "بنزين", "سكن", "بوفيه", "تيبس"]
    if not p_cats: p_cats = ["شامبو وفوط", "صيانة ماكينات", "قطع غيار", "مشتريات عدد"]
    return {"employees": sorted(list(set(emps))), "categories": sorted(list(set(cats))), "purchase_categories": sorted(list(set(p_cats)))}

@app.post("/api/employees")
def create_emp(name: str, region_id: int, db: Session = Depends(get_db)):
    if name.strip(): db.add(Employee(name=name.strip(), region_id=region_id)); db.commit()
    return {"status": "ok"}

@app.delete("/api/employees")
def remove_emp(name: str, db: Session = Depends(get_db)):
    db.query(Employee).filter(Employee.name == name).delete(); db.commit()
    return {"status": "ok"}

@app.post("/api/categories")
def create_cat(name: str, db: Session = Depends(get_db)):
    if name.strip(): db.add(ExpenseCategory(name=name.strip())); db.commit()
    return {"status": "ok"}

@app.delete("/api/categories")
def remove_cat(name: str, db: Session = Depends(get_db)):
    db.query(ExpenseCategory).filter(ExpenseCategory.name == name).delete(); db.commit()
    return {"status": "ok"}

@app.post("/api/purchase-categories")
def create_p_cat(name: str, db: Session = Depends(get_db)):
    if name.strip(): db.add(PurchaseCategory(name=name.strip())); db.commit()
    return {"status": "ok"}

@app.delete("/api/purchase-categories")
def remove_p_cat(name: str, db: Session = Depends(get_db)):
    db.query(PurchaseCategory).filter(PurchaseCategory.name == name).delete(); db.commit()
    return {"status": "ok"}

@app.post("/api/initial-balances")
def set_balances(region_id: int, date_str: str, inside: float, cash_tr: float, insta_tr: float, db: Session = Depends(get_db)):
    t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.region_id == region_id, BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(region_id=region_id, business_date=t_d, status="OPEN")
        db.add(day)
    day.opening_inside, day.opening_cash_treasury, day.opening_insta_treasury = inside, cash_tr, insta_tr
    db.commit()
    return {"status": "ok"}

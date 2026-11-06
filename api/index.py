import os
import enum
import traceback
from datetime import date, datetime, timedelta
from typing import Optional, List, Any
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Date, Enum, Numeric, DateTime, func, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==================== 1. الاتصال بقاعدة البيانات ====================
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        print("Engine creation error:", e)

Base = declarative_base()

# ==================== 2. القوائم الثابتة ====================
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

# ==================== 3. جداول قاعدة البيانات ====================
class BusinessDay(Base):
    __tablename__ = 'business_days'
    id = Column(Integer, primary_key=True)
    business_date = Column(Date, unique=True, nullable=False)
    status = Column(String, default="OPEN")
    opening_treasury = Column(Numeric(10, 2), default=0.00)
    transfer_treasury = Column(Numeric(10, 2), default=0.00)
    is_manual_opening = Column(Boolean, default=False)
    closed_at = Column(DateTime, nullable=True)

class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    basic_salary = Column(Numeric(10, 2), default=0.00)
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

class AdminExpenseCategory(Base):
    __tablename__ = 'admin_expense_categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    booking_date = Column(Date, nullable=False)
    branch = Column(String, default="الشروق")
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    assigned_employee = Column(String, nullable=True)
    wash_type = Column(String, default="غسلة عادية")
    is_subscription = Column(Boolean, default=False)
    price = Column(Numeric(10, 2), default=0.00)
    payment_method = Column(Enum(PaymentMethod), default=PaymentMethod.none)
    status = Column(String, default="pending")
    is_collected = Column(Boolean, default=False)
    notes = Column(String, nullable=True)

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True)
    business_day_id = Column(Integer, ForeignKey('business_days.id'), nullable=False)
    expense_date = Column(Date, nullable=False)
    branch = Column(String, default="عام")
    person_entity = Column(String, nullable=False)
    expense_type = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    source = Column(Enum(ExpenseSource), default=ExpenseSource.inside)
    description = Column(String, nullable=True)

class AdminExpense(Base):
    __tablename__ = 'admin_expenses'
    id = Column(Integer, primary_key=True)
    expense_date = Column(Date, nullable=False)
    category = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String, default="حساب بنكي")
    description = Column(String, nullable=True)

class Penalty(Base):
    __tablename__ = 'penalties'
    id = Column(Integer, primary_key=True)
    penalty_date = Column(Date, nullable=False)
    employee_name = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(String, nullable=True)

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(Integer, primary_key=True)
    purchase_date = Column(Date, nullable=False)
    branch = Column(String, default="عام")
    category = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    source = Column(String, default="العهدة المجمعة")
    description = Column(String, nullable=True)

class Leave(Base):
    __tablename__ = 'leaves'
    id = Column(Integer, primary_key=True)
    leave_date = Column(Date, nullable=False)
    employee_name = Column(String, nullable=False)
    leave_type = Column(String, default="من رصيده")
    notes = Column(String, nullable=True)

class Settlement(Base):
    __tablename__ = 'settlements'
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    settlement_date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)

# ==================== 4. إعداد السيرفر ودوال المساعدة ====================
app = FastAPI(title="Catchy Finance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def ensure_tables():
    if engine:
        try:
            Base.metadata.create_all(bind=engine)
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE business_days ADD COLUMN is_manual_opening BOOLEAN DEFAULT FALSE;"))
                    conn.commit()
            except Exception:
                pass
        except Exception as e:
            print("Auto create tables error:", e)

def get_db():
    if not SessionLocal:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured properly")
    ensure_tables()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def normalize_branch(branch_name: Optional[str]) -> str:
    if not branch_name:
        return "الشروق"
    b = str(branch_name).strip()
    if "مدينت" in b:
        return "مدينتي"
    if "شروق" in b:
        return "الشروق"
    return b

def parse_pm(pm_val: Optional[str]) -> PaymentMethod:
    if not pm_val:
        return PaymentMethod.none
    val = str(pm_val).strip().lower()
    if val in ["cash", "كاش", "نقدي"]:
        return PaymentMethod.cash
    elif val in ["insta", "انستا", "انستاباي", "instapay"]:
        return PaymentMethod.insta
    return PaymentMethod.none

def get_day_remaining(day_obj: BusinessDay, db: Session) -> float:
    if not day_obj:
        return 0.0
    t_d = day_obj.business_date
    orders = db.query(Order).filter(Order.booking_date == t_d).all()
    collected_orders = [o for o in orders if o.status == "done" and o.is_collected]
    cash_collected = sum([float(o.price) for o in collected_orders if o.payment_method == PaymentMethod.cash])

    expenses = db.query(Expense).filter(Expense.expense_date == t_d).all()
    purchases = db.query(Purchase).filter(Purchase.purchase_date == t_d).all()
    total_expenses = sum([float(e.amount) for e in expenses]) + sum([float(p.amount) for p in purchases])

    opening_tr = float(day_obj.opening_treasury or 0)
    transfer_tr = float(day_obj.transfer_treasury or 0)
    total_treasury = opening_tr + cash_collected + transfer_tr
    return total_treasury - total_expenses

# ==================== 5. Pydantic Schemas ====================
class OrderIn(BaseModel):
    booking_date: str
    branch: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = ""
    assigned_employee: Optional[str] = ""
    wash_type: Optional[str] = "غسلة عادية"
    is_subscription: Optional[bool] = False
    price: Optional[float] = 0.0
    payment_method: Optional[str] = "None"
    status: Optional[str] = "pending"
    is_collected: Optional[bool] = False
    notes: Optional[str] = ""

class OrderUpdateIn(BaseModel):
    booking_date: Optional[str] = None
    branch: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    assigned_employee: Optional[str] = None
    wash_type: Optional[str] = None
    is_subscription: Optional[bool] = None
    price: Optional[float] = None
    payment_method: Optional[str] = None
    status: Optional[str] = None
    is_collected: Optional[bool] = None
    notes: Optional[str] = None

class BulkOrdersIn(BaseModel):
    booking_date: str
    branch: Optional[str] = None
    orders: List[dict]

class ExpenseIn(BaseModel):
    expense_date: str
    branch: Optional[str] = "عام"
    person_entity: str
    expense_type: str
    amount: float
    description: Optional[str] = ""

class AdminExpenseIn(BaseModel):
    expense_date: str
    category: str
    amount: float
    payment_method: Optional[str] = "حساب بنكي"
    description: Optional[str] = ""

class PenaltyIn(BaseModel):
    penalty_date: str
    employee_name: str
    amount: float
    notes: Optional[str] = ""

class PurchaseIn(BaseModel):
    purchase_date: str
    branch: Optional[str] = "عام"
    category: str
    amount: float
    source: Optional[str] = "العهدة المجمعة"
    description: Optional[str] = ""

class LeaveIn(BaseModel):
    leave_date: str
    employee_name: str
    leave_type: Optional[str] = "من رصيده"
    notes: Optional[str] = ""

class SettlementIn(BaseModel):
    entity_type: str
    name: str
    amount: float
    settlement_date: str
    notes: Optional[str] = ""

class UpdateTreasuryIn(BaseModel):
    shift_date: str
    opening_treasury: float
    transfer_treasury: float

# ==================== 6. ENDPOINTS ====================

@app.get("/api/meta")
def get_meta(db: Session = Depends(get_db)):
    try:
        emps = [{"id": e.id, "name": e.name, "salary": int(e.basic_salary or 0)} for e in db.query(Employee).filter(Employee.is_active == True).all()]
        cats = [c.name for c in db.query(ExpenseCategory).filter(ExpenseCategory.is_active == True).all()]
        p_cats = [c.name for c in db.query(PurchaseCategory).filter(PurchaseCategory.is_active == True).all()]
        a_cats = [c.name for c in db.query(AdminExpenseCategory).filter(AdminExpenseCategory.is_active == True).all()]
        
        if not cats: cats = ["سحوبات من المرتب", "سلفة", "باقة", "بنزين", "خامات", "صيانة موتسيكلات", "صيانة معدات", "مشتريات للسكن"]
        if not p_cats: p_cats = ["شامبو وفوط", "صيانة ماكينات", "قطع غيار", "مشتريات عدد"]
        if not a_cats: a_cats = ["إيجار مقر", "محامي ومستشار قانوني", "تجديد رخص وسجلات", "شراء أصول وموتوسيكلات"]

        return {
            "employees": emps,
            "categories": sorted(list(set(cats))),
            "purchase_categories": sorted(list(set(p_cats))),
            "admin_categories": sorted(list(set(a_cats)))
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/api/day-summary")
def get_day_summary(date_str: str, db: Session = Depends(get_db)):
    try:
        t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
        
        # البحث عن آخر يوم عمل مسجل قبل هذا اليوم
        prev_day = db.query(BusinessDay).filter(BusinessDay.business_date < t_d).order_by(BusinessDay.business_date.desc()).first()
        prev_remaining = get_day_remaining(prev_day, db) if prev_day else 0.0

        if not day:
            day = BusinessDay(
                business_date=t_d, 
                status="OPEN", 
                opening_treasury=prev_remaining, 
                transfer_treasury=0.0,
                is_manual_opening=False
            )
            db.add(day)
            db.commit()
            db.refresh(day)
        else:
            # إذا لم يتم تحديد العهدة يدوياً بواسطة الإدارة، يتم جلب متبقي الأمس تلقائياً
            is_manual = getattr(day, 'is_manual_opening', False)
            if not is_manual and prev_day:
                day.opening_treasury = prev_remaining
                db.commit()
                db.refresh(day)

        orders = db.query(Order).filter(Order.booking_date == t_d).all()
        collected_orders = [o for o in orders if o.status == "done" and o.is_collected]
        cash_collected = sum([float(o.price) for o in collected_orders if o.payment_method == PaymentMethod.cash])
        insta_collected = sum([float(o.price) for o in collected_orders if o.payment_method == PaymentMethod.insta])
        total_revenue = cash_collected + insta_collected

        expenses = db.query(Expense).filter(Expense.expense_date == t_d).all()
        purchases = db.query(Purchase).filter(Purchase.purchase_date == t_d).all()
        total_expenses = sum([float(e.amount) for e in expenses]) + sum([float(p.amount) for p in purchases])

        opening_tr = float(day.opening_treasury or 0)
        transfer_tr = float(day.transfer_treasury or 0)
        total_treasury = opening_tr + cash_collected + transfer_tr
        remaining_treasury = total_treasury - total_expenses

        return {
            "day": {
                "id": day.id,
                "date": day.business_date.strftime("%Y-%m-%d"),
                "status": day.status,
                "opening_treasury": int(opening_tr),
                "transfer_treasury": int(transfer_tr),
                "cash_collected": int(cash_collected),
                "total_treasury": int(total_treasury),
                "total_expenses": int(total_expenses),
                "remaining_treasury": int(remaining_treasury),
                "is_manual_opening": getattr(day, 'is_manual_opening', False)
            },
            "revenue": {
                "cash": int(cash_collected),
                "insta": int(insta_collected),
                "total": int(total_revenue)
            }
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.post("/api/update-treasury")
def update_treasury(payload: UpdateTreasuryIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.shift_date, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(business_date=t_d, status="OPEN")
        db.add(day)
    day.opening_treasury = payload.opening_treasury
    day.transfer_treasury = payload.transfer_treasury
    try:
        day.is_manual_opening = True
    except Exception:
        pass
    db.commit()
    return {"status": "ok"}

@app.post("/api/reset-opening-treasury")
def reset_opening_treasury(shift_date: str, db: Session = Depends(get_db)):
    t_d = datetime.strptime(shift_date, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
    if day:
        try:
            day.is_manual_opening = False
        except Exception:
            pass
        prev_day = db.query(BusinessDay).filter(BusinessDay.business_date < t_d).order_by(BusinessDay.business_date.desc()).first()
        day.opening_treasury = get_day_remaining(prev_day, db) if prev_day else 0.0
        db.commit()
    return {"status": "ok"}

@app.get("/api/bookings")
def get_bookings(date_str: str, branch: Optional[str] = None, db: Session = Depends(get_db)):
    t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
    q = db.query(Order).filter(Order.booking_date == t_d)
    
    if branch and branch not in ["الكل", "all", "ALL", ""]:
        clean_branch = normalize_branch(branch)
        q = q.filter(Order.branch == clean_branch)
        
    orders = q.order_by(Order.id.asc()).all()
    return [{
        "id": o.id,
        "date": o.booking_date.strftime("%Y-%m-%d"),
        "branch": o.branch,
        "customer_name": o.customer_name,
        "customer_phone": o.customer_phone or "",
        "assigned_employee": o.assigned_employee or "",
        "wash_type": o.wash_type,
        "is_subscription": o.is_subscription,
        "price": int(o.price),
        "payment_method": o.payment_method.value if o.payment_method else "None",
        "status": o.status,
        "is_collected": o.is_collected,
        "notes": o.notes or ""
    } for o in orders]

@app.post("/api/bookings")
def add_booking(payload: OrderIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.booking_date, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(business_date=t_d, status="OPEN")
        db.add(day)
        db.commit()
        db.refresh(day)
        
    pm = parse_pm(payload.payment_method)
    final_branch = normalize_branch(payload.branch)

    emp_name = (payload.assigned_employee or "").strip()
    if emp_name:
        existing_emp = db.query(Employee).filter(Employee.name == emp_name).first()
        if not existing_emp:
            db.add(Employee(name=emp_name, basic_salary=0.0, is_active=True))
            db.commit()

    o = Order(
        business_day_id=day.id,
        booking_date=t_d,
        branch=final_branch,
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone,
        assigned_employee=emp_name,
        wash_type=payload.wash_type,
        is_subscription=payload.is_subscription,
        price=payload.price,
        payment_method=pm,
        status=payload.status or "pending",
        is_collected=payload.is_collected,
        notes=payload.notes
    )
    db.add(o)
    db.commit()
    return {"status": "ok"}

@app.post("/api/bookings/bulk")
def add_bulk_bookings(payload: BulkOrdersIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.booking_date, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(business_date=t_d, status="OPEN")
        db.add(day)
        db.commit()
        db.refresh(day)

    existing_emps = {e.name: e for e in db.query(Employee).all()}
    new_orders = []

    for item in payload.orders:
        clean_item = {str(k).strip(): v for k, v in item.items() if v is not None}

        c_name = str(clean_item.get("customer_name") or clean_item.get("اسم العميل") or clean_item.get("العميل") or "").strip()
        if not c_name: 
            continue
            
        c_phone = str(clean_item.get("customer_phone") or clean_item.get("الهاتف") or clean_item.get("تليفون") or clean_item.get("رقم التليفون") or clean_item.get("الموبايل") or "").strip()
        w_type = str(clean_item.get("wash_type") or clean_item.get("نوع الغسلة") or clean_item.get("الخدمة") or clean_item.get("نوع الخدمة") or "غسلة عادية").strip()
        is_sub = ("اشتراك" in w_type) or bool(clean_item.get("is_subscription"))
        
        row_branch_raw = clean_item.get("branch") or clean_item.get("الفرع") or payload.branch
        row_branch = normalize_branch(row_branch_raw)

        emp_name = str(
            clean_item.get("assigned_employee")
            or clean_item.get("اسم الموظف")
            or clean_item.get("الموظف")
            or clean_item.get("الكابتن")
            or clean_item.get("العامل")
            or clean_item.get("الفني")
            or clean_item.get("القائم بالغسيل")
            or clean_item.get("مسؤول الغسيل")
            or clean_item.get("مسئول الغسيل")
            or clean_item.get("employee")
            or ""
        ).strip()

        if emp_name and emp_name not in existing_emps:
            new_emp = Employee(name=emp_name, basic_salary=0.0, is_active=True)
            db.add(new_emp)
            db.commit()
            existing_emps[emp_name] = new_emp

        pm_raw = clean_item.get("payment_method") or clean_item.get("طريقة الدفع") or clean_item.get("الدفع")
        pm = parse_pm(pm_raw)

        price_val = 0.0
        try:
            price_val = float(clean_item.get("price") or clean_item.get("السعر") or clean_item.get("المبلغ") or clean_item.get("القيمة") or 0)
        except:
            price_val = 0.0
        
        o = Order(
            business_day_id=day.id,
            booking_date=t_d,
            branch=row_branch,
            customer_name=c_name,
            customer_phone=c_phone,
            assigned_employee=emp_name,
            wash_type=w_type,
            is_subscription=is_sub,
            price=price_val,
            payment_method=pm,
            status="pending",
            is_collected=False,
            notes=str(clean_item.get("notes") or clean_item.get("ملاحظات") or "")
        )
        new_orders.append(o)

    if new_orders:
        db.add_all(new_orders)
        db.commit()
    return {"status": "ok", "count": len(new_orders)}

@app.put("/api/bookings/{order_id}")
def update_booking(order_id: int, payload: OrderUpdateIn, db: Session = Depends(get_db)):
    o = db.query(Order).get(order_id)
    if not o: 
        raise HTTPException(status_code=404, detail="Order not found")
        
    if payload.branch is not None:
        o.branch = normalize_branch(payload.branch)
    if payload.customer_name is not None:
        o.customer_name = payload.customer_name.strip()
    if payload.customer_phone is not None:
        o.customer_phone = payload.customer_phone
    if payload.assigned_employee is not None:
        emp_clean = payload.assigned_employee.strip()
        o.assigned_employee = emp_clean
        if emp_clean:
            exist = db.query(Employee).filter(Employee.name == emp_clean).first()
            if not exist:
                db.add(Employee(name=emp_clean, basic_salary=0.0, is_active=True))
                db.commit()
    if payload.wash_type is not None:
        o.wash_type = payload.wash_type
    if payload.is_subscription is not None:
        o.is_subscription = payload.is_subscription
    if payload.price is not None:
        o.price = payload.price
    if payload.payment_method is not None:
        o.payment_method = parse_pm(payload.payment_method)
    if payload.status is not None:
        o.status = payload.status
    if payload.is_collected is not None:
        o.is_collected = payload.is_collected
    if payload.notes is not None:
        o.notes = payload.notes

    db.commit()
    db.refresh(o)
    return {"status": "ok", "order_id": o.id}

@app.delete("/api/bookings/{order_id}")
def delete_booking(order_id: int, db: Session = Depends(get_db)):
    db.query(Order).filter(Order.id == order_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/expenses")
def get_expenses(date_str: str, db: Session = Depends(get_db)):
    t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
    exps = db.query(Expense).filter(Expense.expense_date == t_d).all()
    return [{"id": e.id, "date": e.expense_date.strftime("%Y-%m-%d"), "branch": e.branch, "person": e.person_entity, "type": e.expense_type, "amount": int(e.amount), "notes": e.description or ""} for e in exps]

@app.post("/api/expenses")
def add_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.expense_date, "%Y-%m-%d").date()
    day = db.query(BusinessDay).filter(BusinessDay.business_date == t_d).first()
    if not day:
        day = BusinessDay(business_date=t_d, status="OPEN")
        db.add(day)
        db.commit()
        db.refresh(day)
        
    db.add(Expense(
        business_day_id=day.id, 
        expense_date=t_d, 
        branch=payload.branch or "عام", 
        person_entity=payload.person_entity, 
        expense_type=payload.expense_type, 
        amount=payload.amount, 
        description=payload.description
    ))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    db.query(Expense).filter(Expense.id == expense_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/penalties")
def get_penalties(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Penalty).order_by(Penalty.penalty_date.desc())
    if date_str:
        t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        q = q.filter(Penalty.penalty_date == t_d)
    return [{"id": p.id, "date": p.penalty_date.strftime("%Y-%m-%d"), "employee": p.employee_name, "amount": int(p.amount), "notes": p.notes or ""} for p in q.all()]

@app.post("/api/penalties")
def add_penalty(payload: PenaltyIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.penalty_date, "%Y-%m-%d").date()
    db.add(Penalty(penalty_date=t_d, employee_name=payload.employee_name, amount=payload.amount, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/penalties/{penalty_id}")
def delete_penalty(penalty_id: int, db: Session = Depends(get_db)):
    db.query(Penalty).filter(Penalty.id == penalty_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/purchases")
def get_purchases(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Purchase).order_by(Purchase.purchase_date.desc())
    if date_str:
        t_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        q = q.filter(Purchase.purchase_date == t_d)
    return [{"id": p.id, "date": p.purchase_date.strftime("%Y-%m-%d"), "branch": p.branch, "category": p.category, "amount": int(p.amount), "source": p.source, "description": p.description or ""} for p in q.all()]

@app.post("/api/purchases")
def add_purchase(payload: PurchaseIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.purchase_date, "%Y-%m-%d").date()
    db.add(Purchase(
        purchase_date=t_d, 
        branch=payload.branch or "عام", 
        category=payload.category, 
        amount=payload.amount, 
        source=payload.source or "العهدة المجمعة", 
        description=payload.description
    ))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/purchases/{purchase_id}")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    db.query(Purchase).filter(Purchase.id == purchase_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/admin-expenses")
def get_admin_expenses(db: Session = Depends(get_db)):
    items = db.query(AdminExpense).order_by(AdminExpense.expense_date.desc()).all()
    return [{"id": a.id, "date": a.expense_date.strftime("%Y-%m-%d"), "category": a.category, "amount": int(a.amount), "payment_method": a.payment_method, "description": a.description or ""} for a in items]

@app.post("/api/admin-expenses")
def add_admin_expense(payload: AdminExpenseIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.expense_date, "%Y-%m-%d").date()
    db.add(AdminExpense(
        expense_date=t_d, 
        category=payload.category, 
        amount=payload.amount, 
        payment_method=payload.payment_method, 
        description=payload.description
    ))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/admin-expenses/{item_id}")
def delete_admin_expense(item_id: int, db: Session = Depends(get_db)):
    db.query(AdminExpense).filter(AdminExpense.id == item_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/leaves")
def get_leaves(db: Session = Depends(get_db)):
    return [{"id": l.id, "date": l.leave_date.strftime("%Y-%m-%d"), "employee": l.employee_name, "leave_type": l.leave_type, "notes": l.notes or ""} for l in db.query(Leave).order_by(Leave.leave_date.desc()).all()]

@app.post("/api/leaves")
def add_leave(payload: LeaveIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.leave_date, "%Y-%m-%d").date()
    db.add(Leave(leave_date=t_d, employee_name=payload.employee_name, leave_type=payload.leave_type, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/leaves/{leave_id}")
def delete_leave(leave_id: int, db: Session = Depends(get_db)):
    db.query(Leave).filter(Leave.id == leave_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/payroll-overview")
def get_payroll_overview(start_date: str, end_date: str, db: Session = Depends(get_db)):
    s_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    expenses = db.query(Expense).filter(Expense.expense_date >= s_d, Expense.expense_date <= e_d).all()
    penalties = db.query(Penalty).filter(Penalty.penalty_date >= s_d, Penalty.penalty_date <= e_d).all()
    leaves = db.query(Leave).filter(Leave.leave_date >= s_d, Leave.leave_date <= e_d).all()
    settlements = db.query(Settlement).filter(Settlement.settlement_date >= s_d, Settlement.settlement_date <= e_d, Settlement.entity_type == "employee").all()
    all_loans = db.query(Expense).filter(Expense.expense_type == "سلفة").all()
    all_loan_settlements = db.query(Settlement).filter(Settlement.entity_type == "employee").all()

    payroll_table, advances_overview = [], []

    for emp in employees:
        b_salary = float(emp.basic_salary or 0)
        daily_rate = b_salary / 30.0 if b_salary > 0 else 0

        emp_draws = sum([float(e.amount) for e in expenses if e.person_entity == emp.name and e.expense_type == "سحوبات من المرتب"])
        emp_penalties = sum([float(p.amount) for p in penalties if p.employee_name == emp.name])
        unpaid_days = len([l for l in leaves if l.employee_name == emp.name and l.leave_type == "على حسابه"])
        unpaid_deduction = unpaid_days * daily_rate

        total_loan_ever = sum([float(e.amount) for e in all_loans if e.person_entity == emp.name])
        settled_loan_ever = sum([float(s.amount) for s in all_loan_settlements if s.name == emp.name])
        current_loan_debt = max(0, total_loan_ever - settled_loan_ever)
        this_month_settled = sum([float(s.amount) for s in settlements if s.name == emp.name])

        total_deductions_this_month = emp_draws + emp_penalties + unpaid_deduction + this_month_settled
        net_salary = max(0, b_salary - total_deductions_this_month)

        draw_ratio = (total_deductions_this_month / b_salary * 100) if b_salary > 0 else 0
        status_color = "green" if draw_ratio <= 35 else ("yellow" if draw_ratio <= 65 else "red")
        emp_history = [{"date": e.expense_date.strftime("%Y-%m-%d"), "amount": int(e.amount), "type": e.expense_type, "notes": e.description or ""} for e in expenses if e.person_entity == emp.name and ("سلف" in e.expense_type or "سحوبات" in e.expense_type)]

        advances_overview.append({
            "name": emp.name, 
            "basic_salary": int(b_salary), 
            "monthly_draws": int(emp_draws),
            "loan_installment": int(this_month_settled), 
            "total_monthly_commitment": int(total_deductions_this_month), 
            "total_loan_debt": int(current_loan_debt), 
            "draw_ratio": int(draw_ratio), 
            "status_color": status_color, 
            "history": emp_history
        })

        payroll_table.append({
            "name": emp.name, 
            "basic_salary": int(b_salary), 
            "draws": int(emp_draws), 
            "loan_installment": int(this_month_settled), 
            "penalties": int(emp_penalties), 
            "unpaid_days": unpaid_days, 
            "unpaid_deduction": int(unpaid_deduction), 
            "total_deductions": int(total_deductions_this_month), 
            "net_salary": int(net_salary)
        })

    return {"advances_overview": advances_overview, "payroll_table": payroll_table}

@app.post("/api/settlements")
def add_settlement(payload: SettlementIn, db: Session = Depends(get_db)):
    t_d = datetime.strptime(payload.settlement_date, "%Y-%m-%d").date()
    db.add(Settlement(entity_type=payload.entity_type, name=payload.name, amount=payload.amount, settlement_date=t_d, notes=payload.notes))
    db.commit()
    return {"status": "ok"}

@app.delete("/api/settlements/{item_id}")
def delete_settlement(item_id: int, db: Session = Depends(get_db)):
    db.query(Settlement).filter(Settlement.id == item_id).delete()
    db.commit()
    return {"status": "ok"}

@app.get("/api/company-bi")
def get_company_bi(start_date: str, end_date: str, db: Session = Depends(get_db)):
    s_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    orders = db.query(Order).filter(Order.booking_date >= s_d, Order.booking_date <= e_d, Order.status == "done", Order.is_collected == True).all()
    cash_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.cash])
    insta_rev = sum([float(o.price) for o in orders if o.payment_method == PaymentMethod.insta])
    total_rev = cash_rev + insta_rev
    total_washes = len(orders)
    shorouk_rev = sum([float(o.price) for o in orders if o.branch == "الشروق"])
    madinaty_rev = sum([float(o.price) for o in orders if o.branch == "مدينتي"])

    expenses = db.query(Expense).filter(Expense.expense_date >= s_d, Expense.expense_date <= e_d).all()
    opex_items = [e for e in expenses if e.expense_type not in ["سحوبات من المرتب", "سلفة"]]
    total_opex = sum([float(e.amount) for e in opex_items])
    opex_breakdown = {}
    for e in opex_items: 
        opex_breakdown[e.expense_type] = opex_breakdown.get(e.expense_type, 0) + int(e.amount)

    purchases = db.query(Purchase).filter(Purchase.purchase_date >= s_d, Purchase.purchase_date <= e_d).all()
    total_purchases = sum([float(p.amount) for p in purchases])
    admin_exps = db.query(AdminExpense).filter(AdminExpense.expense_date >= s_d, AdminExpense.expense_date <= e_d).all()
    total_admin = sum([float(a.amount) for a in admin_exps])

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    total_salaries_base = sum([float(e.basic_salary or 0) for e in employees])
    gross_operating_profit = total_rev - total_opex - total_purchases
    net_company_profit = gross_operating_profit - total_salaries_base - total_admin

    cost_per_wash = int(total_opex / total_washes) if total_washes > 0 else 0
    profit_per_wash = int(total_rev / total_washes) - cost_per_wash if total_washes > 0 else 0
    payroll_ratio = int((total_salaries_base / total_rev * 100)) if total_rev > 0 else 0

    return {
        "kpis": {
            "total_revenue": int(total_rev), 
            "cash_revenue": int(cash_rev), 
            "insta_revenue": int(insta_rev),
            "shorouk_revenue": int(shorouk_rev), 
            "madinaty_revenue": int(madinaty_rev), 
            "total_washes": total_washes,
            "total_opex": int(total_opex), 
            "total_purchases": int(total_purchases), 
            "total_admin": int(total_admin),
            "total_salaries": int(total_salaries_base), 
            "gross_profit": int(gross_operating_profit),
            "net_profit": int(net_company_profit), 
            "cost_per_wash": cost_per_wash, 
            "profit_per_wash": profit_per_wash,
            "payroll_ratio": payroll_ratio
        },
        "opex_breakdown": [{"category": k, "amount": v} for k, v in sorted(opex_breakdown.items(), key=lambda x: x[1], reverse=True)]
    }

@app.post("/api/employees")
def add_employee(name: str, salary: float = 0.0, db: Session = Depends(get_db)):
    if name.strip(): 
        db.add(Employee(name=name.strip(), basic_salary=salary))
        db.commit()
    return {"status": "ok"}

@app.put("/api/employees/{emp_id}")
def update_emp_salary(emp_id: int, salary: float, db: Session = Depends(get_db)):
    emp = db.query(Employee).get(emp_id)
    if emp: 
        emp.basic_salary = salary
        db.commit()
    return {"status": "ok"}

@app.delete("/api/employees/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    db.query(Employee).filter(Employee.id == emp_id).delete()
    db.commit()
    return {"status": "ok"}

@app.post("/api/categories")
def add_category(name: str, db: Session = Depends(get_db)):
    if name.strip(): 
        db.add(ExpenseCategory(name=name.strip()))
        db.commit()
    return {"status": "ok"}

@app.delete("/api/categories")
def delete_category(name: str, db: Session = Depends(get_db)):
    db.query(ExpenseCategory).filter(ExpenseCategory.name == name).delete()
    db.commit()
    return {"status": "ok"}

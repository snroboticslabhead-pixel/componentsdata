from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from config import Config
from models import db, Lab, Category, Component, Transaction
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from functools import wraps

IST = ZoneInfo("Asia/Kolkata")

# Predefined login credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

# ---------- Auth helper ---------- #
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow login page without authentication
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Dashboard helper ---------- #
def get_dashboard_stats():
    total_components = Component.query.count()
    total_transactions = Transaction.query.count()
    total_labs = Lab.query.count()
    total_categories = Category.query.count()
    pending_returns = Transaction.query.filter(
        Transaction.status.in_(['Issued', 'Partially Returned'])
    ).count()
    low_stock_components = Component.query.filter(
        Component.quantity <= Component.min_stock_level
    ).count()
    out_of_stock_components = Component.query.filter(
        Component.quantity <= 0
    ).count()

    # Use proper join and return Lab objects with component count
    lab_stats = db.session.query(
        Lab,
        db.func.count(Component.id).label('component_count')
    ).outerjoin(Component, Component.lab_id == Lab.id).group_by(Lab.id).all()
    
    # Convert to list of dictionaries for easier template access
    lab_stats_list = []
    for lab, component_count in lab_stats:
        lab_stats_list.append({
            'lab_name': lab.name,
            'component_count': component_count or 0
        })

    recent_transactions = Transaction.query.order_by(
        Transaction.issue_date.desc()
    ).limit(5).all()

    return {
        "total_components": total_components,
        "total_transactions": total_transactions,
        "total_labs": total_labs,
        "total_categories": total_categories,
        "pending_returns": pending_returns,
        "low_stock_components": low_stock_components,
        "out_of_stock_components": out_of_stock_components,
        "lab_stats": lab_stats_list,
        "recent_transactions": recent_transactions
    }

# ---------- Auth Routes ---------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, go to dashboard
    if session.get("logged_in"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

# ---------- Routes: Dashboard ---------- #
@app.route("/")
@login_required
def index():
    stats = get_dashboard_stats()
    trans_type_agg = db.session.query(
        Transaction.status, db.func.count(Transaction.id)
    ).group_by(Transaction.status).all()
    transaction_types = [t[0] or "Unknown" for t in trans_type_agg]
    transaction_counts = [t[1] for t in trans_type_agg]
    return render_template(
        "index.html",
        stats=stats,
        transaction_types=transaction_types,
        transaction_counts=transaction_counts,
    )

# ---------- Labs CRUD ---------- #
@app.route("/labs", methods=["GET", "POST"])
@login_required
def labs():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Lab name is required.", "danger")
        else:
            lab = Lab(name=name, location=location, description=description)
            db.session.add(lab)
            db.session.commit()
            flash("Lab added successfully.", "success")
            return redirect(url_for("labs"))
    labs_list = Lab.query.order_by(Lab.name).all()
    return render_template("labs.html", labs=labs_list)

@app.route("/labs/<int:lab_id>/edit", methods=["GET", "POST"])
@login_required
def edit_lab(lab_id):
    lab = Lab.query.get(lab_id)
    if not lab:
        flash("Lab not found.", "danger")
        return redirect(url_for("labs"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Lab name is required.", "danger")
        else:
            lab.name = name
            lab.location = location
            lab.description = description
            db.session.commit()
            flash("Lab updated successfully.", "success")
            return redirect(url_for("labs"))
    return render_template("edit_lab.html", lab=lab)

@app.route("/labs/<int:lab_id>/delete", methods=["POST"])
@login_required
def delete_lab(lab_id):
    lab = Lab.query.get(lab_id)
    if lab:
        db.session.delete(lab)
        db.session.commit()
        flash("Lab deleted.", "info")
    return redirect(url_for("labs"))

@app.route("/labs/<int:lab_id>/components")
@login_required
def lab_components(lab_id):
    lab = Lab.query.get(lab_id)
    if not lab:
        flash("Lab not found.", "danger")
        return redirect(url_for("labs"))
    components_list = Component.query.options(
        db.joinedload(Component.category),
        db.joinedload(Component.lab),
    ).filter_by(lab_id=lab_id).all()
    
    for c in components_list:
        qty = c.quantity or 0
        min_stock = c.min_stock_level or 0
        if qty <= 0:
            stock_state, stock_class = "Out of Stock", "out"
        elif qty <= min_stock:
            stock_state, stock_class = "Low Stock", "low"
        else:
            stock_state, stock_class = "In Stock", "instock"
        c.stock_state = stock_state
        c.stock_state_class = stock_class
        c.status_label = stock_state

    return render_template(
        "components.html",
        components=components_list,
        selected_lab=lab,
        selected_category=None,
    )

# ---------- Categories CRUD ---------- #
@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    labs = Lab.query.all()
    if request.method == "POST":
        lab_id = request.form.get("lab_id")
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not (lab_id and name):
            flash("Lab and Category name are required.", "danger")
        else:
            category = Category(
                name=name, description=description, lab_id=lab_id
            )
            db.session.add(category)
            db.session.commit()
            flash("Category added successfully.", "success")
            return redirect(url_for("categories"))
    
    # Use aggregation to get component count and total quantity, and load lab relationship
    results = db.session.query(
        Category,
        db.func.count(Component.id).label('component_count'),
        db.func.sum(Component.quantity).label('total_quantity')
    ).join(
        Component, Component.category_id == Category.id, isouter=True
    ).options(
        db.joinedload(Category.lab)
    ).group_by(Category.id).all()
    
    categories_list = []
    for result in results:
        category_data = {
            'id': result.Category.id,
            'name': result.Category.name,
            'description': result.Category.description,
            'lab': result.Category.lab,
            'created_at': result.Category.created_at,
            'component_count': result.component_count or 0,
            'total_quantity': result.total_quantity or 0
        }
        categories_list.append(category_data)
    
    return render_template(
        "categories.html",
        categories=categories_list,
        labs=labs,
    )

@app.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    category = Category.query.get(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for("categories"))
    labs = Lab.query.all()
    if request.method == "POST":
        lab_id = request.form.get("lab_id")
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not (lab_id and name):
            flash("Lab and Category name are required.", "danger")
        else:
            category.name = name
            category.description = description
            category.lab_id = lab_id
            db.session.commit()
            flash("Category updated successfully.", "success")
            return redirect(url_for("categories"))
    return render_template("edit_category.html", category=category, labs=labs)

@app.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    category = Category.query.get(category_id)
    if category:
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted.", "info")
    return redirect(url_for("categories"))

# ---------- NEW: Components by Category ---------- #
@app.route("/categories/<int:category_id>/components")
@login_required
def category_components(category_id):
    category = Category.query.get(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for("categories"))

    components_list = Component.query.options(
        db.joinedload(Component.category),
        db.joinedload(Component.lab),
    ).filter_by(category_id=category_id).all()

    # Reuse stock status logic
    for c in components_list:
        qty = c.quantity or 0
        min_stock = c.min_stock_level or 0
        if qty <= 0:
            stock_state, stock_class = "Out of Stock", "out"
        elif qty <= min_stock:
            stock_state, stock_class = "Low Stock", "low"
        else:
            stock_state, stock_class = "In Stock", "instock"
        c.stock_state = stock_state
        c.stock_state_class = stock_class
        c.status_label = stock_state

    return render_template(
        "components.html",
        components=components_list,
        selected_lab=None,
        selected_category=category,
    )

# ---------- Components CRUD ---------- #
@app.route("/components")
@login_required
def components():
    components_list = Component.query.options(
        db.joinedload(Component.category),
        db.joinedload(Component.lab),
    ).all()
    
    for c in components_list:
        qty = c.quantity or 0
        min_stock = c.min_stock_level or 0
        if qty <= 0:
            stock_state, stock_class = "Out of Stock", "out"
        elif qty <= min_stock:
            stock_state, stock_class = "Low Stock", "low"
        else:
            stock_state, stock_class = "In Stock", "instock"
        c.stock_state = stock_state
        c.stock_state_class = stock_class
        c.status_label = stock_state

    return render_template(
        "components.html",
        components=components_list,
        selected_lab=None,
        selected_category=None,
    )

@app.route("/components/add", methods=["GET", "POST"])
@login_required
def add_component():
    labs = Lab.query.all()
    categories = Category.query.all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id")
        lab_id = request.form.get("lab_id")
        quantity = int(request.form.get("quantity") or 0)
        min_stock_level = int(request.form.get("min_stock_level") or 0)
        unit = request.form.get("unit", "").strip()
        description = request.form.get("description", "").strip()
        component_type = request.form.get("component_type", "").strip() or "Other"
        if not (name and category_id and lab_id):
            flash("Name, category, and lab are required.", "danger")
        else:
            component = Component(
                name=name,
                category_id=category_id,
                lab_id=lab_id,
                quantity=quantity,
                min_stock_level=min_stock_level,
                unit=unit,
                description=description,
                component_type=component_type,
            )
            db.session.add(component)
            db.session.commit()
            flash("Component added successfully.", "success")
            return redirect(url_for("components"))
    return render_template(
        "add_component.html",
        labs=labs,
        categories=categories,
    )

@app.route("/components/<int:component_id>/edit", methods=["GET", "POST"])
@login_required
def edit_component(component_id):
    component = Component.query.options(
        db.joinedload(Component.category),
        db.joinedload(Component.lab),
    ).get(component_id)
    if not component:
        flash("Component not found.", "danger")
        return redirect(url_for("components"))
    labs = Lab.query.all()
    categories = Category.query.all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id")
        lab_id = request.form.get("lab_id")
        quantity = int(request.form.get("quantity") or 0)
        min_stock_level = int(request.form.get("min_stock_level") or 0)
        unit = request.form.get("unit", "").strip()
        description = request.form.get("description", "").strip()
        component_type = request.form.get("component_type", "").strip() or "Other"
        if not (name and category_id and lab_id):
            flash("Name, category, and lab are required.", "danger")
        else:
            component.name = name
            component.category_id = category_id
            component.lab_id = lab_id
            component.quantity = quantity
            component.min_stock_level = min_stock_level
            component.unit = unit
            component.description = description
            component.component_type = component_type
            component.last_updated = datetime.now(IST)
            db.session.commit()
            flash("Component updated successfully.", "success")
            return redirect(url_for("components"))
    return render_template(
        "edit_component.html",
        component=component,
        labs=labs,
        categories=categories,
    )

@app.route("/components/<int:component_id>/delete", methods=["POST"])
@login_required
def delete_component(component_id):
    component = Component.query.get(component_id)
    if component:
        db.session.delete(component)
        db.session.commit()
        flash("Component deleted.", "info")
    return redirect(url_for("components"))

# ---------- Transactions ---------- #
@app.route("/transactions")
@login_required
def transactions():
    transactions_list = Transaction.query.order_by(
        Transaction.issue_date.desc()
    ).all()
    status_agg = db.session.query(
        Transaction.status, db.func.count(Transaction.id)
    ).group_by(Transaction.status).all()
    status_counts = {item[0] or "Unknown": item[1] for item in status_agg}
    return render_template(
        "transactions.html",
        transactions=transactions_list,
        status_counts=status_counts,
    )

@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    components = Component.query.options(
        db.joinedload(Component.category),
        db.joinedload(Component.lab),
    ).order_by(Component.name).all()
    labs = Lab.query.all()
    
    for c in components:
        c.lab_id_str = str(c.lab_id) if c.lab_id else ""
    
    preselected_component_id = request.args.get("component_id")
    preselected_type = request.args.get("transaction_type") or "issue"
    preselected_lab_id = None
    if preselected_component_id:
        comp = Component.query.get(int(preselected_component_id))
        if comp and comp.lab_id:
            preselected_lab_id = str(comp.lab_id)

    if request.method == "POST":
        transaction_type = request.form.get("transaction_type")
        component_id = request.form.get("component_id")
        lab_id = request.form.get("from_lab_id") or None
        campus = request.form.get("from_campus", "").strip() or None
        person_name = request.form.get("person_name", "").strip()
        purpose = request.form.get("purpose", "").strip()
        notes = request.form.get("notes", "").strip()
        transaction_quantity_raw = request.form.get("transaction_quantity") or "0"

        preselected_component_id = component_id
        preselected_lab_id = lab_id
        preselected_type = transaction_type

        try:
            qty = int(transaction_quantity_raw)
        except ValueError:
            flash("Quantity must be a valid number.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )
        if qty <= 0:
            flash("Quantity must be greater than zero.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )
        if not lab_id:
            flash("Please select a lab first.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )
        if not component_id:
            flash("Please select a component.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )
        if not person_name or not purpose:
            flash("Person and Purpose are required.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )
        component = Component.query.get(int(component_id))
        if not component:
            flash("Component not found.", "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=None,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )

        try:
            if transaction_type == "issue":
                current_stock = component.quantity or 0
                if qty > current_stock:
                    raise ValueError(
                        f"Cannot issue {qty} units. Only {current_stock} available in stock."
                    )
                quantity_after = current_stock - qty
                lab_oid = int(lab_id) if lab_id else None
                campus = campus or None

                existing = Transaction.query.filter(
                    Transaction.component_id == component.id,
                    Transaction.lab_id == lab_oid,
                    Transaction.campus == campus,
                    Transaction.person_name == person_name,
                    Transaction.purpose == purpose,
                    Transaction.status.in_(['Issued', 'Partially Returned']),
                ).first()

                if existing:
                    new_issued = existing.qty_issued + qty
                    qty_returned = existing.qty_returned
                    pending = new_issued - qty_returned
                    status = (
                        "Issued"
                        if qty_returned == 0
                        else ("Completed" if pending <= 0 else "Partially Returned")
                    )
                    existing.qty_issued = new_issued
                    existing.pending_qty = pending
                    existing.status = status
                    existing.quantity_before = current_stock
                    existing.quantity_after = quantity_after
                    existing.transaction_quantity = qty
                    existing.last_action = "issue"
                    existing.date = datetime.now(IST)
                    existing.last_updated = datetime.now(IST)
                    existing.notes = notes or existing.notes
                    db.session.commit()
                else:
                    doc = Transaction(
                        component_id=component.id,
                        lab_id=lab_oid,
                        campus=campus,
                        person_name=person_name,
                        purpose=purpose,
                        qty_issued=qty,
                        qty_returned=0,
                        pending_qty=qty,
                        status="Issued",
                        issue_date=datetime.now(IST),
                        date=datetime.now(IST),
                        quantity_before=current_stock,
                        quantity_after=quantity_after,
                        transaction_quantity=qty,
                        last_action="issue",
                        notes=notes,
                        last_updated=datetime.now(IST),
                    )
                    db.session.add(doc)
                    db.session.commit()

                component.quantity = quantity_after
                component.last_updated = datetime.now(IST)
                db.session.commit()
            elif transaction_type == "return":
                current_stock = component.quantity or 0
                lab_oid = int(lab_id) if lab_id else None
                campus = campus or None

                existing = Transaction.query.filter(
                    Transaction.component_id == component.id,
                    Transaction.lab_id == lab_oid,
                    Transaction.campus == campus,
                    Transaction.person_name == person_name,
                    Transaction.purpose == purpose,
                    Transaction.status.in_(['Issued', 'Partially Returned']),
                ).first()
                if not existing:
                    raise ValueError(
                        "No matching issued transaction found to return against "
                        "(check Component / Lab / Campus / Person / Purpose)."
                    )

                qty_issued = existing.qty_issued
                qty_returned = existing.qty_returned
                pending = qty_issued - qty_returned

                if pending <= 0:
                    raise ValueError("No pending quantity left to return for this transaction.")
                if qty > pending:
                    raise ValueError(
                        f"Return quantity ({qty}) cannot exceed pending quantity ({pending})."
                    )

                new_returned = qty_returned + qty
                new_pending = qty_issued - new_returned
                status = "Completed" if new_pending <= 0 else "Partially Returned"
                quantity_after = current_stock + qty

                existing.qty_returned = new_returned
                existing.pending_qty = new_pending
                existing.status = status
                existing.quantity_before = current_stock
                existing.quantity_after = quantity_after
                existing.transaction_quantity = qty
                existing.last_action = "return"
                existing.date = datetime.now(IST)
                existing.last_updated = datetime.now(IST)
                existing.notes = (existing.notes or "") + (
                    f"\nReturn: {notes}" if notes else ""
                )
                db.session.commit()

                component.quantity = quantity_after
                component.last_updated = datetime.now(IST)
                db.session.commit()
            else:
                flash("Invalid transaction type.", "danger")
                return render_template(
                    "add_transaction.html",
                    components=components,
                    labs=labs,
                    preselected_component_id=preselected_component_id,
                    preselected_type=preselected_type,
                    preselected_lab_id=preselected_lab_id,
                )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "add_transaction.html",
                components=components,
                labs=labs,
                preselected_component_id=preselected_component_id,
                preselected_type=preselected_type,
                preselected_lab_id=preselected_lab_id,
            )

        flash("Transaction recorded successfully.", "success")
        return redirect(url_for("transactions"))

    return render_template(
        "add_transaction.html",
        components=components,
        labs=labs,
        preselected_component_id=preselected_component_id,
        preselected_type=preselected_type,
        preselected_lab_id=preselected_lab_id,
    )

@app.route("/transactions/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    txn = Transaction.query.get(transaction_id)
    if not txn:
        flash("Transaction not found.", "danger")
        return redirect(url_for("transactions"))

    component = Component.query.get(txn.component_id)
    lab = Lab.query.get(txn.lab_id) if txn.lab_id else None
    qty_issued = int(txn.qty_issued or 0)
    qty_returned = int(txn.qty_returned or 0)
    pending = int(txn.pending_qty or (qty_issued - qty_returned))

    if request.method == "POST":
        return_now_raw = request.form.get("return_now") or "0"
        notes = request.form.get("notes", "").strip()
        try:
            return_now = int(return_now_raw)
        except ValueError:
            flash("Return quantity must be a valid number.", "danger")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        if return_now <= 0:
            flash("No changes made (return quantity must be > 0).", "info")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        try:
            current_stock = component.quantity or 0
            lab_oid = txn.lab_id
            campus = txn.campus
            person_name = txn.person_name
            purpose = txn.purpose

            existing = Transaction.query.filter(
                Transaction.component_id == component.id,
                Transaction.lab_id == lab_oid,
                Transaction.campus == campus,
                Transaction.person_name == person_name,
                Transaction.purpose == purpose,
                Transaction.status.in_(['Issued', 'Partially Returned']),
            ).first()
            if not existing:
                raise ValueError(
                    "No matching issued transaction found to return against "
                    "(check Component / Lab / Campus / Person / Purpose)."
                )

            qty_issued = existing.qty_issued
            qty_returned = existing.qty_returned
            pending = qty_issued - qty_returned

            if pending <= 0:
                raise ValueError("No pending quantity left to return for this transaction.")
            if return_now > pending:
                raise ValueError(
                    f"Return quantity ({return_now}) cannot exceed pending quantity ({pending})."
                )

            new_returned = qty_returned + return_now
            new_pending = qty_issued - new_returned
            status = "Completed" if new_pending <= 0 else "Partially Returned"
            quantity_after = current_stock + return_now

            existing.qty_returned = new_returned
            existing.pending_qty = new_pending
            existing.status = status
            existing.quantity_before = current_stock
            existing.quantity_after = quantity_after
            existing.transaction_quantity = return_now
            existing.last_action = "return"
            existing.date = datetime.now(IST)
            existing.last_updated = datetime.now(IST)
            existing.notes = (existing.notes or "") + (
                f"\nReturn: {notes}" if notes else ""
            )
            db.session.commit()

            component.quantity = quantity_after
            component.last_updated = datetime.now(IST)
            db.session.commit()

            flash("Return transaction recorded successfully.", "success")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))

    return render_template(
        "edit_transaction.html",
        txn=txn,
        component=component,
        lab=lab,
        qty_issued=qty_issued,
        qty_returned=qty_returned,
        pending=pending,
    )

@app.route("/transactions/<int:transaction_id>/view")
@login_required
def view_transaction(transaction_id):
    return redirect(url_for("edit_transaction", transaction_id=transaction_id))

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",  # listen on all network interfaces
        port=5000,       # default Flask port
        debug=True       # you can set False in production
    )

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

# Create tables if not exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Homepage ----------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------------- Student Register ----------------
@app.get("/student/register", response_class=HTMLResponse)
async def student_register_page(request: Request):
    return templates.TemplateResponse("student_register.html", {"request": request})

@app.post("/student/register")
async def student_register(
    request: Request,
    student_id: str = Form(...),
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Create User
    user = models.User(username=username, password=password, role="student")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create Student
    student = models.Student(user_id=user.id, student_id=student_id, name=name)
    db.add(student)
    db.commit()

    return RedirectResponse(url="/student/login", status_code=303)

# ---------------- Student Login ----------------
@app.get("/student/login", response_class=HTMLResponse)
async def student_login_page(request: Request):
    return templates.TemplateResponse("student_login.html", {"request": request})

@app.post("/student/login")
async def student_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=username, password=password, role="student").first()
    if not user:
        return templates.TemplateResponse("student_login.html", {"request": request, "error": "Invalid credentials"})
    return RedirectResponse(url=f"/student/dashboard/{user.id}", status_code=303)

# ---------------- Student Dashboard ----------------
@app.get("/student/dashboard/{user_id}", response_class=HTMLResponse)
async def student_dashboard(request: Request, user_id: int, db: Session = Depends(get_db)):
    student = db.query(models.Student).filter_by(user_id=user_id).first()
    if not student:
        return HTMLResponse("Student not found", status_code=404)
    return templates.TemplateResponse("student_dashboard.html", {"request": request, "student": student})

# ---------------- Faculty Register ----------------
@app.get("/faculty/register", response_class=HTMLResponse)
async def faculty_register_page(request: Request):
    return templates.TemplateResponse("faculty_register.html", {"request": request})


@app.post("/faculty/register")
async def faculty_register(
    request: Request,
    faculty_id: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),   # <-- added department as input
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Create User
    user = models.User(username=username, password=password, role="faculty")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create Faculty
    faculty = models.Faculty(
        user_id=user.id,
        faculty_id=faculty_id,
        name=name,
        department=department
    )
    db.add(faculty)
    db.commit()

    # Redirect to login after registration
    return RedirectResponse(url="/faculty/login", status_code=303)


# ---------------- Faculty Login ----------------
@app.get("/faculty/login", response_class=HTMLResponse)
async def faculty_login_page(request: Request):
    return templates.TemplateResponse("faculty_login.html", {"request": request})


from fastapi import Response

@app.post("/faculty/login")
async def faculty_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter_by(username=username, password=password, role="faculty").first()
    if not user:
        return templates.TemplateResponse(
            "faculty_login.html",
            {"request": request, "error": "Invalid credentials"}
        )
    
    faculty = db.query(models.Faculty).filter_by(user_id=user.id).first()

    # Set faculty_id in cookie
    response = RedirectResponse(url="/faculty/dashboard", status_code=303)
    response.set_cookie(key="faculty_id", value=str(faculty.id))
    return response



@app.get("/faculty/dashboard", response_class=HTMLResponse)
async def faculty_dashboard(request: Request, db: Session = Depends(get_db)):
    faculty_id = request.cookies.get("faculty_id")
    if not faculty_id:
        return RedirectResponse(url="/faculty/login", status_code=303)

    faculty = db.query(models.Faculty).filter_by(id=int(faculty_id)).first()
    if not faculty:
        return RedirectResponse(url="/faculty/login", status_code=303)

    return templates.TemplateResponse(
        "faculty_dashboard.html",
        {"request": request, "faculty": faculty}
    )

@app.get("/faculty/logout")
async def faculty_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="faculty_id")
    return response



from sqlalchemy import or_

@app.get("/faculty/students/{faculty_id}", response_class=HTMLResponse)
async def faculty_students(request: Request, faculty_id: int, q: str = None, db: Session = Depends(get_db)):
    faculty = db.query(models.Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        return HTMLResponse("Faculty not found", status_code=404)

    query = db.query(models.Student)

    # Apply search filter if query present
    if q:
        query = query.filter(
            or_(
                models.Student.student_id.like(f"%{q}%"),
                models.Student.name.like(f"%{q}%")
            )
        )

    students = query.all()

    return templates.TemplateResponse("faculty_students.html", {
        "request": request,
        "faculty": faculty,
        "students": students,
        "query": q
    })


import qrcode
import io
from fastapi.responses import StreamingResponse
from fastapi import Query

# In-memory attendance sessions storage
attendance_sessions = {}

@app.get("/faculty/generate_qr")
def generate_qr(faculty_id: int = Query(..., description="Faculty ID")):
    import uuid
    session_id = str(uuid.uuid4())  # unique session ID
    # Store session in memory (in production, store in DB)
    attendance_sessions[session_id] = {"faculty_id": faculty_id, "students": []}

    # QR points students to scan route
    qr_data = f"http://127.0.0.1:8000/student/scan_qr/{session_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/student/scan_qr/{session_id}", response_class=HTMLResponse)
async def scan_qr(request: Request, session_id: str):
    # Check if session exists
    if session_id not in attendance_sessions:
        return HTMLResponse("<h3>Invalid QR Session!</h3>", status_code=404)

    return templates.TemplateResponse("student_scan.html", {
        "request": request,
        "session_id": session_id
    })

from fastapi.responses import JSONResponse

@app.post("/student/mark_attendance/{session_id}")
def mark_attendance(session_id: str):
    if session_id not in attendance_sessions:
        return JSONResponse({"message": "Invalid session!"}, status_code=404)

    # In real app, get student info from login/cookies
    student_name = "Demo Student"
    attendance_sessions[session_id]["students"].append(student_name)

    return JSONResponse({"message": f"Attendance marked for {student_name}!"})


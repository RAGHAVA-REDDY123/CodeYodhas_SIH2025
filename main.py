from fastapi import FastAPI, Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import models
from database import SessionLocal, engine
import io, os, json, cv2, numpy as np
from datetime import datetime
from passlib.context import CryptContext
from PIL import Image
from deepface import DeepFace
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# ---------------- Database setup ----------------
models.Base.metadata.create_all(bind=engine)
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------- Dependency ----------------
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

# =====================================================================
#                               STUDENT
# =====================================================================

@app.get("/student/register", response_class=HTMLResponse)
async def student_register_page(request: Request):
    return templates.TemplateResponse("student_register.html", {"request": request})


@app.post("/student/register")
async def student_register(
    student_id: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),
    password: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Check if a student with the same ID already exists
    existing_student = db.query(models.Student).filter_by(student_id=student_id).first()
    if existing_student:
        raise HTTPException(status_code=400, detail="❌ Student with this ID already registered.")

    # Save photo temporarily
    contents = await photo.read()
    temp_path = f"temp_{student_id}.jpg"
    with open(temp_path, "wb") as f:
        f.write(contents)

    try:
        # Extract embedding using DeepFace
        result = DeepFace.represent(img_path=temp_path, model_name="Facenet")[0]
        embedding = result["embedding"]
        encoding_json = json.dumps(embedding)
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail=f"❌ Face encoding failed: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Password hashing
    hashed_password = pwd_context.hash(password)

    # Save in DB
    new_user = models.User(
    user_id=student_id,     # ✅ set this!
    password=hashed_password,
    role="student"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    new_student = models.Student(
        student_id=student_id,
        name=name,
        department=department,
        face_encodings=encoding_json,
        user_id=new_user.id
    )
    db.add(new_student)
    db.commit()

    return RedirectResponse(url="/student/login", status_code=303)


@app.get("/student/login", response_class=HTMLResponse)
async def student_login_page(request: Request):
    return templates.TemplateResponse("student_login.html", {"request": request})


@app.post("/student/login")
async def student_login(
    request: Request,
    student_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    student = db.query(models.Student).filter_by(student_id=student_id).first()
    if not student:
        return templates.TemplateResponse("student_login.html", {"request": request, "error": "❌ Invalid student ID"})

    user = db.query(models.User).filter_by(id=student.user_id, role="student").first()
    if not user or not pwd_context.verify(password, user.password):
        return templates.TemplateResponse("student_login.html", {"request": request, "error": "❌ Incorrect password"})

    response = RedirectResponse(url=f"/student/dashboard/{student.id}", status_code=303)
    response.set_cookie(key="student_id", value=str(student.id))
    return response


@app.get("/student/dashboard/{student_id}", response_class=HTMLResponse)
async def student_dashboard(request: Request, student_id: int, db: Session = Depends(get_db)):
    student = db.query(models.Student).filter_by(id=student_id).first()
    if not student:
        return HTMLResponse("Student not found", status_code=404)
    return templates.TemplateResponse("student_dashboard.html", {"request": request, "student": student})


@app.get("/student/mark_attendance/{student_id}")
async def mark_attendance(student_id: int, db: Session = Depends(get_db)):
    """Opens webcam, verifies face embedding with DeepFace"""
    student = db.query(models.Student).filter_by(id=student_id).first()
    if not student:
        return JSONResponse({"message": "Student not found"}, status_code=404)

    known_embedding = np.array(json.loads(student.face_encodings))

    cap = cv2.VideoCapture(0)
    matched = False

    if not cap.isOpened():
        return JSONResponse({"message": "❌ Could not access webcam"}, status_code=500)

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            # Save frame temporarily for DeepFace
            temp_frame_path = "temp_frame.jpg"
            cv2.imwrite(temp_frame_path, frame)

            try:
                result = DeepFace.represent(img_path=temp_frame_path, model_name="Facenet")[0]
                new_embedding = np.array(result["embedding"])

                # Cosine similarity
                similarity = np.dot(known_embedding, new_embedding) / (
                    np.linalg.norm(known_embedding) * np.linalg.norm(new_embedding)
                )

                if similarity > 0.7:  # threshold
                    matched = True
                    break
            except Exception:
                pass
            finally:
                if os.path.exists(temp_frame_path):
                    os.remove(temp_frame_path)

            cv2.imshow("Face Verification - Press 'q' to exit", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if matched:
        attendance = models.Attendance(student_id=student.id, timestamp=datetime.utcnow())
        db.add(attendance)
        db.commit()
        return JSONResponse({"message": f"✅ Attendance marked for {student.name}"})
    else:
        return JSONResponse({"message": "❌ Face not verified"}, status_code=403)

@app.get("/student/logout")
async def student_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="student_id")
    return response

# =====================================================================
#                               FACULTY
# =====================================================================

@app.get("/faculty/register", response_class=HTMLResponse)
async def faculty_register_page(request: Request):
    return templates.TemplateResponse("faculty_register.html", {"request": request})

@app.post("/faculty/register")
async def faculty_register(
    faculty_id: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = models.User(user_id=faculty_id, password=password, role="faculty")
    db.add(user)
    db.commit()
    db.refresh(user)

    faculty = models.Faculty(user_id=user.id, faculty_id=faculty_id, name=name, department=department)
    db.add(faculty)
    db.commit()

    return RedirectResponse(url="/faculty/login", status_code=303)

@app.get("/faculty/login", response_class=HTMLResponse)
async def faculty_login_page(request: Request):
    return templates.TemplateResponse("faculty_login.html", {"request": request})

@app.post("/faculty/login")
async def faculty_login(
    request: Request,
    faculty_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    faculty = db.query(models.Faculty).filter_by(faculty_id=faculty_id).first()
    if not faculty:
        return templates.TemplateResponse("faculty_login.html", {"request": request, "error": "❌ Invalid faculty ID"})

    user = db.query(models.User).filter_by(id=faculty.user_id, password=password, role="faculty").first()
    if not user:
        return templates.TemplateResponse("faculty_login.html", {"request": request, "error": "❌ Incorrect password"})

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
    return templates.TemplateResponse("faculty_dashboard.html", {"request": request, "faculty": faculty})

@app.get("/faculty/logout")
async def faculty_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="faculty_id")
    return response

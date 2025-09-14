from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime,Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


# ---------------- User Model ----------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, nullable=False)  # student_id / faculty_id
    password = Column(String(100), nullable=False)
    role = Column(Enum("admin", "faculty", "student", name="user_roles"), nullable=False)

    # Relationships
    student = relationship("Student", back_populates="user", uselist=False)
    faculty = relationship("Faculty", back_populates="user", uselist=False)


# ---------------- Student Model ----------------
class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(String(20), unique=True, nullable=False)  # roll number
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    face_encodings = Column(Text, nullable=False)  # optional

    user = relationship("User", back_populates="student")
    attendances = relationship("Attendance", back_populates="student")  # ✅ added

# ---------------- Faculty Model ----------------
class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    faculty_id = Column(String(20), unique=True, nullable=False)  # faculty code
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)

    user = relationship("User", back_populates="faculty")


# ---------------- Attendance Model ----------------
class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="attendances")

# ⚡ WorkPulseAI

### AI-Powered Workplace Surveillance & Workforce Intelligence Platform

WorkPulseAI is a computer-vision-based workplace monitoring platform designed to provide real-time employee recognition, attendance monitoring, activity analysis, security alerts, and workforce analytics through a centralized web application.

The system uses **Python, Flask, OpenCV, SQLite, and computer vision techniques** to transform a standard camera into an intelligent workplace monitoring system.

---

## 🚀 Overview

WorkPulseAI combines employee management, face recognition, live surveillance, attendance tracking, productivity monitoring, security event detection, analytics, and AI-assisted reporting into a single web-based platform.

The system provides two primary modes:

### 🔓 Public Camera Preview

Users who are not authenticated can access the camera preview to verify that the camera and detection system are functioning.

Identity information and administrative data are protected from unauthenticated users.

### 🔐 Authenticated Admin Dashboard

After login, administrators can access the complete WorkPulseAI platform, including:

- Employee registration and management
- Face recognition
- Attendance monitoring
- Unknown face management
- Live surveillance
- Analytics
- AI-generated reports
- Security alerts
- Camera configuration
- Operational settings

---

# ✨ Key Features

## 👤 Authentication

- User signup and login
- Authenticated administrative dashboard
- Session-based access control
- Protected employee and analytics information

---

## 👨‍💼 Employee Management

Administrators can create and manage employee profiles containing:

- Full name
- Position / designation
- Department
- Uniform information
- Registration date
- Face registration data

Employees can also be edited or removed through the Staff Directory.

---

## 📸 Multi-Angle Face Registration

WorkPulseAI supports multi-angle employee face registration.

During registration, the system can capture multiple facial samples while prompting the employee to change their head direction.

These samples are used to improve recognition reliability under different viewing angles.

Example registration workflow:

```text
Start Camera
      ↓
Capture Front Face
      ↓
Capture Left Angle
      ↓
Capture Right Angle
      ↓
Capture Additional Angles
      ↓
Register Employee

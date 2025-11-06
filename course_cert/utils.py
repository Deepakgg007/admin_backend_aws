from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_CENTER
from django.utils import timezone


def generate_certificate_pdf(attempt):
    """
    Generate a professional certificate PDF for a passed certification attempt
    
    Args:
        attempt: CertificationAttempt instance
    
    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()
    
    # Create PDF with A4 landscape orientation
    p = canvas.Canvas(buffer, pagesize=(A4[1], A4[0]))  # Landscape
    width, height = A4[1], A4[0]
    
    # Draw border
    p.setStrokeColor(colors.HexColor("#1e40af"))  # Blue border
    p.setLineWidth(3)
    p.rect(30, 30, width - 60, height - 60, stroke=1, fill=0)
    
    # Inner decorative border
    p.setStrokeColor(colors.HexColor("#3b82f6"))
    p.setLineWidth(1)
    p.rect(40, 40, width - 80, height - 80, stroke=1, fill=0)
    
    # Title
    p.setFont("Helvetica-Bold", 36)
    p.setFillColor(colors.HexColor("#1e40af"))
    p.drawCentredString(width / 2, height - 100, "CERTIFICATE OF COMPLETION")
    
    # Decorative line under title
    p.setStrokeColor(colors.HexColor("#3b82f6"))
    p.setLineWidth(2)
    p.line(150, height - 120, width - 150, height - 120)
    
    # "This is to certify that"
    p.setFont("Helvetica", 16)
    p.setFillColor(colors.black)
    p.drawCentredString(width / 2, height - 170, "This is to certify that")
    
    # Student name
    p.setFont("Helvetica-Bold", 28)
    p.setFillColor(colors.HexColor("#1e40af"))
    student_name = attempt.user.get_full_name() or attempt.user.username
    p.drawCentredString(width / 2, height - 220, student_name)
    
    # Underline for name
    name_width = p.stringWidth(student_name, "Helvetica-Bold", 28)
    p.setStrokeColor(colors.HexColor("#3b82f6"))
    p.setLineWidth(1)
    p.line(
        width / 2 - name_width / 2 - 20, 
        height - 230, 
        width / 2 + name_width / 2 + 20, 
        height - 230
    )
    
    # "has successfully completed"
    p.setFont("Helvetica", 16)
    p.setFillColor(colors.black)
    p.drawCentredString(width / 2, height - 270, "has successfully completed")
    
    # Certification title
    p.setFont("Helvetica-Bold", 22)
    p.setFillColor(colors.HexColor("#1e40af"))
    cert_title = attempt.certification.title
    p.drawCentredString(width / 2, height - 320, cert_title)
    
    # Course name
    p.setFont("Helvetica", 14)
    p.setFillColor(colors.black)
    course_name = f"Course: {attempt.certification.course.title}"
    p.drawCentredString(width / 2, height - 350, course_name)
    
    # Score information
    p.setFont("Helvetica-Bold", 14)
    score_text = f"Score: {attempt.score}% (Passing: {attempt.certification.passing_score}%)"
    p.drawCentredString(width / 2, height - 390, score_text)
    
    # Date completed
    p.setFont("Helvetica", 12)
    date_completed = attempt.completed_at.strftime("%B %d, %Y")
    p.drawCentredString(width / 2, height - 430, f"Date of Completion: {date_completed}")
    
    # Certificate ID
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.grey)
    cert_id = f"Certificate ID: CERT-{attempt.id}-{attempt.user.id}"
    p.drawCentredString(width / 2, 60, cert_id)
    
    # Signature line (placeholder - you can add actual signatures)
    p.setStrokeColor(colors.black)
    p.setLineWidth(1)
    
    # Left signature
    p.line(100, 120, 250, 120)
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.black)
    p.drawCentredString(175, 100, "Instructor Signature")
    
    # Right signature
    p.line(width - 250, 120, width - 100, 120)
    p.drawCentredString(width - 175, 100, "Administrator Signature")
    
    # Finalize PDF
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer


def generate_simple_certificate_pdf(attempt):
    """
    Generate a simpler certificate PDF (alternative version)
    Useful if reportlab styling becomes complex
    """
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Simple border
    p.rect(50, 50, width - 100, height - 100, stroke=1, fill=0)
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.drawCentredString(width / 2, height - 100, "Certificate of Completion")
    
    # Content
    p.setFont("Helvetica", 14)
    y_position = height - 200
    
    lines = [
        f"This certifies that",
        "",
        f"{attempt.user.get_full_name() or attempt.user.username}",
        "",
        f"has successfully completed",
        "",
        f"{attempt.certification.title}",
        "",
        f"Course: {attempt.certification.course.title}",
        "",
        f"Score: {attempt.score}%",
        f"Date: {attempt.completed_at.strftime('%B %d, %Y')}",
    ]
    
    for line in lines:
        if line == lines[2]:  # Student name
            p.setFont("Helvetica-Bold", 16)
        elif line == lines[6]:  # Certification title
            p.setFont("Helvetica-Bold", 14)
        else:
            p.setFont("Helvetica", 12)
        
        p.drawCentredString(width / 2, y_position, line)
        y_position -= 30
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer
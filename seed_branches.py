import os
import uuid
from app import create_app
from app.extensions import db
from app.models.academic import Institution, Department, Degree, Program, AcademicSession, Semester, Subject

BRANCHES_DATA = [
    {
        "code": "AI",
        "short_name": "AI",
        "name": "Artificial Intelligence and Machine Learning",
        "dept_name": "Department of Artificial Intelligence",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("AI101", "Introduction to Artificial Intelligence", 4),
            ("AI201", "Machine Learning & Statistical Foundations", 4),
            ("AI301", "Deep Learning & Neural Networks", 4),
            ("AI401", "Natural Language Processing & LLMs", 3),
        ]
    },
    {
        "code": "CSE",
        "short_name": "CSE",
        "name": "Computer Science Engineering",
        "dept_name": "Department of Computer Science & Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("CS101", "Data Structures & Algorithms", 4),
            ("CS102", "Database Management Systems", 4),
            ("CS201", "Operating Systems & Systems Programming", 4),
            ("CS301", "Design and Analysis of Algorithms", 4),
            ("CS302", "Computer Networks & Distributed Systems", 3),
        ]
    },
    {
        "code": "IT",
        "short_name": "IT",
        "name": "Information Technology",
        "dept_name": "Department of Information Technology",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("IT101", "Web Architecture & Cloud Services", 4),
            ("IT201", "Information Security & Cryptography", 4),
            ("IT301", "DevOps & Cloud Native Architecture", 3),
        ]
    },
    {
        "code": "Cyber Security",
        "short_name": "Cyber Security",
        "name": "Cyber Security and Information Assurance",
        "dept_name": "Department of Information Security",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("CY101", "Network Security Fundamentals", 4),
            ("CY201", "Ethical Hacking & Vulnerability Assessment", 4),
            ("CY301", "Digital Forensics & Incident Response", 3),
        ]
    },
    {
        "code": "Civil",
        "short_name": "Civil",
        "name": "Civil Engineering",
        "dept_name": "Department of Civil Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("CE101", "Structural Analysis & Mechanics", 4),
            ("CE201", "Geotechnical & Foundation Engineering", 4),
            ("CE301", "Environmental Engineering & Hydrology", 3),
        ]
    },
    {
        "code": "Mechanical",
        "short_name": "Mechanical",
        "name": "Mechanical Engineering",
        "dept_name": "Department of Mechanical Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("ME101", "Engineering Thermodynamics & Fluid Mechanics", 4),
            ("ME201", "Kinematics & Dynamics of Machinery", 4),
            ("ME301", "Computer-Aided Design & Manufacturing (CAD/CAM)", 4),
        ]
    },
    {
        "code": "Electrical",
        "short_name": "Electrical",
        "name": "Electrical and Electronics Engineering",
        "dept_name": "Department of Electrical Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("EE101", "Circuit Analysis & Electromagnetic Fields", 4),
            ("EE201", "Power Systems & Renewable Energy", 4),
            ("EE301", "Control Systems Engineering", 3),
        ]
    },
    {
        "code": "Electronics",
        "short_name": "Electronics",
        "name": "Electronics and Communication Engineering",
        "dept_name": "Department of Electronics & Communication",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("EC101", "Digital Signal Processing", 4),
            ("EC201", "VLSI Design & Embedded Systems", 4),
            ("EC301", "Wireless & Mobile Communications", 3),
        ]
    },
    {
        "code": "Data Science",
        "short_name": "Data Science",
        "name": "Data Science and Analytics",
        "dept_name": "Department of Data Science",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("DS101", "Foundations of Data Science & Big Data", 4),
            ("DS201", "Applied Predictive Modeling & Statistics", 4),
            ("DS301", "Business Intelligence & Data Visualization", 3),
        ]
    },
    {
        "code": "Aerospace",
        "short_name": "Aerospace",
        "name": "Aerospace Engineering",
        "dept_name": "Department of Aerospace Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("AE101", "Aerodynamics & Flight Dynamics", 4),
            ("AE201", "Rocket Propulsion & Gas Turbines", 4),
            ("AE301", "Aircraft Structures & Materials", 3),
        ]
    },
    {
        "code": "Automobile",
        "short_name": "Automobile",
        "name": "Automobile Engineering",
        "dept_name": "Department of Automobile Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("AU101", "Automotive Chassis & Transmission Systems", 4),
            ("AU201", "Electric Vehicles & Powertrain Engineering", 4),
            ("AU301", "Autonomous Driving Systems & Telematics", 3),
        ]
    },
    {
        "code": "Chemical",
        "short_name": "Chemical",
        "name": "Chemical Engineering",
        "dept_name": "Department of Chemical Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("CH101", "Chemical Reaction Engineering", 4),
            ("CH201", "Mass Transfer Operations", 4),
            ("CH301", "Process Dynamics & Plant Automation", 3),
        ]
    },
    {
        "code": "Instrumentation",
        "short_name": "Instrumentation",
        "name": "Instrumentation and Control Engineering",
        "dept_name": "Department of Instrumentation Engineering",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("IC101", "Sensors & Measurement Technology", 4),
            ("IC201", "Industrial Process Control & PLC Systems", 4),
            ("IC301", "Biomedical Instrumentation", 3),
        ]
    },
    {
        "code": "Biotechnology",
        "short_name": "Biotechnology",
        "name": "Biotechnology",
        "dept_name": "Department of Biotechnology",
        "degree_name": "Bachelor of Technology",
        "degree_level": "Undergraduate",
        "courses": [
            ("BT101", "Molecular Biology & Genetic Engineering", 4),
            ("BT201", "Bioprocess Engineering & Fermentation", 4),
            ("BT301", "Bioinformatics & Computational Genomics", 3),
        ]
    },
    {
        "code": "B.Pharm",
        "short_name": "B.Pharm",
        "name": "Bachelor of Pharmacy",
        "dept_name": "Department of Pharmaceutical Sciences",
        "degree_name": "Bachelor of Pharmacy",
        "degree_level": "Undergraduate",
        "courses": [
            ("BP101", "Human Anatomy & Physiology", 4),
            ("BP201", "Pharmaceutical Organic Chemistry", 4),
            ("BP301", "Pharmacology & Therapeutics", 4),
        ]
    },
    {
        "code": "D.Pharm",
        "short_name": "D.Pharm",
        "name": "Diploma in Pharmacy",
        "dept_name": "School of Pharmacy",
        "degree_name": "Diploma in Pharmacy",
        "degree_level": "Diploma",
        "courses": [
            ("DP101", "Pharmaceutics & Dispensing Procedures", 3),
            ("DP102", "Pharmacognosy & Community Pharmacy", 3),
        ]
    },
    {
        "code": "Forensic Science",
        "short_name": "Forensic Science",
        "name": "Forensic Science",
        "dept_name": "Department of Forensic Sciences",
        "degree_name": "Bachelor of Science",
        "degree_level": "Undergraduate",
        "courses": [
            ("FS101", "Criminalistics & Crime Scene Forensics", 4),
            ("FS201", "Forensic Ballistics & Fingerprint Analysis", 4),
            ("FS301", "Forensic Toxicology & Serology", 3),
        ]
    },
    {
        "code": "Agriculture",
        "short_name": "Agriculture",
        "name": "Agriculture",
        "dept_name": "Faculty of Agriculture & Agro-Technology",
        "degree_name": "Bachelor of Science",
        "degree_level": "Undergraduate",
        "courses": [
            ("AG101", "Agronomy & Sustainable Crop Production", 4),
            ("AG201", "Soil Science & Agricultural Chemistry", 4),
            ("AG301", "Horticulture & Plant Pathology", 3),
        ]
    },
    {
        "code": "Architecture",
        "short_name": "Architecture",
        "name": "Architecture",
        "dept_name": "School of Architecture & Planning",
        "degree_name": "Bachelor of Architecture",
        "degree_level": "Undergraduate",
        "courses": [
            ("AR101", "Architectural Design Studio I", 5),
            ("AR201", "Building Construction & Advanced Materials", 4),
            ("AR301", "Sustainable Urban Planning & Architecture", 3),
        ]
    },
    {
        "code": "Other",
        "short_name": "Other",
        "name": "Other Academic Programs",
        "dept_name": "Interdisciplinary Studies",
        "degree_name": "General Certification",
        "degree_level": "Interdisciplinary",
        "courses": [
            ("GN101", "Professional Communication & Ethics", 2),
            ("GN201", "Environmental Studies & Disaster Management", 2),
        ]
    }
]

def run():
    app = create_app("development")
    with app.app_context():
        inst = db.session.query(Institution).first()
        if not inst:
            print("No institution found! Run seed.py first.")
            return

        session = db.session.query(AcademicSession).first()
        if not session:
            session = AcademicSession(name="2025-2026", start_year=2025, end_year=2026)
            db.session.add(session)
            db.session.flush()

        sem = db.session.query(Semester).filter_by(academic_session_id=session.id).first()
        if not sem:
            sem = Semester(name="Fall 2025", academic_session_id=session.id, number=1, is_active=True)
            db.session.add(sem)
            db.session.flush()

        # Cache degrees
        degrees_cache = {}
        for d_name, d_lvl in [
            ("Bachelor of Technology", "Undergraduate"),
            ("Bachelor of Pharmacy", "Undergraduate"),
            ("Diploma in Pharmacy", "Diploma"),
            ("Bachelor of Science", "Undergraduate"),
            ("Bachelor of Architecture", "Undergraduate"),
            ("General Certification", "Interdisciplinary"),
        ]:
            deg = db.session.query(Degree).filter_by(name=d_name).first()
            if not deg:
                deg = Degree(name=d_name, level=d_lvl)
                db.session.add(deg)
                db.session.flush()
            degrees_cache[d_name] = deg

        total_courses_created = 0
        total_depts = 0

        for b in BRANCHES_DATA:
            dept = db.session.query(Department).filter_by(name=b["dept_name"], institution_id=inst.id).first()
            if not dept:
                dept = Department(name=b["dept_name"], institution_id=inst.id)
                db.session.add(dept)
                db.session.flush()
                total_depts += 1

            deg = degrees_cache.get(b["degree_name"]) or list(degrees_cache.values())[0]

            prog = db.session.query(Program).filter_by(name=b["name"], department_id=dept.id).first()
            if not prog:
                prog = Program(name=b["name"], department_id=dept.id, degree_id=deg.id)
                db.session.add(prog)
                db.session.flush()

            for c_code, c_name, c_credits in b["courses"]:
                subj = db.session.query(Subject).filter_by(code=c_code).first()
                if not subj:
                    subj = Subject(
                        code=c_code,
                        name=c_name,
                        program_id=prog.id,
                        semester_id=sem.id,
                        credits=c_credits
                    )
                    db.session.add(subj)
                    total_courses_created += 1

        db.session.commit()
        print(f"[SUCCESS] Seeded {len(BRANCHES_DATA)} Academic Branches!")
        print(f"Created {total_depts} new departments and {total_courses_created} new courses.")

if __name__ == "__main__":
    run()

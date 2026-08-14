import os

base_dir = r'C:\Users\ASUS\.gemini\antigravity\scratch\campusx'
css_dir = os.path.join(base_dir, 'app', 'static', 'css')
js_dir = os.path.join(base_dir, 'app', 'static', 'js')
templates_dir = os.path.join(base_dir, 'app', 'templates')

for d in [css_dir, js_dir, templates_dir, 
          os.path.join(templates_dir, 'auth'),
          os.path.join(templates_dir, 'student'),
          os.path.join(templates_dir, 'faculty'),
          os.path.join(templates_dir, 'admin'),
          os.path.join(templates_dir, 'shared')]:
    os.makedirs(d, exist_ok=True)

files = {}

# CSS Files
files[os.path.join(css_dir, 'design-system.css')] = '''
:root {
    --lumina-primary: #6366f1;
    --lumina-primary-hover: #4f46e5;
    --lumina-bg-light: #f8fafc;
    --lumina-surface-light: #ffffff;
    --lumina-text-light: #1e293b;
    --lumina-text-muted-light: #64748b;
    --lumina-glass-bg-light: rgba(255, 255, 255, 0.7);
    --lumina-glass-border-light: rgba(255, 255, 255, 0.3);
    
    --lumina-bg-dark: #0f172a;
    --lumina-surface-dark: #1e293b;
    --lumina-text-dark: #f8fafc;
    --lumina-text-muted-dark: #94a3b8;
    --lumina-glass-bg-dark: rgba(30, 41, 59, 0.7);
    --lumina-glass-border-dark: rgba(255, 255, 255, 0.1);

    --lumina-radius: 12px;
    --lumina-transition: 0.3s ease;
}

[data-theme=\"dark\"] {
    --bg-color: var(--lumina-bg-dark);
    --surface-color: var(--lumina-surface-dark);
    --text-color: var(--lumina-text-dark);
    --text-muted: var(--lumina-text-muted-dark);
    --glass-bg: var(--lumina-glass-bg-dark);
    --glass-border: var(--lumina-glass-border-dark);
}

[data-theme=\"light\"] {
    --bg-color: var(--lumina-bg-light);
    --surface-color: var(--lumina-surface-light);
    --text-color: var(--lumina-text-light);
    --text-muted: var(--lumina-text-muted-light);
    --glass-bg: var(--lumina-glass-bg-light);
    --glass-border: var(--lumina-glass-border-light);
}

body {
    background-color: var(--bg-color);
    color: var(--text-color);
    font-family: 'Inter', sans-serif;
    transition: background-color var(--lumina-transition), color var(--lumina-transition);
    margin: 0;
    padding: 0;
}
'''

files[os.path.join(css_dir, 'components.css')] = '''
.glass-panel {
    background: var(--glass-bg);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid var(--glass-border);
    border-radius: var(--lumina-radius);
    padding: 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.btn-primary {
    background-color: var(--lumina-primary);
    color: white;
    padding: 10px 20px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    transition: background-color var(--lumina-transition);
}

.btn-primary:hover {
    background-color: var(--lumina-primary-hover);
}
'''

files[os.path.join(css_dir, 'layout.css')] = '''
.app-container {
    display: flex;
    min-height: 100vh;
}
.sidebar {
    width: 250px;
    background-color: var(--surface-color);
    padding: 20px;
    border-right: 1px solid var(--glass-border);
}
.main-content {
    flex: 1;
    padding: 20px;
}
'''

files[os.path.join(css_dir, 'utilities.css')] = '''
.mt-4 { margin-top: 1rem; }
.mb-4 { margin-bottom: 1rem; }
.p-4 { padding: 1rem; }
.text-center { text-align: center; }
.flex { display: flex; }
.justify-between { justify-content: space-between; }
'''

# JS Files
files[os.path.join(js_dir, 'app.js')] = '''
document.addEventListener('alpine:init', () => {
    Alpine.store('theme', {
        mode: localStorage.getItem('theme') || 'light',
        toggle() {
            this.mode = this.mode === 'light' ? 'dark' : 'light';
            localStorage.setItem('theme', this.mode);
            document.documentElement.setAttribute('data-theme', this.mode);
        }
    });
});
'''
files[os.path.join(js_dir, 'chat.js')] = 'console.log("Chat initialized");'
files[os.path.join(js_dir, 'search.js')] = 'console.log("Search initialized");'
files[os.path.join(js_dir, 'upload.js')] = 'console.log("Upload initialized");'
files[os.path.join(js_dir, 'quiz.js')] = 'console.log("Quiz initialized");'
files[os.path.join(js_dir, 'qr.js')] = 'console.log("QR initialized");'

# Templates Base
files[os.path.join(templates_dir, 'base.html')] = '''<!DOCTYPE html>
<html lang="en" data-theme="light" x-data :data-theme=".theme.mode">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CampusX</title>
    <link href="/static/css/design-system.css" rel="stylesheet">
    <link href="/static/css/layout.css" rel="stylesheet">
    <link href="/static/css/components.css" rel="stylesheet">
    <link href="/static/css/utilities.css" rel="stylesheet">
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <script src="/static/js/app.js"></script>
</head>
<body>
    <div class="app-container">
        <aside class="sidebar glass-panel">
            <h2>CampusX</h2>
            <button @click=".theme.toggle()" class="btn-primary mt-4">Toggle Theme</button>
            <nav class="mt-4">
                {% block sidebar %}{% endblock %}
            </nav>
        </aside>
        <main class="main-content">
            {% block content %}{% endblock %}
        </main>
    </div>
</body>
</html>'''

# Admin Templates
admin_templates = ['dashboard.html', 'institutions.html', 'users.html', 'approval_queue.html', 'analytics.html', 'departments.html', 'roles.html', 'settings.html', 'audit_log.html']
for t in admin_templates:
    files[os.path.join(templates_dir, 'admin', t)] = f'''{{% extends "base.html" %}}
{{% block sidebar %}}
<ul>
    <li><a href="#">Admin Dashboard</a></li>
    <li><a href="#">Manage Users</a></li>
</ul>
{{% endblock %}}
{{% block content %}}
<div class="glass-panel">
    <h1>Admin: {t.replace('.html', '').capitalize()}</h1>
    <p>Welcome to the admin interface.</p>
</div>
{{% endblock %}}'''

# Faculty Templates
faculty_templates = ['dashboard.html', 'upload.html', 'my_uploads.html', 'approvals.html', 'subjects.html', 'analytics.html']
for t in faculty_templates:
    files[os.path.join(templates_dir, 'faculty', t)] = f'''{{% extends "base.html" %}}
{{% block sidebar %}}
<ul>
    <li><a href="#">Faculty Dashboard</a></li>
    <li><a href="#">My Uploads</a></li>
</ul>
{{% endblock %}}
{{% block content %}}
<div class="glass-panel">
    <h1>Faculty: {t.replace('.html', '').capitalize()}</h1>
    <p>Welcome to the faculty interface.</p>
</div>
{{% endblock %}}'''

# Student Templates
student_templates = ['dashboard.html', 'library.html', 'detail.html', 'ai_chat.html', 'quiz.html', 'flashcards.html', 'search.html', 'bookmarks.html', 'leaderboard.html', 'profile.html', 'notifications.html', 'qr.html']
for t in student_templates:
    files[os.path.join(templates_dir, 'student', t)] = f'''{{% extends "base.html" %}}
{{% block sidebar %}}
<ul>
    <li><a href="#">Student Dashboard</a></li>
    <li><a href="#">Library</a></li>
</ul>
{{% endblock %}}
{{% block content %}}
<div class="glass-panel">
    <h1>Student: {t.replace('.html', '').capitalize()}</h1>
    <p>Welcome to the student interface.</p>
</div>
{{% endblock %}}'''

# Auth Templates
auth_templates = ['login.html', 'register.html']
for t in auth_templates:
    files[os.path.join(templates_dir, 'auth', t)] = f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <title>CampusX Auth</title>
    <link href="/static/css/design-system.css" rel="stylesheet">
    <link href="/static/css/components.css" rel="stylesheet">
</head>
<body style="display: flex; justify-content: center; align-items: center; height: 100vh;">
    <div class="glass-panel" style="width: 400px; text-align: center;">
        <h1>{t.replace('.html', '').capitalize()}</h1>
        <form>
            <input type="text" placeholder="Username" class="mb-4 p-4" style="width: 100%; border-radius: 8px; border: 1px solid #ccc;"><br>
            <input type="password" placeholder="Password" class="mb-4 p-4" style="width: 100%; border-radius: 8px; border: 1px solid #ccc;"><br>
            <button class="btn-primary" style="width: 100%;">Submit</button>
        </form>
    </div>
</body>
</html>'''


for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Generated {len(files)} files successfully.")

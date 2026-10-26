import os
import re
import html
import base64
import zipfile
import xml.etree.ElementTree as ET


class DocumentViewerService:
    @staticmethod
    def is_viewable_format(filename: str) -> bool:
        ext = (filename or '').rsplit('.', 1)[-1].lower()
        return ext in {'pdf', 'pptx', 'ppt', 'docx', 'doc', 'txt', 'md', 'csv', 'png', 'jpg', 'jpeg', 'webp', 'svg'}

    @classmethod
    def render_to_html(cls, abs_path: str, filename: str, mime_type: str, title: str = None, download_url: str = None) -> str:
        ext = (filename or '').rsplit('.', 1)[-1].lower()
        doc_title = title or filename or 'Document Viewer'
        dl_url = download_url or '#'

        if ext in {'pptx', 'ppt'}:
            body_content = cls._render_pptx_slides(abs_path)
            format_badge = 'PowerPoint Presentation'
            extra_js = cls._get_pptx_js()
        elif ext in {'docx', 'doc'}:
            body_content = cls._render_docx_document(abs_path)
            format_badge = 'Word Document'
            extra_js = ''
        elif ext in {'txt', 'md', 'csv'}:
            body_content = cls._render_text_file(abs_path, ext)
            format_badge = ext.upper() + ' Document'
            extra_js = ''
        elif ext in {'png', 'jpg', 'jpeg', 'webp', 'svg', 'gif'}:
            body_content = cls._render_image_file(abs_path, ext)
            format_badge = 'Image File'
            extra_js = ''
        else:
            body_content = f'<div style="text-align:center;padding:48px 20px;"><p style="font-size:16px;color:#64748B;">This file format cannot be rendered inline.</p><a href="{dl_url}" class="btn-dl">Download File</a></div>'
            format_badge = ext.upper()
            extra_js = ''

        return cls._build_viewer_page(
            title=doc_title,
            filename=filename,
            format_badge=format_badge,
            download_url=dl_url,
            body_content=body_content,
            extra_js=extra_js
        )

    @classmethod
    def _render_pptx_slides(cls, abs_path: str) -> str:
        try:
            slides = []
            with zipfile.ZipFile(abs_path) as z:
                # 1. Extract media images
                images = {}
                for name in z.namelist():
                    if name.startswith('ppt/media/'):
                        data = z.read(name)
                        b64 = base64.b64encode(data).decode('utf-8')
                        ext = name.split('.')[-1].lower()
                        mime = 'image/png' if ext == 'png' else 'image/jpeg'
                        images[name.split('/')[-1]] = f'data:{mime};base64,{b64}'

                # 2. Extract slides in order
                slide_files = [n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                slide_files.sort(key=lambda s: int(re.search(r'\d+', s).group(0)) if re.search(r'\d+', s) else 0)

                for i, s_file in enumerate(slide_files, start=1):
                    tree = ET.fromstring(z.read(s_file))
                    texts = []
                    for t in tree.iter():
                        if t.tag.endswith('}t') and t.text and t.text.strip():
                            texts.append(t.text.strip())

                    # Find relationships
                    rel_file = s_file.replace('ppt/slides/', 'ppt/slides/_rels/') + '.rels'
                    slide_imgs = []
                    if rel_file in z.namelist():
                        rel_tree = ET.fromstring(z.read(rel_file))
                        for rel in rel_tree.iter():
                            target = rel.attrib.get('Target', '')
                            if 'media/' in target:
                                img_key = target.split('/')[-1]
                                if img_key in images:
                                    slide_imgs.append(images[img_key])

                    if not slide_imgs and images and i <= len(images):
                        slide_imgs.append(list(images.values())[i - 1])

                    slides.append({
                        'number': i,
                        'title': texts[0] if texts else f'Slide {i}',
                        'subtitle': texts[1] if len(texts) > 1 else '',
                        'texts': texts[2:] if len(texts) > 2 else [],
                        'images': slide_imgs
                    })

            if not slides:
                return '<div style="text-align:center;padding:40px;color:#64748B;">No slides found in presentation.</div>'

            # Build Carousel HTML
            slides_html = []
            for s in slides:
                active_cls = 'active-slide' if s['number'] == 1 else ''
                img_html = ''
                if s['images']:
                    for img in s['images']:
                        img_html += f'<div style="text-align:center;margin:16px 0;"><img src="{img}" style="max-height:360px;max-width:100%;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.08);border:1px solid #E2E8F0;" /></div>'

                texts_html = ''
                if s['texts']:
                    texts_html += '<ul style="margin:16px 0;padding-left:24px;font-size:15px;line-height:1.7;color:#334155;">'
                    for txt in s['texts']:
                        texts_html += f'<li style="margin-bottom:8px;">{html.escape(txt)}</li>'
                    texts_html += '</ul>'

                slides_html.append(f"""
                <div class="slide-card {active_cls}" id="slide-{s['number']}">
                  <div class="slide-header">
                    <span class="slide-pill">SLIDE {s['number']} of {len(slides)}</span>
                  </div>
                  <h2 class="slide-title">{html.escape(s['title'])}</h2>
                  {f'<h3 class="slide-sub">{html.escape(s["subtitle"])}</h3>' if s['subtitle'] else ''}
                  {img_html}
                  {texts_html}
                </div>
                """)

            total = len(slides)
            return f"""
            <div class="presentation-wrapper">
              <div class="presentation-controls">
                <button type="button" class="ctrl-btn" onclick="prevSlide()" id="prev-btn">
                  &larr; Previous Slide
                </button>
                <div class="slide-indicator">
                  Slide <span id="current-slide-num">1</span> of <span id="total-slides-num">{total}</span>
                </div>
                <button type="button" class="ctrl-btn" onclick="nextSlide()" id="next-btn">
                  Next Slide &rarr;
                </button>
              </div>
              <div class="slides-viewport">
                {''.join(slides_html)}
              </div>
            </div>
            """
        except Exception as e:
            return f'<div style="padding:32px;text-align:center;color:#DC2626;">Error parsing presentation: {html.escape(str(e))}</div>'

    @classmethod
    def _render_docx_document(cls, abs_path: str) -> str:
        try:
            html_parts = []
            with zipfile.ZipFile(abs_path) as z:
                # Extract images
                images = {}
                for name in z.namelist():
                    if name.startswith('word/media/'):
                        data = z.read(name)
                        b64 = base64.b64encode(data).decode('utf-8')
                        ext = name.split('.')[-1].lower()
                        mime = 'image/png' if ext == 'png' else 'image/jpeg'
                        images[name.split('/')[-1]] = f'data:{mime};base64,{b64}'

                # Extract document body text
                if 'word/document.xml' in z.namelist():
                    tree = ET.fromstring(z.read('word/document.xml'))
                    for p in tree.iter():
                        if p.tag.endswith('}p'):
                            texts = [t.text for t in p.iter() if t.tag.endswith('}t') and t.text]
                            if texts:
                                line = ' '.join(texts).strip()
                                if line:
                                    html_parts.append(f'<p style="margin-bottom:14px;line-height:1.7;font-size:15px;color:#1E293B;">{html.escape(line)}</p>')

                # Add embedded images
                for img_name, img_url in images.items():
                    html_parts.append(f'<div style="text-align:center;margin:28px 0;"><img src="{img_url}" style="max-width:100%;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.08);border:1px solid #E2E8F0;" alt="Embedded Document Image" /></div>')

            if not html_parts:
                return '<div style="padding:40px;text-align:center;color:#64748B;">Document contains no displayable text or diagrams.</div>'

            return f"""
            <div class="docx-paper">
              {''.join(html_parts)}
            </div>
            """
        except Exception as e:
            return f'<div style="padding:32px;text-align:center;color:#DC2626;">Error parsing Word document: {html.escape(str(e))}</div>'

    @classmethod
    def _render_text_file(cls, abs_path: str, ext: str) -> str:
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return f"""
            <div class="text-paper">
              <pre style="margin:0;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:#1E293B;">{html.escape(content)}</pre>
            </div>
            """
        except Exception as e:
            return f'<div style="padding:32px;text-align:center;color:#DC2626;">Error loading text file: {html.escape(str(e))}</div>'

    @classmethod
    def _render_image_file(cls, abs_path: str, ext: str) -> str:
        try:
            with open(abs_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            mime = 'image/svg+xml' if ext == 'svg' else f'image/{ext}'
            return f"""
            <div style="text-align:center;padding:32px 16px;">
              <img src="data:{mime};base64,{b64}" style="max-width:100%;max-height:85vh;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.1);border:1px solid #E2E8F0;" />
            </div>
            """
        except Exception as e:
            return f'<div style="padding:32px;text-align:center;color:#DC2626;">Error loading image: {html.escape(str(e))}</div>'

    @classmethod
    def _build_viewer_page(cls, title: str, filename: str, format_badge: str, download_url: str, body_content: str, extra_js: str = '') -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} — CampusX Online Reader</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #F8FAFC;
      color: #0F172A;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}
    .viewer-topbar {{
      height: 56px;
      background: #FFFFFF;
      border-bottom: 1px solid #E2E8F0;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      z-index: 10;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
      flex-shrink: 0;
    }}
    .viewer-title-group {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }}
    .viewer-badge {{
      background: #EBF4EE;
      color: #1E5034;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      white-space: nowrap;
    }}
    .viewer-title {{
      font-size: 15px;
      font-weight: 700;
      color: #0F172A;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin: 0;
    }}
    .viewer-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }}
    .btn-action {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
    }}
    .btn-action-primary {{
      background: #1E5034;
      color: #FFFFFF;
    }}
    .btn-action-primary:hover {{
      background: #163B26;
    }}
    .btn-action-secondary {{
      background: #F1F5F9;
      color: #334155;
      border-color: #E2E8F0;
    }}
    .btn-action-secondary:hover {{
      background: #E2E8F0;
    }}
    .viewer-content-area {{
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
    }}
    .docx-paper {{
      width: 100%;
      max-width: 860px;
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 48px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.04);
      margin: 0 auto;
    }}
    .text-paper {{
      width: 100%;
      max-width: 900px;
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.03);
      margin: 0 auto;
    }}
    .presentation-wrapper {{
      width: 100%;
      max-width: 960px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      align-items: center;
    }}
    .presentation-controls {{
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      padding: 10px 18px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }}
    .ctrl-btn {{
      background: #F1F5F9;
      color: #0F172A;
      border: 1px solid #CBD5E1;
      padding: 7px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }}
    .ctrl-btn:hover {{
      background: #E2E8F0;
    }}
    .ctrl-btn:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}
    .slide-indicator {{
      font-size: 13.5px;
      font-weight: 700;
      color: #475569;
    }}
    .slides-viewport {{
      width: 100%;
    }}
    .slide-card {{
      display: none;
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 40px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.04);
      min-height: 480px;
    }}
    .slide-card.active-slide {{
      display: block;
    }}
    .slide-pill {{
      background: #EEF2FF;
      color: #3730A3;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
    }}
    .slide-title {{
      font-size: 26px;
      font-weight: 800;
      color: #0F172A;
      margin: 14px 0 6px 0;
      line-height: 1.25;
    }}
    .slide-sub {{
      font-size: 17px;
      font-weight: 600;
      color: #1E5034;
      margin: 0 0 20px 0;
    }}
  </style>
</head>
<body>
  <div class="viewer-topbar">
    <div class="viewer-title-group">
      <span class="viewer-badge">{format_badge}</span>
      <h1 class="viewer-title">{html.escape(title)}</h1>
    </div>
    <div class="viewer-actions">
      <a href="{download_url}" class="btn-action btn-action-primary" download>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Download File
      </a>
      <button onclick="window.close()" class="btn-action btn-action-secondary">Close</button>
    </div>
  </div>

  <div class="viewer-content-area">
    {body_content}
  </div>

  {extra_js}
</body>
</html>"""

    @classmethod
    def _get_pptx_js(cls) -> str:
        return """
  <script>
    let currentSlide = 1;
    const slides = document.querySelectorAll('.slide-card');
    const totalSlides = slides.length;

    function showSlide(n) {
      if (n < 1) n = 1;
      if (n > totalSlides) n = totalSlides;
      currentSlide = n;

      slides.forEach(s => s.classList.remove('active-slide'));
      const active = document.getElementById('slide-' + n);
      if (active) active.classList.add('active-slide');

      const numEl = document.getElementById('current-slide-num');
      if (numEl) numEl.textContent = n;

      const prevBtn = document.getElementById('prev-btn');
      const nextBtn = document.getElementById('next-btn');
      if (prevBtn) prevBtn.disabled = (n === 1);
      if (nextBtn) nextBtn.disabled = (n === totalSlides);
    }

    function prevSlide() { showSlide(currentSlide - 1); }
    function nextSlide() { showSlide(currentSlide + 1); }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
        nextSlide();
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        prevSlide();
      }
    });

    document.addEventListener('DOMContentLoaded', () => { showSlide(1); });
  </script>
        """

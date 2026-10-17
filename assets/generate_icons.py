#!/usr/bin/env python3
"""
Generate high-resolution vector and PNG icons for Nobara Jarvis AI Assistant.
"""
import os
import sys

from PySide6.QtGui import QIcon, QPixmap, QPainter, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, QSize, Qt

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

SVG_CONTENT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#141822"/>
      <stop offset="50%" stop-color="#0e1118"/>
      <stop offset="100%" stop-color="#08090d"/>
    </linearGradient>

    <!-- Cyan Arc Glow Gradient -->
    <linearGradient id="cyanGlow" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f7ff"/>
      <stop offset="50%" stop-color="#00aaff"/>
      <stop offset="100%" stop-color="#0055ff"/>
    </linearGradient>

    <!-- Outer Ring Gradient -->
    <linearGradient id="metalRing" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3a4454"/>
      <stop offset="50%" stop-color="#1e2430"/>
      <stop offset="100%" stop-color="#121620"/>
    </linearGradient>

    <!-- Core Radial Glow -->
    <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#00f7ff" stop-opacity="0.8"/>
      <stop offset="40%" stop-color="#00aaff" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#0055ff" stop-opacity="0"/>
    </radialGradient>

    <filter id="neonBlur" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- Base Circle -->
  <circle cx="256" cy="256" r="240" fill="url(#bgGrad)" stroke="url(#metalRing)" stroke-width="12"/>

  <!-- Radial Core Glow -->
  <circle cx="256" cy="256" r="180" fill="url(#coreGlow)"/>

  <!-- Outer Tech Ring (Dashed Arc) -->
  <circle cx="256" cy="256" r="215" fill="none" stroke="#00f7ff" stroke-width="3" stroke-opacity="0.35" stroke-dasharray="24 16"/>

  <!-- Arc Reactor Segmented Ring -->
  <circle cx="256" cy="256" r="175" fill="none" stroke="url(#cyanGlow)" stroke-width="14" filter="url(#neonBlur)" stroke-dasharray="88 24"/>

  <!-- Inner Cyan Ring -->
  <circle cx="256" cy="256" r="130" fill="none" stroke="#00f7ff" stroke-width="4" stroke-opacity="0.6"/>

  <!-- Radial Nodes (8 Dots) -->
  <g fill="#00f7ff" filter="url(#neonBlur)">
    <circle cx="256" cy="110" r="7"/>
    <circle cx="359" cy="153" r="7"/>
    <circle cx="402" cy="256" r="7"/>
    <circle cx="359" cy="359" r="7"/>
    <circle cx="256" cy="402" r="7"/>
    <circle cx="153" cy="359" r="7"/>
    <circle cx="110" cy="256" r="7"/>
    <circle cx="153" cy="153" r="7"/>
  </g>

  <!-- Futuristic Holographic Microphone / AI Core in Center -->
  <g filter="url(#neonBlur)">
    <!-- Capsule Body -->
    <rect x="226" y="170" width="60" height="100" rx="30" fill="url(#cyanGlow)" stroke="#ffffff" stroke-width="4" stroke-opacity="0.9"/>
    
    <!-- Sound Waves / Arc around Capsule -->
    <path d="M 196 230 C 196 280, 316 280, 316 230" fill="none" stroke="#ffffff" stroke-width="8" stroke-linecap="round"/>
    
    <!-- Stem and Stand Base -->
    <line x1="256" y1="280" x2="256" y2="330" stroke="#00f7ff" stroke-width="8" stroke-linecap="round"/>
    <line x1="216" y1="330" x2="296" y2="330" stroke="#00f7ff" stroke-width="8" stroke-linecap="round"/>

    <!-- Futuristic Inner Core Line -->
    <line x1="242" y1="205" x2="270" y2="205" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
    <line x1="238" y1="220" x2="274" y2="220" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
    <line x1="242" y1="235" x2="270" y2="235" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
  </g>

  <!-- Soundwave accents on the sides -->
  <g stroke="#00f7ff" stroke-width="4" stroke-linecap="round" stroke-opacity="0.8" filter="url(#neonBlur)">
    <line x1="160" y1="235" x2="160" y2="277"/>
    <line x1="140" y1="245" x2="140" y2="267"/>
    <line x1="352" y1="235" x2="352" y2="277"/>
    <line x1="372" y1="245" x2="372" y2="267"/>
  </g>
</svg>'''

def main():
    svg_path = os.path.join(ASSETS_DIR, "nobara-jarvis.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(SVG_CONTENT)
    print(f"Written: {svg_path}")

    # Render PNGs using PySide6
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    renderer = QSvgRenderer(QByteArray(SVG_CONTENT.encode("utf-8")))

    sizes = [256, 128, 64, 48]
    for sz in sizes:
        img = QImage(sz, sz, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()

        png_path = os.path.join(ASSETS_DIR, f"nobara-jarvis-{sz}.png")
        img.save(png_path)
        print(f"Rendered: {png_path}")

    # Also save master nobara-jarvis.png (256x256)
    master_png = os.path.join(ASSETS_DIR, "nobara-jarvis.png")
    img = QImage(256, 256, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    img.save(master_png)
    print(f"Rendered: {master_png}")

if __name__ == "__main__":
    main()

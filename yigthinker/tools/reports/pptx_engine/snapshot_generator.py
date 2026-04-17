"""
skill-pptx — Snapshot Generator

Renders slides as PNG images using LibreOffice headless.
Falls back to a placeholder image if LibreOffice is not available.

Note: LibreOffice rendering may differ from PowerPoint. Images are
labeled as "preview" only — final appearance is in PowerPoint.
"""

import os
import subprocess
import shutil
import tempfile
from pathlib import Path


def _find_libreoffice() -> str | None:
    """Find LibreOffice executable on the system."""
    candidates = [
        "libreoffice",
        "soffice",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/opt/libreoffice/program/soffice",
        "C:/Program Files/LibreOffice/program/soffice.exe",
        "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
    ]
    for candidate in candidates:
        if shutil.which(candidate) or os.path.exists(candidate):
            return candidate
    return None


def _generate_with_libreoffice(
    file_path: str,
    output_dir: str,
    dpi: int = 150,
) -> list[str]:
    """
    Generate PNG snapshots using LibreOffice headless.

    Returns list of generated PNG file paths.
    """
    lo_path = _find_libreoffice()
    if not lo_path:
        raise RuntimeError(
            "LibreOffice is not installed. Install libreoffice-impress to generate snapshots."
        )

    # LibreOffice exports all slides to the output dir as PNG
    cmd = [
        lo_path,
        "--headless",
        "--convert-to", f"png:impress_png_Export:PixelWidth={int(dpi * 10)},PixelHeight={int(dpi * 7.5)}",
        "--outdir", output_dir,
        file_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice export failed (code {result.returncode}): {result.stderr}"
        )

    # Find generated PNG files
    base_name = Path(file_path).stem
    generated = sorted(
        str(p) for p in Path(output_dir).glob(f"{base_name}*.png")
    )

    return generated


def _generate_placeholder_png(output_dir: str, slide_count: int) -> list[str]:
    """
    Generate placeholder PNG files when LibreOffice is unavailable.
    Uses Pillow to create simple labeled placeholder images.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        paths = []
        for i in range(slide_count):
            img = Image.new("RGB", (1280, 720), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)
            # Draw slide frame
            draw.rectangle([40, 40, 1240, 680], outline=(200, 200, 200), width=2)
            # Draw label
            draw.text(
                (640, 360),
                f"Slide {i + 1}\n(Preview unavailable — LibreOffice not installed)",
                fill=(128, 128, 128),
                anchor="mm",
            )
            output_path = os.path.join(output_dir, f"slide_{i + 1:03d}.png")
            img.save(output_path, "PNG")
            paths.append(output_path)
        return paths
    except ImportError:
        return []


def generate_snapshots(
    file_path: str,
    output_dir: str,
    dpi: int = 150,
    slide_indices: list | None = None,
) -> dict:
    """
    Render slides as PNG thumbnail images.

    Args:
        file_path: Path to the .pptx file
        output_dir: Directory for PNG output files
        dpi: Resolution (default: 150)
        slide_indices: Optional list of specific slides to render

    Returns:
        dict with list of generated image paths
    """
    os.makedirs(output_dir, exist_ok=True)

    # Try LibreOffice first
    lo_available = _find_libreoffice() is not None

    if lo_available:
        try:
            all_paths = _generate_with_libreoffice(file_path, output_dir, dpi)

            # Filter to requested indices if specified
            if slide_indices is not None:
                filtered = []
                for i, path in enumerate(all_paths):
                    if i in slide_indices:
                        filtered.append(path)
                result_paths = filtered
            else:
                result_paths = all_paths

            return {
                "success": True,
                "snapshots": result_paths,
                "count": len(result_paths),
                "renderer": "libreoffice",
                "note": "Preview rendered by LibreOffice. Final appearance may differ in PowerPoint.",
            }
        except Exception as e:
            # Fall through to placeholder
            pass

    # Fallback: Pillow placeholder
    from pptx import Presentation
    prs = Presentation(file_path)
    slide_count = len(prs.slides)
    if slide_indices:
        count = len(slide_indices)
    else:
        count = slide_count

    placeholder_paths = _generate_placeholder_png(output_dir, count)

    return {
        "success": True if placeholder_paths else False,
        "snapshots": placeholder_paths,
        "count": len(placeholder_paths),
        "renderer": "placeholder",
        "note": "LibreOffice not available. Install libreoffice-impress for real slide previews.",
    }


def export_file(file_path: str, format: str, output_path: str) -> dict:
    """
    Export presentation to specified format.

    Args:
        file_path: Source .pptx path
        format: "pptx" or "pdf"
        output_path: Output file path

    Returns:
        dict with operation result
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if format == "pptx":
        # Simple copy / passthrough
        shutil.copy2(file_path, output_path)
        file_size = os.path.getsize(output_path)
        return {
            "success": True,
            "output_path": output_path,
            "format": "pptx",
            "file_size_bytes": file_size,
        }

    elif format == "pdf":
        lo_path = _find_libreoffice()
        if not lo_path:
            raise RuntimeError(
                "LibreOffice is required for PDF export. Install libreoffice-impress."
            )

        output_dir = os.path.dirname(os.path.abspath(output_path))
        cmd = [
            lo_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            file_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(
                f"PDF export failed (code {result.returncode}): {result.stderr}"
            )

        # LibreOffice outputs <stem>.pdf in output_dir
        base_name = Path(file_path).stem
        generated_pdf = os.path.join(output_dir, f"{base_name}.pdf")

        # Rename if needed
        if generated_pdf != output_path and os.path.exists(generated_pdf):
            shutil.move(generated_pdf, output_path)

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return {
            "success": True,
            "output_path": output_path,
            "format": "pdf",
            "file_size_bytes": file_size,
        }

    else:
        raise ValueError(f"Unsupported format: {format}. Use 'pptx' or 'pdf'.")

import io
import logging
import os
import re
import shutil
import sys
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# Reduce noisy pdfminer logs (common on some PDFs with invalid pattern colors)
logging.getLogger('pdfminer').setLevel(logging.ERROR)
logging.getLogger('pdfminer.pdfinterp').setLevel(logging.ERROR)

class PdfExtractor:
    """
    Extract text from PDF bytes using a combination of methods:
    1. pdfplumber (best for layout)
    2. pypdf (fallback)
    3. OCR (Tesseract) if text extraction yields poor results (scans)
    """

    def __init__(self):
        self._configure_ocr_tools()

    def _configure_ocr_tools(self):
        """Configure paths for Tesseract and Poppler on Windows."""
        if not sys.platform.startswith('win'):
            return

        # 1. Tesseract Configuration
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            os.path.expanduser(r'~\AppData\Local\Tesseract-OCR\tesseract.exe')
        ]
        
        # Check if tesseract is already in PATH or configured
        try:
            import pytesseract
            # Only set if not already found/set
            if not shutil.which("tesseract"):
                for path in tesseract_paths:
                    if os.path.exists(path):
                        pytesseract.pytesseract.tesseract_cmd = path
                        logger.debug(f"Tesseract configured at: {path}")
                        break
        except ImportError:
            pass

        # 2. Poppler Configuration
        self.poppler_path = None
        if not shutil.which("pdftoppm"):
            possible_poppler_paths = [
                r"C:\poppler\Library\bin",
                r"C:\Program Files\poppler-24.02.0\Library\bin",
                r"C:\Program Files\poppler-0.68.0\bin",
                r"C:\poppler\bin",
                r"C:\Tools\poppler\bin"
            ]
            for path in possible_poppler_paths:
                if os.path.exists(path):
                    self.poppler_path = path
                    logger.debug(f"Poppler configured at: {path}")
                    break

    def extract(self, pdf_bytes: bytes, filename: str = None) -> str:
        """
        Main entry point to extract text from PDF bytes.
        """
        if not pdf_bytes:
            return ""

        # Basic sanity check: signature
        if not pdf_bytes.startswith(b'%PDF-'):
            head = pdf_bytes[:32]
            logger.warning(f"Input does not look like a PDF for {filename or 'PDF'} (head={head!r}).")
            return ""

        # 1. Standard extraction
        text_std = self._extract_with_plumber(pdf_bytes)
        
        # If plumber failed or returned empty, try pypdf
        if not text_std:
            text_std = self._extract_with_pypdf(pdf_bytes)

        # 2. Check quality (count alphanumeric characters)
        # This avoids being fooled by long strings of bullet points or whitespace
        std_alnum_count = sum(c.isalnum() for c in text_std)
        
        # Threshold: if we have less than 150 real chars, it's suspicious.
        # (A typical page has > 500 chars. A short letter might have 200-300).
        if std_alnum_count < 150:
            logger.info(f"Standard extraction yielded low quality text ({std_alnum_count} alnum chars) for {filename or 'PDF'}. Attempting OCR...")
            
            text_ocr = self._extract_with_ocr(pdf_bytes)
            ocr_alnum_count = sum(c.isalnum() for c in text_ocr)
            
            # Compare and return the best one
            if ocr_alnum_count > std_alnum_count:
                logger.info(f"OCR result better ({ocr_alnum_count} > {std_alnum_count} chars). Using OCR.")
                return text_ocr
            else:
                logger.info(f"OCR result not better ({ocr_alnum_count} <= {std_alnum_count}). Keeping standard text.")
                return text_std
        
        return text_std

    def _extract_with_plumber(self, pdf_bytes: bytes) -> str:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text_parts = []
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_parts.append(extracted)
                return "\n\n".join(text_parts).strip()
        except ImportError:
            logger.warning("pdfplumber not installed.")
            return ""
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
            return ""

    def _extract_with_pypdf(self, pdf_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            
            full_text = "\n".join(text_parts)
            # Clean up excessive newlines
            return re.sub(r'\n\s*\n', '\n\n', full_text).strip()
        except Exception as e:
            logger.warning(f"pypdf extraction failed: {e}")
            return ""

    def _extract_with_ocr(self, pdf_bytes: bytes) -> str:
        try:
            from pdf2image import convert_from_bytes
            import pytesseract
            
            # Convert PDF to images
            # Pass poppler_path if we found it and it's not in PATH
            kwargs = {}
            if self.poppler_path:
                kwargs["poppler_path"] = self.poppler_path

            images = convert_from_bytes(pdf_bytes, **kwargs)
            
            ocr_text = []
            for i, img in enumerate(images):
                # Assume French text
                text = pytesseract.image_to_string(img, lang='fra')
                ocr_text.append(text)
            
            return "\n".join(ocr_text)
            
        except ImportError:
            logger.error("OCR dependencies missing. Install `pdf2image`, `pytesseract`.")
            return ""
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""

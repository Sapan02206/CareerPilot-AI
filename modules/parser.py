try:
    import pypdf as _pdf_lib
    _PYPDF_ATTR = "pypdf"
except ImportError:
    import PyPDF2 as _pdf_lib   # type: ignore[no-redef]
    _PYPDF_ATTR = "PyPDF2"
import docx
import re
from typing import Optional

class ResumeParser:
    """Extract and clean text from resume documents"""
    
    @staticmethod
    def extract_text(file_path: str) -> Optional[str]:
        """
        Extract text from PDF or DOCX file
        
        Args:
            file_path: Path to the resume file
            
        Returns:
            Extracted text or None if extraction fails
        """
        try:
            if file_path.lower().endswith('.pdf'):
                return ResumeParser._extract_from_pdf(file_path)
            elif file_path.lower().endswith('.docx'):
                return ResumeParser._extract_from_docx(file_path)
            else:
                raise ValueError("Unsupported file format")
        except Exception as e:
            print(f"Error extracting text: {e}")
            return None
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Extract text from PDF file using pypdf (with PyPDF2 fallback)."""
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = _pdf_lib.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    @staticmethod
    def _extract_from_docx(file_path: str) -> str:
        """Extract text from DOCX file"""
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    
    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean and normalize extracted text
        
        Args:
            text: Raw extracted text
            
        Returns:
            Cleaned text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep alphanumeric, common punctuation,
        # and @ (required for email address detection by ATS scorer)
        text = re.sub(r'[^\w\s\.\,\-\+\#\/\@]', '', text)
        
        # Normalize line breaks
        text = text.replace('\n', ' ')
        
        return text.strip()
    
    @staticmethod
    def extract_sections(text: str) -> dict:
        """
        Extract common resume sections (optional enhancement)
        
        Args:
            text: Cleaned resume text
            
        Returns:
            Dictionary with section names and content
        """
        sections = {}
        
        # Common section headers
        section_patterns = {
            'education': r'education|academic|qualification',
            'experience': r'experience|employment|work history',
            'skills': r'skills|technical skills|competencies',
            'projects': r'projects|portfolio',
            'certifications': r'certifications|certificates|licenses'
        }
        
        text_lower = text.lower()
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, text_lower)
            if match:
                sections[section_name] = True
        
        return sections

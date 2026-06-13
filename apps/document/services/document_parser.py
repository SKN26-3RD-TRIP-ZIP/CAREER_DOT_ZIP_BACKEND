from io import BytesIO

_PARSERS = {
    'txt': lambda f: _extract_txt(f),
    'pdf': lambda f: _extract_pdf(f),
    'docx': lambda f: _extract_docx(f),
}


def extract_text_from_document(uploaded_document):
    try:
        parser = _PARSERS[uploaded_document.file_type]
    except KeyError as exc:
        raise ValueError(f'Unsupported file type: {uploaded_document.file_type}') from exc

    uploaded_document.file.open('rb')
    try:
        return parser(uploaded_document.file)
    finally:
        uploaded_document.file.close()


def extract_text_from_file(file_obj, file_type):
    """
    업로드 파일 객체(Django UploadedFile 등)에서 텍스트를 추출한다.
    document 앱 외부(JD/이력서 업로드)에서 파서를 재사용하기 위한 함수.
    file_type: 'pdf' | 'docx' | 'txt'
    """
    try:
        parser = _PARSERS[file_type]
    except KeyError as exc:
        raise ValueError(f'Unsupported file type: {file_type}') from exc

    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass
    return parser(file_obj)


def _extract_txt(file_obj):
    return file_obj.read().decode('utf-8')


def _extract_pdf(file_obj):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError('PyMuPDF is required to parse PDF files.') from exc

    with fitz.open(stream=file_obj.read(), filetype='pdf') as document:
        return '\n'.join(page.get_text() for page in document)


def _extract_docx(file_obj):
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError('python-docx is required to parse DOCX files.') from exc

    document = Document(BytesIO(file_obj.read()))
    return '\n'.join(paragraph.text for paragraph in document.paragraphs)

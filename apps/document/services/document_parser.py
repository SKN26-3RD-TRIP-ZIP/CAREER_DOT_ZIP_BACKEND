from io import BytesIO


def extract_text_from_document(uploaded_document):
    parsers = {
        'txt': _extract_txt,
        'pdf': _extract_pdf,
        'docx': _extract_docx,
    }
    try:
        parser = parsers[uploaded_document.file_type]
    except KeyError as exc:
        raise ValueError(f'Unsupported file type: {uploaded_document.file_type}') from exc

    uploaded_document.file.open('rb')
    try:
        return parser(uploaded_document.file)
    finally:
        uploaded_document.file.close()


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

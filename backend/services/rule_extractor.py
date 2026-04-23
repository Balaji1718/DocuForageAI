"""
Universal DOCX Rule Extractor
Extracts formatting rules from any DOCX file - domain agnostic
Returns 52-key universal schema covering any document type
"""

from __future__ import annotations
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Optional
import re


EXTRACTION_FALLBACKS: dict[str, Any] = {
    "body_font": "Times New Roman",
    "body_size_halfpt": 24,
    "body_alignment": "both",
    "body_line_spacing_val": 360,
    "body_line_spacing_rule": "auto",
    "body_space_before": 0,
    "body_space_after": 120,
    "body_first_line_indent_dxa": 0,
    "body_is_bold": False,
    "body_is_italic": False,
    "body_is_underline": False,
    "h1_font": "Calibri",
    "h1_size_halfpt": 36,
    "h1_alignment": "left",
    "h1_is_bold": True,
    "h1_is_italic": False,
    "h1_is_underline": False,
    "h1_space_before": 240,
    "h1_space_after": 120,
    "h2_font": "Calibri",
    "h2_size_halfpt": 32,
    "h2_alignment": "left",
    "h2_is_bold": True,
    "h2_is_italic": False,
    "h2_is_underline": False,
    "h2_space_before": 200,
    "h2_space_after": 100,
    "h3_font": "Calibri",
    "h3_size_halfpt": 28,
    "h3_alignment": "left",
    "h3_is_bold": True,
    "h3_is_italic": False,
    "h3_is_underline": False,
    "h3_space_before": 160,
    "h3_space_after": 80,
    "h4_font": "Calibri",
    "h4_size_halfpt": 26,
    "h4_alignment": "left",
    "h4_is_bold": True,
    "h4_is_italic": False,
    "h4_is_underline": False,
    "h5_font": "Calibri",
    "h5_size_halfpt": 24,
    "h5_alignment": "left",
    "h5_is_bold": True,
    "h5_is_italic": False,
    "h6_font": "Calibri",
    "h6_size_halfpt": 22,
    "h6_alignment": "left",
    "h6_is_bold": True,
    "h6_is_italic": False,
    "has_page_numbers": False,
    "page_number_format": "decimal",
    "page_number_alignment": "center",
    "element_count_tables": 0,
    "element_count_images": 0,
    "element_count_lists": 0,
    "element_count_paragraphs": 0,
    "flag_markdown_leak": False,
    "flag_artifact_numbers": False,
    "flag_mixed_fonts": False,
    "flag_inconsistent_spacing": False,
}

# ============================================================================
# 52-KEY UNIVERSAL SCHEMA (Domain Agnostic)
# ============================================================================
NEUTRAL_DEFAULTS = {
    # PAGE SETTINGS
    "page_width_dxa": 11906,          # A4: 8.27" in twips (1/20th point)
    "page_height_dxa": 16838,         # A4: 11.69" in twips
    "margin_top_dxa": 1440,           # 1.0" in twips
    "margin_bottom_dxa": 1440,        # 1.0" in twips
    "margin_left_dxa": 1800,          # 1.25" in twips
    "margin_right_dxa": 1800,         # 1.25" in twips
    "margin_header_dxa": 720,         # 0.5" in twips
    "margin_footer_dxa": 720,         # 0.5" in twips

    # BODY TEXT FORMATTING
    "body_font": None,
    "body_size_halfpt": None,         # Font size in half-points (24 = 12pt)
    "body_alignment": None,            # left, center, right, both (justified)
    "body_line_spacing_val": None,    # 240 = single, 360 = 1.5x, 480 = double
    "body_line_spacing_rule": None,   # auto, atLeast, exact
    "body_space_before": None,
    "body_space_after": None,
    "body_first_line_indent_dxa": None,
    "body_is_bold": None,
    "body_is_italic": None,
    "body_is_underline": None,

    # HEADING 1
    "h1_font": None,
    "h1_size_halfpt": None,
    "h1_alignment": None,
    "h1_is_bold": None,
    "h1_is_italic": None,
    "h1_is_underline": None,
    "h1_space_before": None,
    "h1_space_after": None,

    # HEADING 2
    "h2_font": None,
    "h2_size_halfpt": None,
    "h2_alignment": None,
    "h2_is_bold": None,
    "h2_is_italic": None,
    "h2_is_underline": None,
    "h2_space_before": None,
    "h2_space_after": None,

    # HEADING 3
    "h3_font": None,
    "h3_size_halfpt": None,
    "h3_alignment": None,
    "h3_is_bold": None,
    "h3_is_italic": None,
    "h3_is_underline": None,
    "h3_space_before": None,
    "h3_space_after": None,

    # HEADING 4
    "h4_font": None,
    "h4_size_halfpt": None,
    "h4_alignment": None,
    "h4_is_bold": None,
    "h4_is_italic": None,
    "h4_is_underline": None,

    # HEADING 5
    "h5_font": None,
    "h5_size_halfpt": None,
    "h5_alignment": None,
    "h5_is_bold": None,
    "h5_is_italic": None,

    # HEADING 6
    "h6_font": None,
    "h6_size_halfpt": None,
    "h6_alignment": None,
    "h6_is_bold": None,
    "h6_is_italic": None,

    # PAGE NUMBERING
    "has_page_numbers": None,
    "page_number_format": None,       # decimal, roman, lowercase, etc.
    "page_number_alignment": None,    # left, center, right

    # DOCUMENT ELEMENTS COUNT
    "element_count_tables": None,
    "element_count_images": None,
    "element_count_lists": None,
    "element_count_paragraphs": None,

    # QUALITY FLAGS
    "flag_markdown_leak": None,        # Detected markdown syntax in text
    "flag_artifact_numbers": None,     # Detected artifact/temp numbers
    "flag_mixed_fonts": None,          # Multiple fonts in body
    "flag_inconsistent_spacing": None, # Inconsistent line spacing

    # METADATA
    "_confidence": "low",              # low, medium, high
    "_warnings": [],                   # List of warnings during extraction
}


def extract_rules(docx_bytes: bytes, source_filename: str) -> dict[str, Any]:
    """
    Extract formatting rules from DOCX file.
    
    Args:
        docx_bytes: Raw bytes of DOCX file
        source_filename: Filename for reference
    
    Returns:
        Dictionary with 52 keys (all from NEUTRAL_DEFAULTS)
        None values indicate key was not extractable from this document
    """
    rules = NEUTRAL_DEFAULTS.copy()
    warnings = []
    
    try:
        # Open DOCX as ZIP
        docx_zip = zipfile.ZipFile(io.BytesIO(docx_bytes), 'r')
        
        # Parse document.xml
        doc_xml = docx_zip.read('word/document.xml')
        doc_root = ET.fromstring(doc_xml)
        
        # Define namespaces
        ns = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        }
        
        # Extract page settings
        _extract_page_settings(doc_root, rules, ns, warnings)
        
        # Extract body formatting
        _extract_body_formatting(doc_root, rules, ns, warnings)
        
        # Extract headings
        _extract_headings(doc_root, rules, ns, warnings)
        
        # Extract document structure
        _extract_document_elements(doc_root, rules, ns, warnings)
        
        # Check quality flags
        _check_quality_flags(doc_root, rules, ns, warnings)

        # Ensure all schema keys are populated for deterministic downstream usage.
        _apply_inference_and_fallbacks(rules)
        
        # Close ZIP
        docx_zip.close()
        
        rules['_warnings'] = warnings
        rules['_confidence'] = 'medium' if len(warnings) < 3 else 'low'
        
    except Exception as e:
        warnings.append(f"Extraction error: {str(e)}")
        _apply_inference_and_fallbacks(rules)
        rules['_warnings'] = warnings
        rules['_confidence'] = 'low'
    
    return rules


def _extract_page_settings(root: ET.Element, rules: dict, ns: dict, warnings: list) -> None:
    """Extract page size and margins from document settings"""
    try:
        # Find section properties
        sectPr = root.find('.//w:sectPr', ns)
        if sectPr is None:
            return
        
        # Page size (pgSz)
        pgSz = sectPr.find('w:pgSz', ns)
        if pgSz is not None:
            w = pgSz.get('{' + ns['w'] + '}w')
            h = pgSz.get('{' + ns['w'] + '}h')
            if w:
                rules['page_width_dxa'] = int(w)
            if h:
                rules['page_height_dxa'] = int(h)
        
        # Margins (pgMar)
        pgMar = sectPr.find('w:pgMar', ns)
        if pgMar is not None:
            top = pgMar.get('{' + ns['w'] + '}top')
            bottom = pgMar.get('{' + ns['w'] + '}bottom')
            left = pgMar.get('{' + ns['w'] + '}left')
            right = pgMar.get('{' + ns['w'] + '}right')
            header = pgMar.get('{' + ns['w'] + '}header')
            footer = pgMar.get('{' + ns['w'] + '}footer')
            
            if top:
                rules['margin_top_dxa'] = int(top)
            if bottom:
                rules['margin_bottom_dxa'] = int(bottom)
            if left:
                rules['margin_left_dxa'] = int(left)
            if right:
                rules['margin_right_dxa'] = int(right)
            if header:
                rules['margin_header_dxa'] = int(header)
            if footer:
                rules['margin_footer_dxa'] = int(footer)
    except Exception as e:
        warnings.append(f"Page settings extraction failed: {str(e)}")


def _extract_body_formatting(root: ET.Element, rules: dict, ns: dict, warnings: list) -> None:
    """Extract body text formatting from Normal or document defaults style"""
    try:
        # Get first paragraph to infer body formatting
        paragraphs = root.findall('.//w:p', ns)
        if not paragraphs:
            return
        
        for p in paragraphs[:10]:  # Check first 10 paragraphs
            # Get run properties
            rPr = p.find('.//w:rPr', ns)
            if rPr is None:
                continue
            
            # Font
            rFonts = rPr.find('w:rFonts', ns)
            if rFonts is not None:
                ascii_font = rFonts.get('{' + ns['w'] + '}ascii')
                if ascii_font and rules['body_font'] is None:
                    rules['body_font'] = ascii_font
            
            # Font size
            sz = rPr.find('w:sz', ns)
            if sz is not None:
                size = sz.get('{' + ns['w'] + '}val')
                if size and rules['body_size_halfpt'] is None:
                    rules['body_size_halfpt'] = int(size)
            
            # Bold, Italic, Underline
            if rPr.find('w:b', ns) is not None and rules['body_is_bold'] is None:
                rules['body_is_bold'] = True
            if rPr.find('w:i', ns) is not None and rules['body_is_italic'] is None:
                rules['body_is_italic'] = True
            if rPr.find('w:u', ns) is not None and rules['body_is_underline'] is None:
                rules['body_is_underline'] = True
        
        # Paragraph alignment and spacing
        pPr = paragraphs[0].find('w:pPr', ns)
        if pPr is not None:
            jc = pPr.find('w:jc', ns)
            if jc is not None:
                val = jc.get('{' + ns['w'] + '}val')
                if val:
                    rules['body_alignment'] = val
            
            spacing = pPr.find('w:spacing', ns)
            if spacing is not None:
                line = spacing.get('{' + ns['w'] + '}line')
                lineRule = spacing.get('{' + ns['w'] + '}lineRule')
                before = spacing.get('{' + ns['w'] + '}before')
                after = spacing.get('{' + ns['w'] + '}after')
                
                if line:
                    rules['body_line_spacing_val'] = int(line)
                if lineRule:
                    rules['body_line_spacing_rule'] = lineRule
                if before:
                    rules['body_space_before'] = int(before)
                if after:
                    rules['body_space_after'] = int(after)
            
            ind = pPr.find('w:ind', ns)
            if ind is not None:
                firstLine = ind.get('{' + ns['w'] + '}firstLine')
                if firstLine:
                    rules['body_first_line_indent_dxa'] = int(firstLine)
    except Exception as e:
        warnings.append(f"Body formatting extraction failed: {str(e)}")


def _extract_headings(root: ET.Element, rules: dict, ns: dict, warnings: list) -> None:
    """Extract heading formatting from heading styles"""
    try:
        # Find all paragraphs with heading styles
        paragraphs = root.findall('.//w:p', ns)
        
        heading_levels = {}
        
        for p in paragraphs:
            pPr = p.find('w:pPr', ns)
            if pPr is None:
                continue
            
            pStyle = pPr.find('w:pStyle', ns)
            if pStyle is None:
                continue
            
            style_val = pStyle.get('{' + ns['w'] + '}val', '')
            
            # Match heading styles
            match = re.match(r'Heading(\d)', style_val)
            if not match:
                continue
            
            level = match.group(1)
            if level not in heading_levels:
                heading_levels[level] = {
                    'font': None,
                    'size_halfpt': None,
                    'alignment': None,
                    'is_bold': False,
                    'is_italic': False,
                    'is_underline': False,
                    'space_before': None,
                    'space_after': None,
                }
            
            # Extract run properties
            rPr = p.find('.//w:rPr', ns)
            if rPr is not None:
                # Font
                rFonts = rPr.find('w:rFonts', ns)
                if rFonts is not None:
                    ascii_font = rFonts.get('{' + ns['w'] + '}ascii')
                    if ascii_font:
                        heading_levels[level]['font'] = ascii_font
                
                # Size
                sz = rPr.find('w:sz', ns)
                if sz is not None:
                    size = sz.get('{' + ns['w'] + '}val')
                    if size:
                        heading_levels[level]['size_halfpt'] = int(size)
                
                # Bold, Italic, Underline
                if rPr.find('w:b', ns) is not None:
                    heading_levels[level]['is_bold'] = True
                if rPr.find('w:i', ns) is not None:
                    heading_levels[level]['is_italic'] = True
                if rPr.find('w:u', ns) is not None:
                    heading_levels[level]['is_underline'] = True
            
            # Alignment and spacing
            jc = pPr.find('w:jc', ns)
            if jc is not None:
                val = jc.get('{' + ns['w'] + '}val')
                if val:
                    heading_levels[level]['alignment'] = val
            
            spacing = pPr.find('w:spacing', ns)
            if spacing is not None:
                before = spacing.get('{' + ns['w'] + '}before')
                after = spacing.get('{' + ns['w'] + '}after')
                if before:
                    heading_levels[level]['space_before'] = int(before)
                if after:
                    heading_levels[level]['space_after'] = int(after)
        
        # Store extracted heading levels
        for level, props in heading_levels.items():
            prefix = f'h{level}'
            rules[f'{prefix}_font'] = props['font']
            rules[f'{prefix}_size_halfpt'] = props['size_halfpt']
            rules[f'{prefix}_alignment'] = props['alignment']
            rules[f'{prefix}_is_bold'] = props['is_bold'] if props['is_bold'] else None
            rules[f'{prefix}_is_italic'] = props['is_italic'] if props['is_italic'] else None
            rules[f'{prefix}_is_underline'] = props['is_underline'] if props['is_underline'] else None
            rules[f'{prefix}_space_before'] = props['space_before']
            rules[f'{prefix}_space_after'] = props['space_after']
    except Exception as e:
        warnings.append(f"Heading extraction failed: {str(e)}")


def _extract_document_elements(root: ET.Element, rules: dict, ns: dict, warnings: list) -> None:
    """Extract counts of tables, images, lists, paragraphs"""
    try:
        paragraphs = root.findall('.//w:p', ns)
        tables = root.findall('.//w:tbl', ns)
        
        # Count images
        images = root.findall('.//a:blip', {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
        
        # Count lists
        lists = sum(1 for p in paragraphs if p.find('.//w:pStyle', ns) is not None and 
                   'List' in p.find('.//w:pStyle', ns).get('{' + ns['w'] + '}val', ''))
        
        rules['element_count_paragraphs'] = len(paragraphs)
        rules['element_count_tables'] = len(tables)
        rules['element_count_images'] = len(images)
        rules['element_count_lists'] = lists
    except Exception as e:
        warnings.append(f"Element counting failed: {str(e)}")


def _check_quality_flags(root: ET.Element, rules: dict, ns: dict, warnings: list) -> None:
    """Check for quality issues in document"""
    try:
        # Get all text content
        all_text = ' '.join([t.text or '' for t in root.findall('.//w:t', ns)])
        
        # Check for markdown syntax
        if re.search(r'#{1,6}\s+|^\*\*|`{3}|---|\[.*\]\(.*\)', all_text):
            rules['flag_markdown_leak'] = True
        
        # Check for artifact numbers
        if re.search(r'\d{10,}|artifact_\d+|temp_\d+', all_text):
            rules['flag_artifact_numbers'] = True
        
        # Check for mixed fonts
        fonts = set()
        for rFonts in root.findall('.//w:rFonts', ns):
            ascii_font = rFonts.get('{' + ns['w'] + '}ascii')
            if ascii_font:
                fonts.add(ascii_font)
        
        if len(fonts) > 3:
            rules['flag_mixed_fonts'] = True
        
        # Check for inconsistent spacing
        spacings = []
        for spacing in root.findall('.//w:spacing', ns):
            line = spacing.get('{' + ns['w'] + '}line')
            if line:
                spacings.append(int(line))
        
        if len(set(spacings)) > 3:
            rules['flag_inconsistent_spacing'] = True
    except Exception as e:
        warnings.append(f"Quality check failed: {str(e)}")


def _apply_inference_and_fallbacks(rules: dict[str, Any]) -> None:
    """Fill missing extracted values using inferred relationships and stable fallbacks."""
    # Use body settings as a fallback anchor for missing heading fields.
    body_font = rules.get("body_font")
    body_alignment = rules.get("body_alignment")

    for level in range(1, 7):
        prefix = f"h{level}"
        if rules.get(f"{prefix}_font") is None and body_font is not None:
            rules[f"{prefix}_font"] = body_font
        if rules.get(f"{prefix}_alignment") is None and body_alignment is not None:
            rules[f"{prefix}_alignment"] = body_alignment

    # Fill all remaining schema gaps with deterministic defaults.
    for key in list(rules.keys()):
        if key.startswith("_"):
            continue
        if rules.get(key) is None and key in EXTRACTION_FALLBACKS:
            rules[key] = EXTRACTION_FALLBACKS[key]

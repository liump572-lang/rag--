"""
课设报告格式修复脚本
根据《课设报告内容及格式规范》修复文档格式：
- 页面设置：A4, 上2.5cm, 左2.5cm, 下右各2cm, 装订线0.5cm
- 一级标题：小三黑体加粗顶格，单倍行距，段前段后0.5行
- 二级标题：四号宋体加粗顶格，单倍行距，段前0.5行
- 三级标题：四号宋体顶格，单倍行距，段前0.5行
- 正文：小四宋体+Times New Roman，行距固定值18磅，首行缩进两字符
- 图题/表题：五号字，段前6磅，段后6磅，居中
- 页码：正文页脚居中，从1开始
"""

import copy
import re
from docx import Document
from docx.shared import Pt, Cm, Emu, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
from lxml import etree

INPUT_FILE = '课设报告_基于RAG的计算机学科知识点智能问答系统.docx'
OUTPUT_FILE = '课设报告_基于RAG的计算机学科知识点智能问答系统_格式修复.docx'


def set_run_font(run, font_name_cn='宋体', font_name_en='Times New Roman', size_pt=12, bold=None):
    """设置run的字体"""
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    # 设置中文字体
    run.font.name = font_name_en
    r = run._element
    rPr = r.find(qn('w:rPr'))
    if rPr is None:
        rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
        r.insert(0, rPr)
    # 设置东亚字体
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")}></w:rFonts>')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:eastAsia'), font_name_cn)
    rFonts.set(qn('w:ascii'), font_name_en)
    rFonts.set(qn('w:hAnsi'), font_name_en)


def set_paragraph_spacing(paragraph, before_pt=None, after_pt=None, line_spacing_pt=None, line_spacing_rule=None):
    """设置段落间距"""
    pf = paragraph.paragraph_format
    if before_pt is not None:
        pf.space_before = Pt(before_pt)
    if after_pt is not None:
        pf.space_after = Pt(after_pt)
    if line_spacing_pt is not None:
        pf.line_spacing = Pt(line_spacing_pt)
    if line_spacing_rule is not None:
        pf.line_spacing_rule = line_spacing_rule


def set_paragraph_indent(paragraph, first_line_chars=None, first_line_cm=None):
    """设置首行缩进"""
    pf = paragraph.paragraph_format
    if first_line_chars is not None:
        # 小四(12pt) * 2字符 ≈ 24pt ≈ 0.85cm
        pf.first_line_indent = Pt(12 * first_line_chars)
    elif first_line_cm is not None:
        pf.first_line_indent = Cm(first_line_cm)


# 文档的六个主章节标题
H1_TITLES = {
    '一、需求分析', '二、概要设计', '三、详细设计',
    '四、系统实现及结果分析', '五、总结与思考', '六、附录'
}


def is_h1(text):
    """判断是否为一级标题（仅匹配六个主章节标题）"""
    t = text.strip()
    return t in H1_TITLES


def is_h2(text):
    """判断是否为二级标题（如 1.1 问题描述）"""
    return bool(re.match(r'^\d+\.\d+\s', text.strip()))


def is_h3(text):
    """判断是否为三级标题（如 1.2.1 产品视角）"""
    return bool(re.match(r'^\d+\.\d+\.\d+\s', text.strip()))


def is_sub_section(text):
    """判断是否为子模块标题（如 一、用户认证模块，非主章节标题）"""
    t = text.strip()
    return bool(re.match(r'^[一二三四五六七八九十]+、', t)) and t not in H1_TITLES


def is_fig_caption(text):
    """判断是否为图题（如 图2-1 xxx）"""
    return bool(re.match(r'^图\d+-\d+\s', text.strip()))


def is_table_caption(text):
    """判断是否为表题（如 表2-1 xxx）"""
    return bool(re.match(r'^表\d+-\d+\s', text.strip()))


def is_cover_page(paragraphs, index):
    """判断段落是否在封面区域（第一个一级标题之前）"""
    for i in range(index, len(paragraphs)):
        text = paragraphs[i].text.strip()
        if is_h1(text):
            return i != index  # 如果当前段就是一级标题，不在封面
    return True


def fix_page_setup(doc):
    """修复页面设置"""
    for section in doc.sections:
        section.page_width = Cm(21)     # A4 宽
        section.page_height = Cm(29.7)  # A4 高
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2)
        section.gutter = Cm(0.5)        # 装订线


def add_page_numbers(doc):
    """添加页码到页脚（正文从1开始）"""
    # 找到正文开始的位置（第一个一级标题所在的section）
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        # 清空已有内容
        for p in footer.paragraphs:
            p.clear()

        # 添加页码
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 设置页码字体
        run = p.add_run()
        set_run_font(run, '宋体', 'Times New Roman', 10.5)

        # 插入 PAGE 字段
        fldChar1 = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>')
        run._element.append(fldChar1)

        instrText = parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>')
        run._element.append(instrText)

        fldChar2 = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>')
        run._element.append(fldChar2)


def fix_formatting(doc):
    """修复所有段落格式"""
    paragraphs = doc.paragraphs
    found_first_h1 = False

    for i, p in enumerate(paragraphs):
        text = p.text.strip()
        if not text:
            continue

        # 封面区域：跳过格式修改（保持原有封面样式）
        if not found_first_h1 and not is_h1(text):
            continue

        if is_h1(text):
            found_first_h1 = True
            # 一级标题：小三(15pt) 黑体 加粗 顶格 单倍行距 段前段后0.5行
            for run in p.runs:
                set_run_font(run, '黑体', '黑体', 15, bold=True)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.line_spacing = Pt(15 * 1.2)  # 单倍行距 ≈ 字号×1.2
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pf.space_before = Pt(15 * 0.5)  # 0.5行
            pf.space_after = Pt(15 * 0.5)
            continue

        if is_h2(text):
            # 二级标题：四号(14pt) 宋体 加粗 顶格 单倍行距 段前0.5行
            for run in p.runs:
                set_run_font(run, '宋体', 'Times New Roman', 14, bold=True)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pf.space_before = Pt(14 * 0.5)
            pf.space_after = Pt(0)
            continue

        if is_h3(text):
            # 三级标题：四号(14pt) 宋体 顶格 单倍行距 段前0.5行
            for run in p.runs:
                set_run_font(run, '宋体', 'Times New Roman', 14, bold=None)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pf.space_before = Pt(14 * 0.5)
            pf.space_after = Pt(0)
            continue

        if is_sub_section(text):
            # 子模块标题（如 一、用户认证模块）：小四(12pt) 宋体 加粗 顶格
            for run in p.runs:
                set_run_font(run, '宋体', 'Times New Roman', 12, bold=True)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pf.space_before = Pt(6)
            pf.space_after = Pt(3)
            continue

        if is_fig_caption(text):
            # 图题：五号(10.5pt) 居中 段前6磅 段后6磅
            for run in p.runs:
                set_run_font(run, '宋体', 'Times New Roman', 10.5)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(6)
            pf.space_after = Pt(6)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            continue

        if is_table_caption(text):
            # 表题：五号(10.5pt) 居中 段前6磅 段后6磅
            for run in p.runs:
                set_run_font(run, '宋体', 'Times New Roman', 10.5)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(6)
            pf.space_after = Pt(6)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            continue

        # 附录标题
        if text.startswith('六、附录') or text.startswith('附录'):
            if is_h1(text):
                continue  # 已在上面处理
            # 附录子标题当作二级标题处理
            if re.match(r'^附录[A-Z]', text):
                for run in p.runs:
                    set_run_font(run, '宋体', 'Times New Roman', 14, bold=True)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                pf = p.paragraph_format
                pf.first_line_indent = Pt(0)
                from docx.enum.text import WD_LINE_SPACING
                pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
                pf.space_before = Pt(14 * 0.5)
                pf.space_after = Pt(0)
                continue

        # 正文：小四(12pt) 宋体+Times New Roman 行距固定值18磅 首行缩进两字符
        for run in p.runs:
            # 保留原有的加粗/颜色等格式，只修改字体和大小
            original_bold = run.font.bold
            original_color = run.font.color.rgb if run.font.color and run.font.color.rgb else None
            set_run_font(run, '宋体', 'Times New Roman', 12, bold=original_bold)
            if original_color:
                run.font.color.rgb = original_color

        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # 两端对齐
        pf = p.paragraph_format
        pf.first_line_indent = Pt(24)  # 12pt × 2 = 24pt ≈ 两字符
        pf.line_spacing = Pt(18)       # 固定值18磅
        from docx.enum.text import WD_LINE_SPACING
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)


def fix_table_formats(doc):
    """修复表格内文字格式（五号字 = 10.5pt）"""
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_run_font(run, '宋体', 'Times New Roman', 10.5)


def main():
    print(f'正在读取文档: {INPUT_FILE}')
    doc = Document(INPUT_FILE)

    print('正在修复页面设置...')
    fix_page_setup(doc)

    print('正在修复段落格式...')
    fix_formatting(doc)

    print('正在修复表格格式...')
    fix_table_formats(doc)

    print('正在添加页码...')
    add_page_numbers(doc)

    print(f'正在保存文档: {OUTPUT_FILE}')
    doc.save(OUTPUT_FILE)
    print(f'格式修复完成！已保存为: {OUTPUT_FILE}')


if __name__ == '__main__':
    main()

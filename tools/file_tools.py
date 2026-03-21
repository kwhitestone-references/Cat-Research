"""
文件操作工具 - 工作空间文件读写
"""
import os
import json
import sys
from datetime import datetime
from typing import Any, Optional


def read_file(path: str) -> str:
    """读取文件内容"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"[文件不存在] {path}"
    except PermissionError:
        return f"[权限错误] 无法读取: {path}"
    except Exception as e:
        return f"[读取错误] {path}: {str(e)}"


def write_file(path: str, content: str) -> str:
    """写入文件内容，自动创建目录"""
    try:
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"[写入成功] {path} ({len(content)} 字符)"
    except PermissionError:
        return f"[权限错误] 无法写入: {path}"
    except Exception as e:
        return f"[写入错误] {path}: {str(e)}"


def read_json(path: str) -> Any:
    """读取并解析 JSON 文件，返回 Python 对象"""
    content = read_file(path)
    # 检查是否是错误消息（不是真正的文件内容）
    if not content or content.startswith('[文件不存在]') or content.startswith('[读取错误]') or content.startswith('[权限错误]'):
        return {"error": content, "path": path}
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # 尝试提取可能嵌入在文本中的 JSON
        extracted = _extract_json_from_text(content)
        if extracted is not None:
            return extracted
        return {"error": f"JSON 解析失败: {str(e)}", "path": path, "raw": content[:500]}


def _extract_json_from_text(text: str) -> Optional[Any]:
    """从文本中提取第一个有效的 JSON 对象或数组。
    优先顺序：
    1. ---JSON_START--- / ---JSON_END--- 标记
    2. ```json ... ``` Markdown 代码块
    3. 括号计数器兜底扫描
    """
    # 1. 优先查找标准化标记
    marker_start = text.find("---JSON_START---")
    marker_end = text.find("---JSON_END---")
    if marker_start != -1 and marker_end != -1 and marker_end > marker_start:
        candidate = text[marker_start + 16:marker_end].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2. 尝试 Markdown 代码块 ```json ... ``` 或 ``` ... ```
    import re
    code_block_patterns = [
        r'```json\s*\n([\s\S]*?)\n\s*```',
        r'```\s*\n(\{[\s\S]*?\})\s*\n\s*```',
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # 3. 括号计数器兜底
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break
    return None


def write_json(path: str, data: Any) -> str:
    """将数据序列化为 JSON 并写入文件"""
    try:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return write_file(path, content)
    except (TypeError, ValueError) as e:
        return f"[JSON 序列化错误]: {str(e)}"


def list_files(directory: str) -> str:
    """列出目录中的文件和子目录"""
    try:
        if not os.path.exists(directory):
            return f"[目录不存在] {directory}"

        items = []
        for item in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, item)
            if os.path.isdir(full_path):
                count = len(os.listdir(full_path))
                items.append(f"📁 {item}/  ({count} 项)")
            else:
                size = os.path.getsize(full_path)
                size_str = f"{size:,} B" if size < 1024 else f"{size//1024:,} KB"
                items.append(f"📄 {item}  ({size_str})")

        if not items:
            return f"[空目录] {directory}"

        return f"目录: {directory}\n" + "\n".join(items)
    except Exception as e:
        return f"[列目录错误] {directory}: {str(e)}"


def append_to_log(path: str, message: str) -> bool:
    """追加日志记录，返回是否成功"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(log_line)
        return True
    except Exception as e:
        # 日志失败时输出到 stderr，不影响主流程
        print(f"[日志错误] {str(e)}", file=sys.stderr)
        return False


def normalize_path(path: str) -> str:
    """将路径中的反斜杠统一为正斜杠（适配跨平台）"""
    return path.replace('\\', '/')

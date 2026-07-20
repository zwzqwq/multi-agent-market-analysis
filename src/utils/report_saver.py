from src.models.contracts import DraftReport
from pathlib import Path

def save_report(draft: DraftReport, output_path: str) -> str:
    """将报告按照markdown格式保存到指定路径"""
    file_path=Path(output_path)
    if file_path.exists():
        print("目录已存在")
    else:
        file_path.mkdir(parents=True, exist_ok=True)
        print("目录不存在，执行创建流程")
    
    create_time=draft.metadata.get("generated_at","")
    # 文件名不能包含 Windows 不支持的字符
    topic=draft.topic
    safe_time = create_time.replace(":", "-").replace(" ", "_")
    safe_topic = "".join(c for c in topic if c not in r'<>:"/\|?*')
    filename = f"{safe_topic}_{safe_time}.md"
    sections = draft.sections

    with open(file_path/filename,'w',encoding='utf-8') as f:
        f.write(f"#{topic}\n")
        f.write(f">{create_time}\n")
        for section in sections:
            f.write(f"## {section.title}\n")
            f.write(f"{section.content}\n")
    
    return str(file_path/filename)
    

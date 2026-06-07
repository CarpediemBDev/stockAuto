import glob
import json

with open('search_output.txt', 'w', encoding='utf-8') as out:
    for file_path in glob.glob('C:/Users/Im/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '네이버' in line or '토스' in line or 'KIS 종목발굴' in line or '종목발굴' in line:
                        data = json.loads(line)
                        if data.get('type') in ('USER_INPUT', 'PLANNER_RESPONSE'):
                            content = data.get('content', '')[:1000]
                            out.write(f"[{file_path[-45:-37]}] {content}\n")
                            out.write("-" * 50 + "\n")
        except Exception as e:
            pass

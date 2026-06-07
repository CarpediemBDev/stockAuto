import json

with open('conv_history.txt', 'w', encoding='utf-8') as out:
    try:
        with open('C:/Users/Im/.gemini/antigravity/brain/ca8f4bea-87d3-4ecd-8321-28d8681ed885/.system_generated/logs/transcript.jsonl', 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                if data.get('type') in ('USER_INPUT', 'PLANNER_RESPONSE'):
                    out.write(f"[{data.get('type')}] {data.get('content', '')}\n")
                    out.write("="*80 + "\n")
    except Exception as e:
        out.write(str(e))

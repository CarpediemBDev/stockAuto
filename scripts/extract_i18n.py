import os
import re
import json

def extract_korean_strings():
    print("[*] 스크립트 시작: 한국어 문자열 추출 중...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(base_dir, 'frontend')
    backend_dir = os.path.join(base_dir, 'backend')
    
    korean_regex = re.compile(r'[\'"]([^\'"]*[가-힣]+[^\'"]*)[\'"]')
    
    results = {
        "frontend": {},
        "backend": {}
    }
    
    # 1. 프론트엔드 스캔 (.tsx)
    if os.path.exists(frontend_dir):
        for root, _, files in os.walk(frontend_dir):
            if 'node_modules' in root or '.next' in root:
                continue
            for file in files:
                if file.endswith('.tsx'):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, frontend_dir)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            matches = korean_regex.findall(content)
                            if matches:
                                results["frontend"][rel_path] = list(set(matches))
                    except Exception as e:
                        pass
                        
    # 2. 백엔드 스캔 (.py)
    if os.path.exists(backend_dir):
        for root, _, files in os.walk(backend_dir):
            if 'venv' in root or '__pycache__' in root or 'alembic' in root:
                continue
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, backend_dir)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            matches = korean_regex.findall(content)
                            if matches:
                                results["backend"][rel_path] = list(set(matches))
                    except Exception as e:
                        pass

    output_file = os.path.join(base_dir, 'locales', 'korean_strings_report.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"[*] 추출 완료. {output_file} 에 저장되었습니다.")

if __name__ == "__main__":
    extract_korean_strings()

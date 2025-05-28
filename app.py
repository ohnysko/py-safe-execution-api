from flask import Flask, jsonify, request
import tempfile
import subprocess
import json
import os
import textwrap
import re

app = Flask(__name__)

ALLOWED_MODULES = {
    'os', 'pandas', 'numpy', 'json', 'sys', 'math', 'random', 
    'datetime', 'collections', 'itertools', 'functools', 'time'
}

def validate_script(script):
    # Compile regex patterns once for better performance
    IMPORT_PATTERNS = [
        re.compile(r'(?:^|\n)\s*import\s+(\w+)'),  # import module
        re.compile(r'(?:^|\n)\s*from\s+(\w+)(?:\.\w+)*\s+import\s+(\w+)'),  # from module import name
        re.compile(r'(?:^|\n)\s*import\s+(\w+)\s+as\s+\w+'),  # import module as alias
        re.compile(r'(?:^|\n)\s*from\s+(\w+)(?:\.\w+)*\s+import\s+\w+\s+as\s+\w+'),  # from module import as alias
    ]
    
    DANGEROUS_NAMES = {'system', 'popen', 'spawn', 'fork', 'kill', 'exec', 'eval'}
    DANGEROUS_PATTERNS = [
        re.compile(r'__import__\s*\('),
        re.compile(r'eval\s*\('),
        re.compile(r'exec\s*\('),
        re.compile(r'os\.system\s*\('),
        re.compile(r'subprocess\s*\.'),
        re.compile(r'open\s*\('),
        re.compile(r'file\s*\('),
        re.compile(r'\.__dict__'),
        re.compile(r'\.__class__'),
        re.compile(r'\.__bases__'),
        re.compile(r'\.__subclasses__'),
        re.compile(r'\.__globals__'),
        re.compile(r'\.__builtins__'),
        re.compile(r'\.connect\s*\('),
        re.compile(r'\.bind\s*\('),
        re.compile(r'\.listen\s*\('),
        re.compile(r'\.accept\s*\('),
        re.compile(r'\.send\s*\('),
        re.compile(r'\.recv\s*\('),
        re.compile(r'\.sendto\s*\('),
        re.compile(r'\.recvfrom\s*\('),
        re.compile(r'\.getaddrinfo\s*\('),
        re.compile(r'\.gethostbyname\s*\('),
        re.compile(r'\.gethostbyaddr\s*\('),
        re.compile(r'\.getservbyname\s*\('),
        re.compile(r'\.getservbyport\s*\('),
        re.compile(r'\.socket\s*\('),
    ]
    
    # Check imports
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(script):
            module = match.group(1)
            if module not in ALLOWED_MODULES or module in DANGEROUS_NAMES:
                raise ValueError(f"Potentially dangerous import detected")
    
    # Check for dangerous names in from-import statements
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(script):
            if len(match.groups()) > 1:  # This is a from-import statement
                imported_name = match.group(2)
                if imported_name in DANGEROUS_NAMES:
                    raise ValueError(f"Potentially dangerous import detected")
    
    # Check dangerous operations
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(script):
            raise ValueError(f"Potentially dangerous operation detected")

@app.route("/execute", methods=["POST"])
def execute():
    data = request.get_json()

    if not data or "script" not in data:
        return jsonify({"error": "Missing 'script' in request"}), 400
    
    script = data.get("script")

    if 'def main' not in script:
        return jsonify({"error": "Script must define a main() function"}), 400
    
    try:
        validate_script(script)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Create a temporary file for the script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        wrapped_script = f"{script.rstrip()}\n\n" + textwrap.dedent("""\
    if __name__ == "__main__":
        import json
        import sys
        import os
        import pandas
        import numpy
        result = main()
        # something can be printed to stdout while executing main
        # add a print to divide stdout and return
        print("--------------------------------")
        try:
            print(json.dumps(result))
        except Exception as e:
            print(json.dumps({"error": f"Error serializing result: {str(e)}"}))
""")
        f.write(wrapped_script)
        f.flush()
        script_path = f.name
        
        try:
            # Execute the script using nsjail
            cmd = [
                "nsjail",
                "--config", "./config.proto",
                "--",
                "/usr/local/bin/python3", script_path
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )

            whole_stdout = result.stdout.strip()
            outputs = whole_stdout.split("--------------------------------\n")
            stdout = outputs[0]
            return_value = outputs[1]

            # Validate that return value is valid JSON
            parsed_json = json.loads(return_value)
            if not isinstance(parsed_json, dict) or "error" in parsed_json:
                return jsonify({
                    "error": "Script must return a valid JSON value",
                    "stdout": stdout
                }), 400
            
            return jsonify({
                "result": parsed_json,
                "stdout": stdout
            })
        
        except subprocess.TimeoutExpired:
            return jsonify({
                "error": "Script execution timed out after 5 seconds",
                "stdout": ""
            }), 400
        except Exception as e:
            return jsonify({
                "error": "Script execution failed",
                "stderr": str(e)
            }), 400
        finally:
            if 'script_path' in locals():
                os.remove(script_path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
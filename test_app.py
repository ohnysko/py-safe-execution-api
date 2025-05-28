import pytest
from app import app, validate_script
import json

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_missing_script(client):
    """Test that a request without 'script' field returns 400 error"""
    response = client.post('/execute', json={'blabla': 'blabla'})
    assert response.status_code == 400
    assert response.json == {"error": "Missing 'script' in request"}

def test_missing_main_function(client):
    """Test that a script without main() function returns 400 error"""
    response = client.post('/execute', json={
        "script": "print('Hello')"
    })
    assert response.status_code == 400
    assert response.json == {"error": "Script must define a main() function"}

def test_non_json_return(client):
    """Test that a main function returning non-JSON value throws an exception"""
    # Test with a string (not a JSON object)
    response = client.post('/execute', json={
        "script": "def main():\n    return 'Hello'"
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "Script must return a valid JSON value" in response.json["error"]
    
    # Test with a Python object that isn't JSON serializable
    response = client.post('/execute', json={
        "script": "def main():\n    return {'key': lambda x: x}"
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "Script must return a valid JSON value" in response.json["error"]

def test_valid_json_return(client):
    """Test that a main function returning valid JSON works correctly"""
    response = client.post('/execute', json={
        "script": "def main():\n    return {'message': 'Hello', 'number': 42}"
    })
    assert response.status_code == 200
    assert response.json["result"] == {"message": "Hello", "number": 42}

def test_various_json_return_types(client):
    """Test that main function can return various valid JSON types"""
    test_cases = [
        # Test with different JSON-compatible types
        ("def main():\n    return {'list': [1, 2, 3]}", {"list": [1, 2, 3]}),
        ("def main():\n    return {'nested': {'key': 'value'}}", {"nested": {"key": "value"}}),
        ("def main():\n    return {'numbers': [1.5, 2.5]}", {"numbers": [1.5, 2.5]}),
        ("def main():\n    return {'boolean': True}", {"boolean": True}),
        ("def main():\n    return {'null': None}", {"null": None}),
    ]
    
    for script, expected in test_cases:
        response = client.post('/execute', json={"script": script})
        assert response.status_code == 200
        assert response.json["result"] == expected

def test_stdout_capture(client):
    """Test that stdout is properly captured and returned"""
    script = """
def main():
    print("Hello from stdout")
    print("Multiple lines")
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 200
    assert response.json["stdout"] == "Hello from stdout\nMultiple lines\n"
    assert response.json["result"] == {"status": "success"}

def test_library_access(client):
    """Test that os, pandas, and numpy are accessible"""
    # Test os
    os_script = """
import os
def main():
    return {
        "cwd": os.getcwd(),
        "env": dict(os.environ)
    }
"""
    response = client.post('/execute', json={"script": os_script})
    assert response.status_code == 200
    assert "cwd" in response.json["result"]
    assert "env" in response.json["result"]

    # Test pandas
    pandas_script = """
import pandas as pd
def main():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
    return df.to_dict()
"""
    response = client.post('/execute', json={"script": pandas_script})
    assert response.status_code == 200
    assert response.json["result"] == {
        "A": {'0': 1, '1': 2, '2': 3},
        "B": {'0': 4, '1': 5, '2': 6}
    }

    # Test numpy
    numpy_script = """
import numpy as np
def main():
    arr = np.array([1, 2, 3])
    return {
        "sum": float(arr.sum()),
        "mean": float(arr.mean()),
        "shape": list(arr.shape)
    }
"""
    response = client.post('/execute', json={"script": numpy_script})
    assert response.status_code == 200
    assert response.json["result"] == {
        "sum": 6.0,
        "mean": 2.0,
        "shape": [3]
    }

def test_security_measures(client):
    """Test various security measures"""
    # Test forbidden imports
    forbidden_imports = [
        "import subprocess",
        "import socket",
        "import multiprocessing",
        "from os import system",
        "import builtins",
    ]
    
    for import_stmt in forbidden_imports:
        script = f"""
{import_stmt}
def main():
    return {{"status": "success"}}
"""
        response = client.post('/execute', json={"script": script})
        print(f"\nTesting import: {import_stmt}")
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.json}")
        assert response.status_code == 400
        # Check for either type of import error
        assert "Potentially dangerous import detected" in response.json["error"]

    # Test dangerous operations
    dangerous_operations = [
        "__import__('os')",
        "eval('2+2')",
        "exec('print(1)')",
        "os.system('ls')",
        "subprocess.run(['ls'])",
        "open('/etc/passwd')",
        "().__class__.__bases__",
        "().__class__.__subclasses__()",
        "().__dict__",
        "().__globals__",
    ]
    
    for operation in dangerous_operations:
        script = f"""
def main():
    {operation}
    return {{"status": "success"}}
"""
        response = client.post('/execute', json={"script": script})
        assert response.status_code == 400
        assert "Potentially dangerous operation detected" in response.json["error"]

def test_timeout(client):
    """Test that long-running scripts are terminated"""
    script = """
def main():
    import time
    time.sleep(10)  # This should trigger the timeout
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 400
    assert "Script execution timed out" in response.json["error"]

def test_memory_limit(client):
    """Test that memory-intensive scripts are terminated"""
    script = """
def main():
    # Try to allocate a large amount of memory
    x = [0] * (1024 * 1024 * 1024)  # 1GB of memory
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 400
    assert "Script execution failed" in response.json["error"]

def test_file_system_access(client):
    """Test that file system access is restricted"""
    script = """
def main():
    import os
    # Try to write to a file outside /tmp
    with open('/etc/test.txt', 'w') as f:
        f.write('test')
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 400
    assert "Potentially dangerous operation detected" in response.json["error"]

def test_network_access(client):
    """Test that network access is restricted"""
    script = """
def main():
    import os
    # Try to make a network connection
    s = os.socket()  # This should be caught by our pattern detection
    s.connect(('google.com', 80))
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 400
    assert "Potentially dangerous operation detected" in response.json["error"]

def test_complex_data_processing(client):
    """Test complex data processing with pandas and numpy"""
    script = """
import pandas as pd
import numpy as np
from datetime import datetime

def main():
    # Create a complex DataFrame
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=3),
        'values': [1.5, 2.5, 3.5],
        'categories': ['A', 'B', 'A']
    })
    
    # Perform some operations
    grouped = df.groupby('categories')['values'].agg(['mean', 'sum']).to_dict()
    
    # Create a numpy array and perform operations
    arr = np.array([[1, 2], [3, 4]])
    matrix_ops = {
        'determinant': float(np.linalg.det(arr)),
        'eigenvalues': [float(x) for x in np.linalg.eigvals(arr)]
    }
    
    return {
        'grouped_stats': grouped,
        'matrix_operations': matrix_ops
    }
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 200
    result = response.json["result"]
    assert "grouped_stats" in result
    assert "matrix_operations" in result
    assert "determinant" in result["matrix_operations"]
    assert "eigenvalues" in result["matrix_operations"]

def test_multiple_print_statements(client):
    """Test multiple print statements with different data types"""
    script = """
def main():
    print("String output")
    print(42)
    print([1, 2, 3])
    print({"key": "value"})
    return {"status": "success"}
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 200
    expected_stdout = "String output\n42\n[1, 2, 3]\n{'key': 'value'}\n"
    assert response.json["stdout"] == expected_stdout
    assert response.json["result"] == {"status": "success"}

def test_datetime_operations(client):
    """Test working with dates and times"""
    script = """
from datetime import datetime, timedelta

def main():
    now = datetime.now()
    future = now + timedelta(days=7)
    
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "future_time": future.strftime("%Y-%m-%d %H:%M:%S"),
        "time_difference": str(future - now)
    }
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 200
    result = response.json["result"]
    assert "current_time" in result
    assert "future_time" in result
    assert "time_difference" in result

def test_list_dict_comprehensions(client):
    """Test list and dictionary comprehensions"""
    script = """
def main():
    # List comprehension
    squares = [x**2 for x in range(5)]
    
    # Dictionary comprehension
    square_dict = {x: x**2 for x in range(5)}
    
    # Nested comprehension
    matrix = [[i+j for j in range(3)] for i in range(3)]
    
    return {
        "squares": squares,
        "square_dict": square_dict,
        "matrix": matrix
    }
"""
    response = client.post('/execute', json={"script": script})
    assert response.status_code == 200
    result = response.json["result"]
    assert result["squares"] == [0, 1, 4, 9, 16]
    assert result["square_dict"] == {'0': 0, '1': 1, '2': 4, '3': 9, '4': 16}
    assert result["matrix"] == [[0, 1, 2], [1, 2, 3], [2, 3, 4]]
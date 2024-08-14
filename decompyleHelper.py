import os
import re
import sys
import subprocess
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed

openai.api_key = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
pycdc_path = r"pycdc.exe"
pycdas_path = r"pycdas.exe"


def find_py_files(directory):
    py_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    return py_files

def decompile_pyc_file(pyc_file_path):
    py_file_path = os.path.splitext(pyc_file_path)[0] + '.py'
    command = [pycdc_path, pyc_file_path]

    try:
        print(f"Running command: {' '.join(command)}")
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        output = e.output
        print(f"Failed to decompile {pyc_file_path}: {output}")
    except Exception as e:
        output = str(e)
        print(f"Unexpected error while processing {pyc_file_path}: {output}")

    with open(py_file_path, 'w', encoding='utf-8') as py_file:
        py_file.write(output)
    print(f"Output saved to {py_file_path}")

def traverse_and_decompile(root_dir, max_workers=4):
    pyc_files = []
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.pyc'):
                pyc_file_path = os.path.join(subdir, file)
                pyc_files.append(pyc_file_path)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(decompile_pyc_file, pyc_file_path) for pyc_file_path in pyc_files]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error during processing: {e}")
                
def find_broken_methods(file_path):
    broken_methods = []
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
        method_pattern = re.compile(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(.*?\):')
        warning_pattern = re.compile(r'# WARNING: Decompyle incomplete')
        node_pattern = re.compile(r'<NODE')
        lambda_pattern = re.compile(r'\(lambda')

        methods = method_pattern.findall(content)
        for method in methods:
            method_start = content.find(f'def {method}')
            method_end = content.find('def ', method_start + 1)
            if method_end == -1:
                method_end = len(content)
            method_body = content[method_start:method_end]
            if warning_pattern.search(method_body) or node_pattern.search(method_body) or lambda_pattern.search(method_body):
                broken_methods.append((method, method_start, method_end))
    return broken_methods
    
def run_pycdas(file_path):
    try:
        result = subprocess.run([pycdas_path, file_path.replace(".py", ".pyc")], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error running pycdas on {file_path}: {e}"

def extract_bytecode(pycdc_output, method_name):
    pattern = re.compile(rf"(?s)(\[Code\])(?:(?!\[Code\]).)*Object Name: {method_name}.*?{method_name}'", re.DOTALL)
    match = pattern.search(pycdc_output)
    if match:
        return match.group(0)
    else:
        return None
    
def save_decompiled_code(file_path, method_name, decompiled_code):
    base_path = os.path.splitext(file_path)[0]
    fixed_file_path = f"{base_path}_{method_name}_fixed.py"
    with open(fixed_file_path, 'w', encoding='utf-8') as file:
        file.write(decompiled_code)
    print(f"Decompiled code for method '{method_name}' saved to '{fixed_file_path}'")

def gpt4o_decompile(bytecode):
    #You can even use gpt3.5 here if your api key does not allow use of gpt4+, only real benefit of gpt4+ is context window for larger methods to fix
    try:
        response = openai.chat.completions.create(
          model="gpt-4o",
          messages=[
              {"role": "system", "content": "You are a Python code decompiler."},
              {"role": "user", "content": f"Convert this python bytecode back to python code as best as you can ONLY THE METHOD NOTHING ELSE no imports for example, respond just with the code and not in a block:\n\n{bytecode}"}
          ],
          max_tokens=4000
        )
        code_block_pattern = re.compile(r'```(?:python)?(.*?)```', re.DOTALL)
        match = code_block_pattern.search(response.choices[0].message.content.strip())
        if match:
            return match.group(1).strip()
        
        return response.choices[0].message.content.strip()
    except:
        response = openai.chat.completions.create(
          model="gpt-3.5-turbo",
          messages=[
              {"role": "system", "content": "You are a Python code decompiler."},
              {"role": "user", "content": f"Convert this python bytecode back to python code as best as you can ONLY THE METHOD NOTHING ELSE no imports for example, respond just with the code and not in a block:\n\n{bytecode}"}
          ],
          max_tokens=4000
        )
        code_block_pattern = re.compile(r'```(?:python)?(.*?)```', re.DOTALL)
        match = code_block_pattern.search(response.choices[0].message.content.strip())
        if match:
            return match.group(1).strip()
        
        return response.choices[0].message.content.strip()

def save_decompiled_code(file_path, method_name, decompiled_code):
    base_path = os.path.splitext(file_path)[0]
    fixed_file_path = f"{base_path}_{method_name}_fixed.py"
    with open(fixed_file_path, 'w', encoding='utf-8') as file:
        file.write(decompiled_code)
    print(f"Decompiled code for method '{method_name}' saved to '{fixed_file_path}'")
    
def replace_method_in_file(file_path, method_name, new_method_code):
    with open(file_path, 'r+', encoding='utf-8') as file:
        content = file.read()

        method_pattern = re.compile(rf'^(\s*def\s+{method_name}\s*\(.*?\):.*?)(?=^def\s|\Z)', re.DOTALL | re.MULTILINE)

        method_match = method_pattern.search(content)
        if not method_match:
            print(f"Method {method_name} not found in the file.")
            return

        method_start = method_match.start()
        method_end = method_match.end()

        original_indent = re.match(r'\s*', content[method_start:method_start + 1]).group(0)
        indented_new_method_code = ''.join(original_indent + line for line in new_method_code.splitlines())
        indented_new_method_code = indented_new_method_code.rstrip() + '\n\n'
        new_content = content[:method_start] + indented_new_method_code + content[method_end:].lstrip()

        file.seek(0)
        file.write(new_content)
        file.truncate()

    print(f"Replaced method '{method_name}' in {file_path} with corrected code.")

def process_file(py_file):
    broken_methods = find_broken_methods(py_file)
    if broken_methods:
        pycdc_output = run_pycdas(py_file)
        for method, _, _ in broken_methods:
            print(f"Broken method: {method}")
            bytecode = extract_bytecode(pycdc_output, method)
            if bytecode:
                try:
                    decompiled_code = gpt4o_decompile(bytecode)
                    replace_method_in_file(py_file, method, decompiled_code)
                    print(f"Successfully replaced method: {method}")
                except Exception as e:
                    print(f"An AI exception occurred: {e}")
            else:
                print(f"Could not extract bytecode for method '{method}'")

def main(directory):
    traverse_and_decompile(directory, max_workers=40)
    py_files = find_py_files(directory)
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_file, py_file) for py_file in py_files]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error processing file: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        main(directory)
    else:
        print("Usage: decompyleHelper.py <directory_path>")
